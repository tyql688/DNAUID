import asyncio
from pathlib import Path
from typing import List, Optional

from ..utils import dna_api
from ..utils.api.model import DNARoleForToolInstanceInfo, DNARoleForToolRes

TEXT_PATH = Path(__file__).parent / "texture2d"

# 改进的缓存结构
cache = {
    "timestamp": 0,
    "result": None,
    "lock": asyncio.Lock(),
}


async def get_mh_result(timestamp: int) -> Optional[List[DNARoleForToolInstanceInfo]]:
    global cache

    if timestamp == cache["timestamp"]:
        return cache["result"]

    async with cache["lock"]:
        if timestamp == cache["timestamp"]:
            return cache["result"]

        dna_user = await dna_api.get_random_dna_user()
        if not dna_user:
            return

        res = await dna_api.get_default_role_for_tool(
            dna_user.cookie, dna_user.dev_code
        )
        if not res.is_success:
            return

        mh_result = DNARoleForToolRes.model_validate(res.data).instanceInfo
        if not mh_result:
            return

        cache["timestamp"] = timestamp
        cache["result"] = mh_result
        return mh_result
