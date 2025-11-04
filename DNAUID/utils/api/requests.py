import asyncio
import json
from typing import Any, Dict, List, Literal, Mapping, Optional, Union
from urllib.parse import urlencode

import aiohttp

from gsuid_core.logger import logger

from ..constants.constants import DNA_GAME_ID
from ..utils import timed_async_cache
from .api import GET_RSA_PUBLIC_KEY_URL, LOGIN_URL, ROLE_LIST_URL
from .request_util import DNAApiResp, RespCode, get_base_header, is_h5
from .sign import build_signature, get_dev_code, rsa_encrypt


class DNAApi:
    ssl_verify = True

    @timed_async_cache(86400, lambda x: x and len(x) > 0)
    async def get_rsa_public_key(self) -> str:
        dev_code = get_dev_code()
        headers = await get_base_header(dev_code=dev_code)
        res = await self._dna_request(
            url=GET_RSA_PUBLIC_KEY_URL, method="POST", header=headers
        )

        rsa_pub = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDGpdbezK+eknQZQzPOjp8mr/dP+QHwk8CRkQh6C6qFnfLH3tiyl0pnt3dePuFDnM1PUXGhCkQ157ePJCQgkDU2+mimDmXh0oLFn9zuWSp+U8uLSLX3t3PpJ8TmNCROfUDWvzdbnShqg7JfDmnrOJz49qd234W84nrfTHbzdqeigQIDAQAB"
        if res.is_success and isinstance(res.data, dict):
            key = res.data.get("key")
            if key and isinstance(key, str):
                rsa_pub = key

        return rsa_pub

    async def login(self, mobile: Union[int, str], code: str, dev_code: str):
        payload = {"mobile": mobile, "code": code, "gameList": DNA_GAME_ID}
        si = build_signature(payload)
        payload.update({"sign": si["s"], "timestamp": si["t"]})
        data = urlencode(payload)

        rk = si["k"]
        pk = await self.get_rsa_public_key()
        ek = rsa_encrypt(rk, pk)
        header = await get_base_header(
            dev_code, is_need_origin=True, is_need_refer=True
        )

        if is_h5(header):
            header.update({"k": ek})
        else:
            header.update({"rk": rk, "key": ek})

        return await self._dna_request(LOGIN_URL, "POST", header, data=data)

    async def get_role_list(self, token: str, dev_code: Optional[str] = None):
        headers = await get_base_header(dev_code=dev_code)
        headers["token"] = token
        return await self._dna_request(ROLE_LIST_URL, "POST", headers)

    async def _dna_request(
        self,
        url: str,
        method: Literal["GET", "POST"] = "GET",
        header: Optional[Mapping[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, Dict[str, Any]]] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> DNAApiResp[Union[str, Dict[str, Any], List[Any]]]:
        if header is None:
            header = await get_base_header()

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method,
                        url,
                        headers=header,
                        params=params,
                        json=json_data,
                        data=data,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        try:
                            raw_res = await response.json()
                        except aiohttp.ContentTypeError:
                            _raw_data = await response.text()
                            raw_res = {
                                "code": RespCode.ERROR.value,
                                "data": _raw_data,
                            }
                        if isinstance(raw_res, dict):
                            try:
                                raw_res["data"] = json.loads(raw_res.get("data", ""))
                            except Exception:
                                pass

                        logger.debug(
                            f"[DNA] url:[{url}] params:[{params}] headers:[{header}] data:[{data}] raw_res:{raw_res}"
                        )
                        return DNAApiResp[Any].model_validate(raw_res)
            except Exception as e:
                logger.error(f"请求失败: {e}")
                await asyncio.sleep(retry_delay * (2**attempt))

        return DNAApiResp[Any].err("请求服务器失败，已达最大重试次数")
