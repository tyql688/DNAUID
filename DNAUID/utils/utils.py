import re
import time
import asyncio
import functools
from typing import Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import OrderedDict

import httpx

from gsuid_core.models import Event

TZ = ZoneInfo("Asia/Shanghai")


class TimedCache:
    def __init__(self, timeout=5, maxsize=10):
        self.cache = OrderedDict()
        self.timeout = timeout
        self.maxsize = maxsize

    def set(self, key, value):
        if len(self.cache) >= self.maxsize:
            self._clean_up()
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            self._clean_up()
        self.cache[key] = (value, time.time() + self.timeout)

    def get(self, key):
        if key in self.cache:
            value, expiry = self.cache.pop(key)
            if time.time() < expiry:
                self.cache[key] = (value, expiry)
                return value
        return None

    def delete(self, key):
        if key in self.cache:
            del self.cache[key]

    def _clean_up(self):
        current_time = time.time()
        keys_to_delete = []
        for key, (value, expiry_time) in self.cache.items():
            if expiry_time <= current_time:
                keys_to_delete.append(key)
        for key in keys_to_delete:
            del self.cache[key]


def timed_async_cache(expiration, condition=lambda x: True):
    def decorator(func):
        cache = {}
        locks = {}

        @functools.wraps(func)
        async def wrapper(*args):
            current_time = time.time()
            # 如果是类方法，args[0]是实例，我们获取类名
            if args and hasattr(args[0], "__class__"):
                cache_key = f"{args[0].__class__.__name__}.{func.__name__}"
            else:
                cache_key = func.__name__

            # 为每个缓存键创建一个锁
            if cache_key not in locks:
                locks[cache_key] = asyncio.Lock()

            # 检查缓存，如果有效则直接返回
            if cache_key in cache:
                value, timestamp = cache[cache_key]
                if current_time - timestamp < expiration:
                    return value

            # 获取锁以确保并发安全
            async with locks[cache_key]:
                # 双重检查，避免等待锁期间其他协程已经更新了缓存
                if cache_key in cache:
                    value, timestamp = cache[cache_key]
                    if current_time - timestamp < expiration:
                        return value

                # 执行原始函数
                value = await func(*args)
                if condition(value):
                    cache[cache_key] = (value, current_time)
                return value

        return wrapper

    return decorator


@timed_async_cache(86400)
async def get_public_ip(host="127.127.127.127"):
    # 尝试从 kurobbs 获取 IP 地址
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://event.kurobbs.com/event/ip", timeout=4)
            ip = r.text
            return ip
    except Exception:
        pass

    # 尝试从 ipify 获取 IP 地址
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.ipify.org/?format=json", timeout=4)
            ip = r.json()["ip"]
            return ip
    except Exception:
        pass

    # 尝试从 httpbin.org 获取 IP 地址
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://httpbin.org/ip", timeout=4)
            ip = r.json()["origin"]
            return ip
    except Exception:
        pass

    return host


def get_datetime(tz: ZoneInfo = TZ):
    return datetime.now(tz)


def get_today_date():
    today = get_datetime()
    return today.strftime("%Y-%m-%d")


def get_yesterday_date():
    yesterday = get_datetime() - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def get_two_days_ago_date():
    two_days_ago = get_datetime() - timedelta(days=2)
    return two_days_ago.strftime("%Y-%m-%d")


async def get_using_id(ev: Event) -> str:
    from ..dna_config.dna_config import DNAConfig
    from ..utils.database.models import DNAPrivacy, DNAGroupPrivacy

    # 没有 @ 目标
    if not ev.at:
        return ev.user_id

    # 用户AT自己，查询自己的数据，不受偷窥权限限制
    if ev.at == ev.user_id:
        return ev.user_id

    # 功能未开启
    allow_config = DNAConfig.get_config("AllowAtQuery")
    if not allow_config or not allow_config.data:
        return ev.user_id

    # 检查群是否有强制隐私设置（优先级最高）
    if ev.group_id:
        group_privacy = await DNAGroupPrivacy.check_group_force_privacy(ev.group_id, ev.bot_id)
        if group_privacy is not None:
            # 群有强制设置
            if not group_privacy:
                # 强制全体防偷窥，不允许查询他人
                return ev.user_id
            # 强制全体开偷窥，允许查询
            return ev.at

    # 检查被@用户的隐私设置
    privacy = await DNAPrivacy.get_privacy_setting(ev.at, ev.bot_id)
    if privacy and not privacy.allow_peek:
        return ev.user_id
    return ev.at


async def is_uid_hidden(user_id: str, bot_id: str, group_id: Optional[str] = None) -> bool:
    """检查指定用户的 UID 是否应该被隐藏

    优先级：
    1. 群级强制设置（如果存在）
    2. 用户个人设置

    Args:
        user_id: 用户ID
        bot_id: Bot ID
        group_id: 群组ID（可选）

    Returns:
        bool: True 表示 UID 应该被隐藏，False 表示可以显示
    """
    from ..utils.database.models import DNAPrivacy, DNAGroupPrivacy

    # 优先检查群级强制设置
    if group_id:
        group_force_hidden = await DNAGroupPrivacy.check_uid_hidden(group_id, bot_id)
        if group_force_hidden is not None:
            return group_force_hidden

    # 检查用户个人设置
    return await DNAPrivacy.is_uid_hidden(user_id, bot_id)


# 预编译UID脱敏正则表达式
_UID_MASK_PATTERNS = [
    (re.compile(r"UID:\s*\[?\d+\]?", re.IGNORECASE), "UID: ***"),
    (re.compile(r"二重螺旋uid:\s*\d+", re.IGNORECASE), "二重螺旋uid: ***"),
]


def mask_uid_in_text(text: str) -> str:
    """对文本中的UID进行脱敏处理

    匹配模式：
    - UID: [数字] 或 UID:[数字]
    - uid: [数字] 或 uid:[数字]
    - 二重螺旋uid: [数字]

    Args:
        text: 原始文本

    Returns:
        str: 脱敏后的文本
    """
    for pattern, replacement in _UID_MASK_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
