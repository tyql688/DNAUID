import time
import asyncio
import functools
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import OrderedDict

import httpx

from gsuid_core.models import Event

from ..dna_config.dna_config import DNAConfig

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


def get_uid_by_config(ev: Event) -> str:
    """
    通过 “允许AT查询他人信息” 配置获取他人或自己的 UID
    """
    # 获取at的id
    at_id = ev.at
    # 如果有at且允许AT查询，则使用被at方的UID查询；否则使用自己的UID
    user_id = at_id if should_use_other_id(ev) else ev.user_id
    return user_id


def should_use_other_id(ev: Event) -> bool:
    """
    通过 “允许AT查询他人信息” 配置是否使用其它人的 UID
    """
    at_id = ev.at
    allow_at = DNAConfig.get_config("AllowAtQuery").data
    return bool(at_id and allow_at)
