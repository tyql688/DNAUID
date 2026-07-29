from __future__ import annotations

from dataclasses import dataclass

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils import dna_api
from ..utils.utils import mask_uid_in_text
from ..utils.api.auth import (
    LoginChannel,
    LoginCredentials,
    create_device_code,
)
from ..utils.api.model import (
    DNALoginRes,
    DNARoleListRes,
    DNARoleForToolRes,
)
from ..utils.database.models import DNABind, DNAUser
from ..utils.constants.constants import DNA_GAME_ID

complete_error_msg = "您尚未注册二重螺旋账号，请先在【皎皎角】进行角色绑定"
role_error_msg = "未找到二重螺旋角色，请在皎皎角注册账号后重新登录"


@dataclass(frozen=True, slots=True, kw_only=True)
class _RoleToBind:
    uid: str
    name: str | None
    is_default: bool


def _normalize_optional(value: str | None) -> str:
    if value is None:
        return ""
    return value


def _credential_values(credentials: LoginCredentials) -> dict[str, str]:
    if credentials.channel is LoginChannel.APP:
        return {
            "cookie": credentials.token,
            "status": "",
            "dev_code": credentials.dev_code,
            "d_num": credentials.d_num,
            "refresh_token": credentials.refresh_token,
        }
    return {
        "web_token": credentials.token,
        "web_status": "",
        "web_dev_code": credentials.dev_code,
        "web_d_num": credentials.d_num,
        "web_refresh_token": credentials.refresh_token,
    }


class DNALoginService:
    def __init__(self, bot: Bot, ev: Event) -> None:
        self.bot = bot
        self.ev = ev

    async def login(
        self,
        *,
        channel: LoginChannel,
        mobile: str,
        code: str,
        dev_code: str | None = None,
    ) -> str:
        if dev_code is None or dev_code == "":
            dev_code = create_device_code(channel)

        if channel is LoginChannel.APP:
            result = await dna_api.login_app(mobile, code, dev_code)
        else:
            result = await dna_api.login_web(mobile, code, dev_code)
        if not result.is_success:
            return result.throw_msg()

        login_response = DNALoginRes.model_validate(result.data)
        if login_response.isComplete == 0:
            return complete_error_msg

        credentials = LoginCredentials(
            channel=channel,
            token=login_response.token.strip(),
            dev_code=dev_code,
            refresh_token=login_response.refreshToken,
            d_num=_normalize_optional(login_response.dNum),
        )
        return await self.login_with_credentials(credentials)

    async def dna_login_by_token(
        self,
        token: str,
        dev_code: str | None = None,
        refresh_token: str | None = "",
        d_num: str | None = "",
    ) -> str:
        token = token.strip()
        if token == "":
            return "token不能为空"
        if dev_code is None or dev_code == "":
            dev_code = create_device_code(LoginChannel.APP)
        normalized_refresh_token = _normalize_optional(refresh_token)
        normalized_d_num = _normalize_optional(d_num)

        app_credentials = LoginCredentials(
            channel=LoginChannel.APP,
            token=token,
            dev_code=dev_code,
            refresh_token=normalized_refresh_token,
            d_num=normalized_d_num,
        )
        app_roles = await self._get_roles(app_credentials)
        if not isinstance(app_roles, str):
            return await self._complete_login(app_credentials, app_roles)

        web_credentials = LoginCredentials(
            channel=LoginChannel.WEB,
            token=token,
            dev_code=create_device_code(LoginChannel.WEB),
            refresh_token=normalized_refresh_token,
            d_num=normalized_d_num,
        )
        web_roles = await self._get_roles(web_credentials)
        if isinstance(web_roles, str):
            return "token无效或已过期"
        return await self._complete_login(web_credentials, web_roles)

    async def login_with_credentials(
        self,
        credentials: LoginCredentials,
    ) -> str:
        roles_to_bind = await self._get_roles(credentials)
        if isinstance(roles_to_bind, str):
            return roles_to_bind
        return await self._complete_login(credentials, roles_to_bind)

    async def _complete_login(
        self,
        credentials: LoginCredentials,
        roles_to_bind: list[_RoleToBind],
    ) -> str:
        if not roles_to_bind:
            return complete_error_msg

        role_ids_msg: list[dict[str, str]] = []
        for role in roles_to_bind:
            await self._save_credentials(role.uid, credentials)
            await self._bind_uid(role)

            role_name = role.name
            if role_name is None:
                role_name = "未命名角色"
            message_role = {"name": role_name, "uid": role.uid}
            if role.is_default:
                role_ids_msg.insert(0, message_role)
            else:
                role_ids_msg.append(message_role)

        message = ["登录成功, 已为您绑定以下角色:"]
        for role in role_ids_msg:
            message.append(f"- 名字: {role['name']}")
        if credentials.channel is LoginChannel.WEB:
            message.append("Web 登录暂不支持签到、体力和周报")
        return "\n".join(message)

    async def _get_roles(
        self,
        credentials: LoginCredentials,
    ) -> list[_RoleToBind] | str:
        if credentials.channel is LoginChannel.WEB:
            role_response = await dna_api.get_web_default_role(
                credentials.token,
                credentials.dev_code,
            )
            if not role_response.is_success:
                return role_response.throw_msg()
            if not role_response.data:
                return role_error_msg

            role_for_tool = DNARoleForToolRes.model_validate(
                role_response.data,
            )
            role_show = role_for_tool.roleInfo.roleShow
            return [
                _RoleToBind(
                    uid=role_show.roleId,
                    name=role_show.roleName,
                    is_default=True,
                )
            ]

        role_list_response = await dna_api.get_app_role_list(
            credentials.token,
            credentials.dev_code,
        )
        if not role_list_response.is_success:
            return role_list_response.throw_msg()
        if not role_list_response.data:
            return role_error_msg

        role_list = DNARoleListRes.model_validate(role_list_response.data)
        roles_to_bind: list[_RoleToBind] = []
        for role in role_list.roles:
            if role.gameId != DNA_GAME_ID:
                continue
            for show_vo in role.showVoList:
                roles_to_bind.append(
                    _RoleToBind(
                        uid=show_vo.roleId,
                        name=show_vo.roleName,
                        is_default=show_vo.isDefault == 1,
                    )
                )
        return roles_to_bind

    async def _save_credentials(
        self,
        uid: str,
        credentials: LoginCredentials,
    ) -> None:
        user_id = self.ev.user_id
        bot_id = self.ev.bot_id
        values = _credential_values(credentials)
        user = await DNAUser.select_dna_user(uid, user_id, bot_id)
        if user is None:
            await DNAUser.insert_data(
                user_id=user_id,
                bot_id=bot_id,
                uid=uid,
                **values,
            )
            return

        await DNAUser.update_data_by_data(
            select_data={
                "user_id": user_id,
                "bot_id": bot_id,
                "uid": uid,
            },
            update_data=values,
        )

    async def _bind_uid(self, role: _RoleToBind) -> None:
        user_id = self.ev.user_id
        bot_id = self.ev.bot_id
        result = await DNABind.insert_uid(
            user_id,
            bot_id,
            role.uid,
            self.ev.group_id,
            lenth_limit=13,
        )
        if result == 0 or (result == -2 and role.is_default):
            await DNABind.switch_uid_by_game(user_id, bot_id, role.uid)

    async def get_cookie(self) -> str:
        from ..utils.utils import is_uid_hidden

        is_uid_hidden_enabled = await is_uid_hidden(
            self.ev.user_id,
            self.ev.bot_id,
            self.ev.group_id,
        )
        dna_users = await DNAUser.select_dna_users(
            self.ev.user_id,
            self.ev.bot_id,
        )
        if not dna_users:
            return "当前并未登录"

        message: list[str] = []
        seen_app_tokens: set[str] = set()
        seen_web_tokens: set[str] = set()
        for raw_user in dna_users:
            if raw_user.cookie != "" and raw_user.cookie not in seen_app_tokens:
                dna_user = await dna_api.check_cookie(raw_user)
                if dna_user is not None and dna_user.cookie not in seen_app_tokens:
                    seen_app_tokens.add(dna_user.cookie)
                    message.extend(
                        (
                            f"二重螺旋UID: {dna_user.uid}",
                            "App token:",
                            dna_user.cookie,
                            "--------------------------------",
                        )
                    )

            if raw_user.web_token != "" and raw_user.web_status != "无效" and raw_user.web_token not in seen_web_tokens:
                seen_web_tokens.add(raw_user.web_token)
                message.extend(
                    (
                        f"二重螺旋UID: {raw_user.uid}",
                        "Web token:",
                        raw_user.web_token,
                        "--------------------------------",
                    )
                )

        if not message:
            return "未找到可用的二重螺旋 token"

        result = "\n".join(message)
        if is_uid_hidden_enabled:
            result = mask_uid_in_text(result)
        return result
