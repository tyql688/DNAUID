import uuid
from typing import Optional

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils import dna_api
from ..utils.api.model import DNALoginRes, DNARoleListRes
from ..utils.constants.constants import DNA_GAME_ID
from ..utils.database.models import DNABind, DNAUser

complete_error_msg = "您尚未注册二重螺旋账号，请先在【皎皎角】进行角色绑定"
role_error_msg = "未找到二重螺旋角色，请在皎皎角注册账号后重新登录"


class DNALoginService:
    def __init__(self, bot: Bot, ev: Event):
        self.bot = bot
        self.ev = ev

    async def get_dev_code(self) -> str:
        return str(uuid.uuid4()).upper()

    async def dna_login(self, mobile: str, code: str, dev_code: Optional[str] = None):
        if not dev_code:
            dev_code = await self.get_dev_code()
        result = await dna_api.login(mobile, code, dev_code)
        if not result.is_success:
            return result.throw_msg()
        login_response = DNALoginRes.model_validate(result.data)

        if login_response.isComplete == 0:
            return complete_error_msg

        role_list_response = await dna_api.get_role_list(login_response.token, dev_code)
        if not role_list_response.is_success:
            return role_list_response.throw_msg()
        if not role_list_response.data:
            return role_error_msg
        role_list = DNARoleListRes.model_validate(role_list_response.data)

        ev = self.ev
        user_id = ev.user_id
        bot_id = ev.bot_id
        group_id = ev.group_id

        role_ids_msg = []
        for role in role_list.roles:
            if role.gameId != DNA_GAME_ID:
                continue
            for show_vo in role.showVoList:
                uid = show_vo.roleId

                user = await DNAUser.get_user_by_attr(user_id, bot_id, "uid", uid)

                if user:
                    await DNAUser.update_data_by_data(
                        select_data={"user_id": user_id, "bot_id": bot_id, "uid": uid},
                        update_data={
                            "cookie": login_response.token,
                            "status": "",
                            "dev_code": dev_code,
                        },
                    )
                else:
                    await DNAUser.insert_data(
                        user_id=user_id,
                        bot_id=bot_id,
                        cookie=login_response.token,
                        uid=uid,
                        status="",
                        dev_code=dev_code,
                    )

                res = await DNABind.insert_uid(
                    user_id, bot_id, uid, group_id, lenth_limit=13
                )
                if res == 0 or (res == -2 and show_vo.isDefault == 1):
                    await DNABind.switch_uid_by_game(user_id, bot_id, uid)

                msg = {"name": show_vo.roleName, "uid": uid}
                if show_vo.isDefault == 1:
                    role_ids_msg.insert(0, msg)
                else:
                    role_ids_msg.append(msg)

        if not role_ids_msg:
            return complete_error_msg

        msg = ["登录成功, 已为您绑定以下角色:"]
        for role in role_ids_msg:
            msg.append(f"- UID: [{role['uid']}] 名字: {role['name']}")
        return "\n".join(msg)
        return "\n".join(msg)
