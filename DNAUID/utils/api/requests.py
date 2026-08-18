import json
import random
import asyncio
import inspect
from typing import Any, Dict, List, Union, Literal, Mapping, TypeVar, Optional
from datetime import datetime

import aiohttp

from gsuid_core.logger import logger

from .api import (
    LOGIN_URL,
    ANN_LIST_URL,
    BBS_SIGN_URL,
    GAME_SIGN_URL,
    LIKE_POST_URL,
    LOGIN_LOG_URL,
    ROLE_LIST_URL,
    WIKI_LIST_URL,
    REPLY_POST_URL,
    SHARE_POST_URL,
    SHORT_NOTE_URL,
    ROLE_DETAIL_URL,
    WIKI_DETAIL_URL,
    GET_SMS_CODE_URL,
    HAVE_SIGN_IN_URL,
    ACTIVITY_LIST_URL,
    CALENDAR_LIST_URL,
    DAMAGE_CONFIG_URL,
    DAMAGE_WEAPON_URL,
    GET_POST_LIST_URL,
    REFRESH_TOKEN_URL,
    ROLE_FOR_TOOL_URL,
    SIGN_CALENDAR_URL,
    WEAPON_DETAIL_URL,
    WIKI_HOME_LIST_URL,
    GET_POST_DETAIL_URL,
    DAMAGE_CALCULATE_URL,
    GET_TASK_PROCESS_URL,
    DAMAGE_ENVIRONMENT_URL,
    GET_RSA_PUBLIC_KEY_URL,
    ITEM_WEEKLY_REPORT_URL,
    get_local_proxy_url,
    get_need_proxy_func,
    get_no_need_proxy_func,
)
from .auth import (
    LoginChannel,
    DNACapability,
    get_token_user_id,
    get_channel_credentials,
    get_capability_credentials,
)
from .dnum import check_decrypt_dnum
from .sign import get_dev_code, get_signed_headers_and_body
from ..utils import timed_async_cache
from .sign_h5 import generate_headers_h5
from .sign_130 import generate_headers_130
from .damage_model import (
    BuildConfigData,
    WeaponCalculateData,
    CharacterCalculateData,
    WeaponCalculateRequest,
    EnvironmentCalculateData,
    CharacterCalculateRequest,
    EnvironmentCalculateRequest,
)
from .request_util import (
    RespCode,
    DNAApiResp,
    get_base_header,
    get_damage_header,
    get_web_login_header,
)
from ..database.models import DNAUser
from ..constants.constants import DNA_GAME_ID

_DamageDataT = TypeVar("_DamageDataT")


class DNAApi:
    ssl_verify = True
    ann_list_data = []
    _sessions: Dict[str, aiohttp.ClientSession] = {}
    _session_lock = asyncio.Lock()

    async def get_session(self, proxy: Optional[str] = None) -> aiohttp.ClientSession:
        # 使用代理 URL 作为 key，None 表示直连
        key = proxy or "no_proxy"

        # 检查是否已有可用的 session
        if key in self._sessions and not self._sessions[key].closed:
            return self._sessions[key]

        async with self._session_lock:
            # 双重检查，避免并发创建多个 session
            if key in self._sessions and not self._sessions[key].closed:
                return self._sessions[key]

            session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=self.ssl_verify),
            )
            self._sessions[key] = session
            return session

    async def get_dna_user(self, uid: str, user_id: str, bot_id: str) -> Optional[DNAUser]:
        dna_user = await DNAUser.select_dna_user(uid, user_id, bot_id)
        if dna_user is None:
            return None
        return await self._prepare_dna_user(dna_user)

    async def get_random_dna_user(self) -> Optional[DNAUser]:
        dna_users = await DNAUser.get_all_card_users()
        if not dna_users:
            return None
        random.shuffle(dna_users)
        for dna_user in dna_users[:3]:
            available_user = await self._prepare_dna_user(dna_user)
            if available_user is not None:
                return available_user
        return None

    async def _prepare_dna_user(
        self,
        dna_user: DNAUser,
    ) -> DNAUser | None:
        app_credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_QUERY,
        )
        if app_credentials is not None:
            checked_user = await self.check_cookie(dna_user)
            if checked_user is not None:
                return checked_user

        web_credentials = get_channel_credentials(
            dna_user,
            LoginChannel.WEB,
        )
        if web_credentials is not None:
            return dna_user
        return None

    async def check_cookie(self, dna_user: DNAUser) -> Optional[DNAUser]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_QUERY,
        )
        if credentials is None:
            return None

        dr = check_decrypt_dnum(credentials.d_num)
        logger.debug(f"[DNA登录] 检查 App 凭据 uid={dna_user.uid} dr={dr}")
        # if dr > 0:
        #     return dna_user

        if dr == 0 and credentials.refresh_token != "":
            res = await self.refresh_token(
                credentials.token,
                credentials.refresh_token,
                credentials.dev_code,
            )
            if res.success and res.data and isinstance(res.data, dict):
                dna_user.cookie = res.data["token"]
                dna_user.d_num = res.data["dNum"]
                dna_user.status = ""
                await DNAUser.update_data_by_data(
                    select_data={"user_id": dna_user.user_id, "bot_id": dna_user.bot_id, "uid": dna_user.uid},
                    update_data={
                        "status": "",
                        "cookie": dna_user.cookie,
                        "d_num": dna_user.d_num,
                    },
                )
                return dna_user

        login_log = await self.login_log(
            credentials.token,
            credentials.dev_code,
        )
        if not login_log.success:
            await DNAUser.mark_cookie_invalid(
                dna_user.uid,
                credentials.token,
                "无效",
            )
            dna_user.status = "无效"
            return None

        return dna_user

    @timed_async_cache(86400, lambda x: x and len(x) > 0)
    async def get_rsa_public_key(self) -> str:
        dev_code = get_dev_code()
        headers = await get_base_header(dev_code=dev_code)
        res = await self._dna_request(url=GET_RSA_PUBLIC_KEY_URL, method="POST", header=headers)

        rsa_pub = (
            "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDGpdbezK+eknQZQzPOjp8mr/dP+"
            "QHwk8CRkQh6C6qFnfLH3tiyl0pnt3dePuFDnM1PUXGhCkQ157ePJCQgkDU2+mimDmXh0oLFn9zuWSp+"
            "U8uLSLX3t3PpJ8TmNCROfUDWvzdbnShqg7JfDmnrOJz49qd234W84nrfTHbzdqeigQIDAQAB"
        )

        if res.is_success and isinstance(res.data, dict):
            key = res.data.get("key")
            if key and isinstance(key, str):
                rsa_pub = key

        return rsa_pub

    async def _get_web_signed_headers_and_body(
        self,
        payload: dict[str, Any],
        dev_code: str,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        headers = get_web_login_header(dev_code)
        rsa_pub = await self.get_rsa_public_key()
        return generate_headers_h5(headers, payload, rsa_pub)

    async def get_app_sms_code(
        self,
        mobile: str | int,
        v_json: str,
        dev_code: str,
    ) -> DNAApiResp[Any]:
        headers = await get_base_header(dev_code=dev_code)
        payload = {
            "isCaptcha": 1,
            "mobile": mobile,
            "vJson": v_json,
        }
        rsa_pub = await self.get_rsa_public_key()
        signed_headers, signed_payload = get_signed_headers_and_body(
            url=GET_SMS_CODE_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(
            GET_SMS_CODE_URL,
            "POST",
            signed_headers,
            data=signed_payload,
        )

    async def get_web_sms_code(
        self,
        mobile: str | int,
        v_json: str,
        dev_code: str,
    ) -> DNAApiResp[Any]:
        payload = {"mobile": mobile, "vJson": v_json}
        headers, signed_payload = await self._get_web_signed_headers_and_body(
            payload,
            dev_code,
        )
        return await self._dna_request(
            GET_SMS_CODE_URL,
            "POST",
            headers,
            data=signed_payload,
        )

    async def login_app(
        self,
        mobile: str | int,
        code: str,
        dev_code: str,
    ) -> DNAApiResp[Any]:
        headers = await get_base_header(dev_code)
        payload = {"code": code, "devCode": dev_code, "gameList": DNA_GAME_ID, "loginType": 1, "mobile": mobile}
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = get_signed_headers_and_body(
            url=LOGIN_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(LOGIN_URL, "POST", headers, data=payload)

    async def login_web(
        self,
        mobile: str | int,
        code: str,
        dev_code: str,
    ) -> DNAApiResp[Any]:
        payload = {
            "mobile": mobile,
            "code": code,
            "gameList": DNA_GAME_ID,
        }
        headers, signed_payload = await self._get_web_signed_headers_and_body(
            payload,
            dev_code,
        )
        return await self._dna_request(
            LOGIN_URL,
            "POST",
            headers,
            data=signed_payload,
        )

    async def refresh_token(self, token: str, refresh_token: str, dev_code: str):
        headers = await get_base_header(dev_code=dev_code, token=token)
        payload = {"refreshToken": refresh_token}
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = get_signed_headers_and_body(
            url=REFRESH_TOKEN_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(REFRESH_TOKEN_URL, "POST", headers, data=payload)

    @timed_async_cache(3600, lambda x: x and x.success)
    async def login_log(self, token: str, dev_code: Optional[str] = None):
        headers = await get_base_header(dev_code=dev_code, token=token)
        res = await self._dna_request(LOGIN_LOG_URL, "POST", headers)
        await asyncio.sleep(1 + random.uniform(0, 0.5))
        return res

    async def get_app_role_list(
        self,
        token: str,
        dev_code: str,
    ) -> DNAApiResp[Any]:
        headers = await get_base_header(dev_code=dev_code, token=token)
        payload = {}
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = get_signed_headers_and_body(
            url=ROLE_LIST_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(ROLE_LIST_URL, "POST", headers, data=payload)

    async def get_mh(self):
        dna_user = await self.get_random_dna_user()
        if not dna_user:
            return DNAApiResp[Any].err("获取DNA用户失败")

        return await self.get_default_role_for_tool(dna_user)

    async def get_default_role_for_tool(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[Any]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ROLE_CARD,
        )
        if credentials is None:
            return DNAApiResp[Any].err("当前账号没有可用的角色卡片凭据")
        if credentials.channel is LoginChannel.WEB:
            return await self.get_web_default_role(
                credentials.token,
                credentials.dev_code,
            )

        header = await get_base_header(
            credentials.dev_code,
            token=credentials.token,
        )
        payload = {"type": 1}
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = get_signed_headers_and_body(
            url=ROLE_FOR_TOOL_URL,
            header=header,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(ROLE_FOR_TOOL_URL, "POST", headers, data=payload)

    async def get_web_default_role(
        self,
        token: str,
        dev_code: str,
    ) -> DNAApiResp[Any]:
        user_id = get_token_user_id(token)
        if user_id is None:
            return DNAApiResp[Any].err("Web token 格式错误")

        headers = await get_base_header(dev_code, token=token)
        payload = {"otherUserId": user_id, "type": 2}
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = generate_headers_130(
            headers,
            payload,
            rsa_pub,
        )
        return await self._dna_request(
            ROLE_FOR_TOOL_URL,
            "POST",
            headers,
            data=payload,
        )

    async def _damage_request(
        self,
        dna_user: DNAUser,
        url: str,
        response_model: type[DNAApiResp[_DamageDataT]],
        payload: dict[str, Any] | None = None,
    ) -> DNAApiResp[_DamageDataT]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.DAMAGE_CALCULATION,
        )
        if credentials is None:
            return response_model.err("伤害计算需要 Web 登录")

        response = await self._dna_request(
            url,
            "POST",
            get_damage_header(credentials.token),
            json_data=payload,
        )
        return response_model.model_validate(response.model_dump())

    async def get_damage_config(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[BuildConfigData]:
        return await self._damage_request(
            dna_user,
            DAMAGE_CONFIG_URL,
            DNAApiResp[BuildConfigData],
        )

    async def calculate_damage(
        self,
        dna_user: DNAUser,
        request: CharacterCalculateRequest,
    ) -> DNAApiResp[CharacterCalculateData]:
        payload = request.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        return await self._damage_request(
            dna_user,
            DAMAGE_CALCULATE_URL,
            DNAApiResp[CharacterCalculateData],
            payload,
        )

    async def calculate_weapon(
        self,
        dna_user: DNAUser,
        request: WeaponCalculateRequest,
    ) -> DNAApiResp[WeaponCalculateData]:
        payload = request.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        return await self._damage_request(
            dna_user,
            DAMAGE_WEAPON_URL,
            DNAApiResp[WeaponCalculateData],
            payload,
        )

    async def calculate_environment(
        self,
        dna_user: DNAUser,
        request: EnvironmentCalculateRequest,
    ) -> DNAApiResp[EnvironmentCalculateData]:
        payload = request.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        return await self._damage_request(
            dna_user,
            DAMAGE_ENVIRONMENT_URL,
            DNAApiResp[EnvironmentCalculateData],
            payload,
        )

    async def get_role_detail(
        self,
        dna_user: DNAUser,
        char_id: str,
        char_eid: str,
    ) -> DNAApiResp[Any]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ROLE_CARD,
        )
        if credentials is None:
            return DNAApiResp[Any].err("当前账号没有可用的角色卡片凭据")

        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        data: dict[str, str | int] = {
            "charId": char_id,
            "charEid": char_eid,
            "type": 1,
        }
        if credentials.channel is LoginChannel.WEB:
            user_id = get_token_user_id(credentials.token)
            if user_id is None:
                return DNAApiResp[Any].err("Web token 格式错误")
            data.update(
                {
                    "type": 2,
                    "userId": user_id,
                    "otherUserId": user_id,
                }
            )
        return await self._dna_request(ROLE_DETAIL_URL, "POST", headers, data=data)

    async def get_weapon_detail(
        self,
        dna_user: DNAUser,
        weapon_id: int,
        weapon_eid: str,
    ) -> DNAApiResp[Any]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ROLE_CARD,
        )
        if credentials is None:
            return DNAApiResp[Any].err("当前账号没有可用的角色卡片凭据")

        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        data: dict[str, str | int] = {
            "weaponId": weapon_id,
            "weaponEid": weapon_eid,
            "type": 1,
        }
        if credentials.channel is LoginChannel.WEB:
            user_id = get_token_user_id(credentials.token)
            if user_id is None:
                return DNAApiResp[Any].err("Web token 格式错误")
            data.update(
                {
                    "type": 2,
                    "userId": user_id,
                    "otherUserId": user_id,
                }
            )
        return await self._dna_request(WEAPON_DETAIL_URL, "POST", headers, data=data)

    async def get_short_note_info(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[Any]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_QUERY,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        payload = {}
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = get_signed_headers_and_body(
            url=SHORT_NOTE_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(SHORT_NOTE_URL, "POST", headers)

    async def get_item_weekly_report(
        self,
        dna_user: DNAUser,
        week_type: int = 1,
    ) -> DNAApiResp[Any]:
        """获取周报（资源获取统计）

        Args:
            week_type: 1=本周, 2=上周
        """
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_QUERY,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        data = {"weekType": week_type}
        return await self._dna_request(ITEM_WEEKLY_REPORT_URL, "POST", headers, data=data)

    async def have_sign_in(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[Any]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_QUERY,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        data = {"gameId": DNA_GAME_ID}
        return await self._dna_request(HAVE_SIGN_IN_URL, "POST", headers, data=data)

    async def sign_calendar(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[Any]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_QUERY,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        data = {"gameId": DNA_GAME_ID}
        return await self._dna_request(SIGN_CALENDAR_URL, "POST", headers, data=data)

    async def game_sign(
        self,
        dna_user: DNAUser,
        day_award_id: int,
        period: int,
    ) -> DNAApiResp[Any]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_ACTION,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            credentials.dev_code,
            token=credentials.token,
        )
        payload = {"dayAwardId": day_award_id, "periodId": period, "signinType": 1}
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = get_signed_headers_and_body(
            url=GAME_SIGN_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(GAME_SIGN_URL, "POST", headers, data=payload)

    async def bbs_sign(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[Any]:
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_ACTION,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        payload = {"gameId": DNA_GAME_ID}
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = get_signed_headers_and_body(
            url=BBS_SIGN_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(BBS_SIGN_URL, "POST", headers, data=payload)

    async def get_task_process(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[Any]:
        """获取任务进度"""
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_QUERY,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        data = {"gameId": DNA_GAME_ID}
        try:
            return await self._dna_request(GET_TASK_PROCESS_URL, "POST", headers, data=data)
        except Exception as e:
            logger.exception("get_task_process", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    @timed_async_cache(
        3600,
        lambda x: x and isinstance(x, DNAApiResp) and x.is_success,
    )
    async def get_post_list(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[Any]:
        """获取帖子列表"""
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_QUERY,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        data = {
            "forumId": 46,  # 全部
            "gameId": DNA_GAME_ID,
            "pageIndex": 1,
            "pageSize": 20,
            "searchType": 1,  # 1:最新 2:热门
            "timeType": 0,
        }
        try:
            return await self._dna_request(GET_POST_LIST_URL, "POST", headers, data=data)
        except Exception as e:
            logger.exception("get_post_list", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    async def get_post_detail(
        self,
        post_id: str,
        dna_user: DNAUser | None = None,
    ) -> DNAApiResp[Any]:
        """获取帖子详情"""
        if dna_user is None:
            header = await get_base_header()
        else:
            credentials = get_capability_credentials(
                dna_user,
                DNACapability.ACCOUNT_QUERY,
            )
            if credentials is None:
                return DNAApiResp[Any].err("该功能需要 App 登录")
            header = await get_base_header(
                dev_code=credentials.dev_code,
                token=credentials.token,
            )
        data = {"postId": post_id}
        try:
            return await self._dna_request(GET_POST_DETAIL_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception("get_post_detail", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    async def do_like(
        self,
        dna_user: DNAUser,
        post: Dict[str, Any],
    ) -> DNAApiResp[Any]:
        """点赞帖子"""
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_ACTION,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        headers = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )

        payload = {
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
        rsa_pub = await self.get_rsa_public_key()
        headers, payload = get_signed_headers_and_body(
            url=LIKE_POST_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        try:
            return await self._dna_request(LIKE_POST_URL, "POST", headers, data=payload)
        except Exception as e:
            logger.exception("do_like", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    async def do_share(
        self,
        dna_user: DNAUser,
    ) -> DNAApiResp[Any]:
        """分享帖子任务"""
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_ACTION,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        header = await get_base_header(
            dev_code=credentials.dev_code,
            token=credentials.token,
        )
        data = {"gameId": DNA_GAME_ID}
        try:
            return await self._dna_request(SHARE_POST_URL, "POST", header, data=data)
        except Exception as e:
            logger.exception("do_share", e)
            return DNAApiResp[Any].err("请求皎皎角服务失败")

    async def do_reply(
        self,
        dna_user: DNAUser,
        post: Dict[str, Any],
        content: str,
    ) -> DNAApiResp[Any]:
        """回复帖子"""
        credentials = get_capability_credentials(
            dna_user,
            DNACapability.ACCOUNT_ACTION,
        )
        if credentials is None:
            return DNAApiResp[Any].err("该功能需要 App 登录")
        content_json = json.dumps([{"content": content, "contentType": "1"}])
        header = await get_base_header(
            credentials.dev_code,
            token=credentials.token,
        )
        rsa_pub = await self.get_rsa_public_key()
        payload = {
            "postId": post.get("postId"),
            "forumId": post.get("gameForumId", 47),
            "postType": "1",
            "content": content_json,
            "toUserId": post.get("userId"),
        }
        headers, payload = get_signed_headers_and_body(
            url=REPLY_POST_URL,
            header=header,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(REPLY_POST_URL, "POST", headers, data=payload)

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

    async def get_calendar_info(self):
        headers = await get_base_header(is_h5=True, is_need_origin=True, is_need_refer=True)
        data = {}
        res = await self._dna_request(CALENDAR_LIST_URL, "POST", headers, data=data)
        if res.is_success and isinstance(res.data, dict):
            return res.data.get("vos", [])
        return []

    async def get_wiki_home_list(self):
        headers = await get_base_header(is_h5=True, is_need_origin=True, is_need_refer=True)
        data = {}
        try:
            res = await self._dna_request(WIKI_HOME_LIST_URL, "POST", headers, data=data)
            if res.is_success and isinstance(res.data, dict):
                return res.data
            return None
        except Exception as e:
            logger.exception("get_wiki_home_list", e)
            return None

    async def get_wiki_list(
        self,
        wiki_type: int = 1,
        page_num: int = 1,
        page_size: int = 20,
        filter_ids: Optional[str] = None,
    ):
        """获取图鉴列表

        Args:
            wiki_type: 图鉴类型，1=角色图鉴, 2=武器图鉴, 3=魔之楔图鉴, 4=魔灵图鉴, etc.
            page_num: 页码
            page_size: 每页数量
            filter_ids: 筛选条件ID，多个用逗号分隔
        """
        headers = await get_base_header(is_h5=True, is_need_origin=True, is_need_refer=True)
        data: Dict[str, Any] = {
            "pageNum": page_num,
            "pageSize": page_size,
            "id": wiki_type,  # 使用 categorize ID 而非 WikiType 枚举值
        }
        if filter_ids:
            data["filterIds"] = filter_ids
        try:
            res = await self._dna_request(WIKI_LIST_URL, "POST", headers, data=data)
            return res
        except Exception as e:
            logger.exception("get_wiki_list", e)
            return DNAApiResp[Any].err("请求皎皎角Wiki服务失败")

    async def get_wiki_detail(self, wiki_id: str):
        """获取图鉴详情

        Args:
            wiki_id: 图鉴的wikiId
        """
        headers = await get_base_header(is_h5=True, is_need_origin=True, is_need_refer=True)
        data = {"id": wiki_id}
        try:
            res = await self._dna_request(WIKI_DETAIL_URL, "POST", headers, data=data)
            return res
        except Exception as e:
            logger.exception("get_wiki_detail", e)
            return DNAApiResp[Any].err("请求皎皎角Wiki详情失败")

    async def get_activity_info(self):
        now = datetime.now()
        headers = await get_base_header(dev_code=get_dev_code())
        rsa_pub = await self.get_rsa_public_key()
        payload = {
            "curTime": now.strftime("%Y-%m-%d %H:%M:%S"),  # 当前时间
            "endTime": "2026-04-05 23:59:59",
            "startTime": "2025-12-01 00:00:00",
        }
        headers, payload = get_signed_headers_and_body(
            url=ACTIVITY_LIST_URL,
            header=headers,
            data=payload,
            rsa_public_key=rsa_pub,
        )
        return await self._dna_request(ACTIVITY_LIST_URL, "POST", headers, data=payload)

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

        proxy_func = get_need_proxy_func()
        func = inspect.stack()[1].function
        if func in proxy_func or "all" in proxy_func:
            proxy_url = get_local_proxy_url()
        else:
            proxy_url = None

        if proxy_url and func in get_no_need_proxy_func():
            proxy_url = None

        is_proxy = proxy_url is not None
        session = await self.get_session(proxy=proxy_url)
        for attempt in range(max_retries):
            try:
                async with session.request(
                    method,
                    url,
                    headers=header,
                    params=params,
                    json=json_data,
                    data=data,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=30),
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
                        f"[DNA] url:[{url}] func:[{func}] "
                        f"is_proxy:[{is_proxy}] params:[{params}] "
                        f"headers:[{header}] json_data:[{json_data}] "
                        f"data:[{data}] "
                        f"raw_res:{raw_res}"
                    )

                    res = DNAApiResp[Any].model_validate(raw_res)
                    if res.code == 10100 and res.msg == "业务异常":
                        raise Exception(f"{url} 业务异常: {json.dumps(raw_res, ensure_ascii=False)}")
                    elif res.code == 200 and res.msg == "请求成功" and not res.data:
                        if (
                            url.endswith("/user/login/log")
                            or url.endswith("/user/getSmsCode")
                            or url.endswith("/encourage/level/shareTask")
                        ):
                            return res
                        raise Exception(f"{url} 请求成功，但数据为空: {json.dumps(raw_res, ensure_ascii=False)}")

                    return res
            except Exception as e:
                logger.warning("请求失败", e)
                if attempt < max_retries - 1:  # 最后一次重试不需要等待
                    await asyncio.sleep(retry_delay * (2**attempt))

        return DNAApiResp[Any].err("请求服务器失败，请稍后再试")
