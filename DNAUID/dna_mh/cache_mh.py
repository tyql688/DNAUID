import asyncio

from ..utils.dna_api import dna_api
from ..utils.api.model import DNAMHRes, DNARoleForToolInstanceInfo

# 改进的缓存结构
cache = {
    "timestamp": 0,
    "result": None,
    "lock": asyncio.Lock(),
}


def get_cache_config():
    from ..dna_config.dna_config import DNAConfig

    return DNAConfig.get_config("MHCache").data


async def get_mh_result(
    timestamp: int,
    is_force: bool = False,
) -> list[DNARoleForToolInstanceInfo] | None:
    global cache

    config_cache_enabled = get_cache_config()

    # 如果is_force=True或缓存未启用，直接获取新数据
    if is_force or not config_cache_enabled:
        return await _fetch_and_update_cache(timestamp)

    async with cache["lock"]:
        if cache.get("result") is not None and cache.get("timestamp") == timestamp:
            return cache["result"]

        # 缓存无效，重新获取数据
        return await _fetch_and_update_cache(timestamp)


async def _fetch_and_update_cache(
    timestamp: int,
) -> list[DNARoleForToolInstanceInfo] | None:
    global cache

    res = await dna_api.get_mh()
    if not res.is_success:
        return

    mh_result = DNAMHRes.model_validate(res.data).instanceInfo
    if not mh_result:
        return

    cache["timestamp"] = timestamp
    cache["result"] = mh_result
    return mh_result
