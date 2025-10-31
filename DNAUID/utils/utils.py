import asyncio
import functools
import time
from collections import OrderedDict

import httpx


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
            r = await client.get(
                "https://event.kurobbs.com/event/ip", timeout=4
            )
            ip = r.text
            return ip
    except Exception:
        pass

    # 尝试从 ipify 获取 IP 地址
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.ipify.org/?format=json", timeout=4
            )
            ip = r.json()["ip"]
            return ip
    except:  # noqa:E722, B001
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
