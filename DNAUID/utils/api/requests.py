import asyncio
import json
import random
from typing import Any, Dict, List, Literal, Mapping, Optional, Union
from urllib.parse import urlencode

import aiohttp

from gsuid_core.logger import logger

from ..constants.constants import DNA_GAME_ID
from ..database.models import DNAUser
from ..utils import timed_async_cache
from .api import (
    ANN_LIST_URL,
    BBS_SIGN_URL,
    GAME_SIGN_URL,
    GET_POST_DETAIL_URL,
    GET_POST_LIST_URL,
    GET_RSA_PUBLIC_KEY_URL,
    GET_TASK_PROCESS_URL,
    HAVE_SIGN_IN_URL,
    LIKE_POST_URL,
    LOGIN_LOG_URL,
    LOGIN_URL,
    REPLY_POST_URL,
    ROLE_FOR_TOOL_URL,
    ROLE_LIST_URL,
    SHARE_POST_URL,
    SIGN_CALENDAR_URL,
)
from .request_util import DNAApiResp, RespCode, get_base_header, is_h5
from .sign import build_signature, get_dev_code, rsa_encrypt


class DNAApi:
    ssl_verify = True
    ann_list_data = []

    async def get_dna_user(
        self, uid: str, user_id: str, bot_id: str
    ) -> Optional[DNAUser]:
        dna_user = await DNAUser.select_dna_user(uid, user_id, bot_id)
        if not dna_user or not dna_user.cookie:
            return

        if dna_user.status == "无效":
            return

        login_log = await self.login_log(dna_user.cookie, dna_user.dev_code)
        if not login_log.success:
            await DNAUser.mark_cookie_invalid(uid, dna_user.cookie, "无效")
            return

        return dna_user

    async def get_random_dna_user(self) -> Optional[DNAUser]:
        dna_users = await DNAUser.get_dna_all_user()
        if not dna_users:
            return
        random.shuffle(dna_users)
        for dna_user in dna_users[:3]:
            login_log = await self.login_log(dna_user.cookie, dna_user.dev_code)
            if not login_log.success:
                await DNAUser.mark_cookie_invalid(dna_user.uid, dna_user.cookie, "无效")
                continue

            return dna_user
        return None

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

    async def login_log(self, token: str, dev_code: Optional[str] = None):
        headers = await get_base_header(dev_code=dev_code, token=token)
        return await self._dna_request(LOGIN_LOG_URL, "POST", headers)

    async def get_role_list(self, token: str, dev_code: str):
        headers = await get_base_header(dev_code=dev_code, token=token)
        return await self._dna_request(ROLE_LIST_URL, "POST", headers)

    async def get_default_role_for_tool(self, token: str, dev_code: str):
        headers = await get_base_header(dev_code=dev_code, token=token)
        data = {"type": 1}
        return await self._dna_request(ROLE_FOR_TOOL_URL, "POST", headers, data=data)

    async def have_sign_in(self, token: str, dev_code: Optional[str] = None):
        headers = await get_base_header(dev_code=dev_code, token=token)
        data = {"gameId": DNA_GAME_ID}
        return await self._dna_request(HAVE_SIGN_IN_URL, "POST", headers, data=data)

    async def sign_calendar(self, token: str, dev_code: Optional[str] = None):
        headers = await get_base_header(dev_code=dev_code, token=token)
        data = {"gameId": DNA_GAME_ID}
        return await self._dna_request(SIGN_CALENDAR_URL, "POST", headers, data=data)

    async def game_sign(
        self, token: str, day_award_id: int, period: int, dev_code: Optional[str] = None
    ):
        headers = await get_base_header(dev_code=dev_code, token=token)
        data = {
            "dayAwardId": day_award_id,
            "periodId": period,
            "signinType": 1,
        }
        return await self._dna_request(GAME_SIGN_URL, "POST", headers, data=data)

    async def bbs_sign(self, token: str, dev_code: Optional[str] = None):
        headers = await get_base_header(dev_code=dev_code, token=token)
        data = {"gameId": DNA_GAME_ID}
        return await self._dna_request(BBS_SIGN_URL, "POST", headers, data=data)

    async def get_task_process(self, token: str, dev_code: Optional[str] = None):
        """获取任务进度"""
        headers = await get_base_header(dev_code=dev_code, token=token)
        data = {"gameId": DNA_GAME_ID}
        try:
            return await self._dna_request(
                GET_TASK_PROCESS_URL, "POST", headers, data=data
            )
        except Exception as e:
            logger.exception("get_task_process", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    @timed_async_cache(
        3600,
        lambda x: x and isinstance(x, DNAApiResp) and x.is_success,
    )
    async def get_post_list(self, token: str, dev_code: Optional[str] = None):
        """获取帖子列表"""
        headers = await get_base_header(dev_code=dev_code, token=token)
        data = {
            "forumId": 46,  # 全部
            "gameId": DNA_GAME_ID,
            "pageIndex": 1,
            "pageSize": 20,
            "searchType": 1,  # 1:最新 2:热门
            "timeType": 0,
        }
        try:
            return await self._dna_request(
                GET_POST_LIST_URL, "POST", headers, data=data
            )
        except Exception as e:
            logger.exception("get_post_list", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    async def get_post_detail(
        self, post_id: str, token: Optional[str] = None, dev_code: Optional[str] = None
    ):
        """获取帖子详情"""
        header = await get_base_header(dev_code=dev_code, token=token)
        data = {"postId": post_id}
        try:
            return await self._dna_request(
                GET_POST_DETAIL_URL, "POST", header, data=data
            )
        except Exception as e:
            logger.exception("get_post_detail", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    async def do_like(
        self,
        token: str,
        post: Dict[str, Any],
        dev_code: Optional[str] = None,
    ):
        """点赞帖子"""
        header = await get_base_header(dev_code=dev_code, token=token)
        data = {
            "forumId": post.get("gameForumId"),
            "gameId": DNA_GAME_ID,
            "likeType": "1",
            "operateType": "1",
            "postCommentId": "",
            "postCommentReplyId": "",
            "postId": post.get("postId"),
            "postType": post.get("postType"),
            "toUserId": post.get("userId"),
        }
        try:
            return await self._dna_request(LIKE_POST_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception("do_like", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    async def do_share(self, token: str, dev_code: Optional[str] = None):
        """分享帖子任务"""
        header = await get_base_header(dev_code=dev_code, token=token)
        data = {"gameId": DNA_GAME_ID}
        try:
            return await self._dna_request(SHARE_POST_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception("do_share", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    async def do_reply(
        self,
        token: str,
        post: Dict[str, Any],
        content: str,
        dev_code: Optional[str] = None,
    ):
        """回复帖子"""
        content_json = json.dumps(
            [
                {
                    "content": content,
                    "contentType": "1",
                    "imgHeight": 0,
                    "imgWidth": 0,
                    "url": "",
                }
            ]
        )
        payload = {
            "postId": post.get("postId"),
            "forumId": post.get("gameForumId", 47),
            "postType": "1",
            "content": content_json,
        }

        si = build_signature(payload)
        payload.update(
            {
                "sign": si["s"],
                "timestamp": si["t"],
                "toUserId": post.get("userId"),
            }
        )
        data = urlencode(payload)

        rk = si["k"]
        pk = await self.get_rsa_public_key()
        ek = rsa_encrypt(rk, pk)
        header = await get_base_header(
            dev_code, token=token, is_need_origin=True, is_need_refer=True
        )

        if is_h5(header):
            header.update({"k": ek})
        else:
            header.update({"rk": rk, "key": ek})

        return await self._dna_request(REPLY_POST_URL, "POST", header, data=data)

    async def get_ann_list(self, is_cache: bool = False):
        if is_cache and self.ann_list_data:
            return self.ann_list_data

        headers = await get_base_header(dev_code=get_dev_code())
        data = {
            "otherUserId": "709542994134436647",
            "searchType": 1,
            "type": 2,
        }
        res = await self._dna_request(ANN_LIST_URL, "POST", headers, data=data)
        if res.is_success and isinstance(res.data, dict):
            self.ann_list_data = res.data.get("postList", [])
        return self.ann_list_data

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
