from typing import Dict, Optional, Union

from ..utils import dna_api
from ..utils.api.model import DNACalendarSignResponse
from ..utils.database.models import DNASign, DNASignData, DNASignStatus

SIGN_STATUS = {
    True: "✅ 已完成",
    False: "❌ 未完成",
    "skip": "🚫 请勿重复签到",
    "forbidden": "🚫 签到功能已关闭",
    "failed": "❌ 签到失败",
}


def can_sign():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("DNASignin").data


def can_bbs_sign():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("DNABBSSignin").data


def can_bbs_task(task_name: str):
    from ..dna_config.dna_config import DNASignConfig

    return task_name in DNASignConfig.get_config("DNABBSLink").data


def get_check_config():
    from ..dna_config.dna_config import DNASignConfig

    return DNASignConfig.get_config("DNABBSLink").data


class SignService:
    def __init__(self, uid: str, token: str, dev_code: Optional[str] = None):
        self.uid = uid
        self.token = token
        self.dev_code = dev_code
        self.msg_temp: Dict[str, Union[bool, str]] = {}
        self.bbs_res: Dict[str, Union[bool, str]] = {}
        self._init_status()

    def _init_status(self):
        # 可以签到则返回 False，否则返回 "forbidden"
        self.msg_temp["signed"] = False if can_sign() else "forbidden"
        self.msg_temp["bbs_signed"] = False if can_bbs_sign() else "forbidden"

    def turn_msg(self):
        msg_list = []
        msg_list.append(f"UID: {self.uid}")
        if self.msg_temp["signed"] != "forbidden":
            msg_list.append(f"签到状态: {SIGN_STATUS[self.msg_temp['signed']]}")
        if self.msg_temp["bbs_signed"] != "forbidden":
            msg_list.append(f"社区签到状态: {SIGN_STATUS[self.msg_temp['bbs_signed']]}")
        msg_list.append("-----------------------------")
        return "\n".join(msg_list)

    async def save_sign_data(self):
        await DNASign.upsert_dna_sign(DNASignData.rebuild(self.dna_sign))

    async def check_status(self):
        """
        检查签到状态
        如果签到已完成（包括 True, "skip", "forbidden", "failed"），则返回 True
        如果签到未完成，则返回 False
        """
        dna_sign: Optional[DNASign] = await DNASign.get_sign_data(self.uid)
        if not dna_sign:
            self.dna_sign = DNASignData.build(self.uid)
            return False
        else:
            self.dna_sign = dna_sign

        if DNASignStatus.game_sign_complete(self.dna_sign):
            self.msg_temp["signed"] = "skip"

        if DNASignStatus.bbs_sign_complete(self.dna_sign, get_check_config()):
            self.msg_temp["bbs_signed"] = "skip"

        if self.msg_temp["signed"] and self.msg_temp["bbs_signed"]:
            return True

        # 二次检查
        res = await dna_api.have_sign_in(self.token, self.dev_code)
        have_game_sign = True  # game
        have_bbs_sign = True  # bbs
        if res.is_success and res.data and isinstance(res.data, dict):
            have_game_sign = res.data.get("haveRoleSignIn", False)
            have_bbs_sign = res.data.get("haveSignIn", False)

        if have_game_sign:
            self.msg_temp["signed"] = "skip"
            self.dna_sign.game_sign = DNASignStatus.GAME_SIGN
        if have_bbs_sign:
            self.dna_sign.bbs_sign = DNASignStatus.BBS_SIGN

        if self.msg_temp["signed"] and self.msg_temp["bbs_signed"]:
            return True
        return False

    async def token_check(self):
        res = await dna_api.login_log(self.token, self.dev_code)
        return res.is_success

    async def do_sign(self):
        if self.msg_temp["signed"]:
            return

        if self.dna_sign.game_sign == DNASignStatus.GAME_SIGN:
            return

        res = await dna_api.sign_calendar(self.token, self.dev_code)
        if not res.is_success:
            return True

        calendar_sign = DNACalendarSignResponse.model_validate(res.data)
        today_sign_award = calendar_sign.dayAward[calendar_sign.signinTime]

        # 开始签到
        res = await dna_api.game_sign(
            self.token, today_sign_award.id, today_sign_award.periodId, self.dev_code
        )
        if res.is_success:
            self.msg_temp["signed"] = True
            self.dna_sign.game_sign = DNASignStatus.GAME_SIGN
        elif res.code == 10000:
            # 已签到
            self.msg_temp["signed"] = "skip"
            self.dna_sign.game_sign = DNASignStatus.GAME_SIGN
        else:
            self.msg_temp["signed"] = "failed"

    async def do_bbs_sign(self):
        if self.msg_temp["bbs_signed"]:
            return

        # 开始社区签到
        await self._bbs_sign()
        await self._bbs_detail()
        await self._bbs_like()
        await self._bbs_share()
        await self._bbs_reply()

    async def _bbs_sign(self):
        if not can_bbs_task("bbs_sign"):
            return

        # 开始社区签到
        if self.dna_sign.bbs_sign == DNASignStatus.BBS_SIGN:
            return

        res = await dna_api.bbs_sign(self.token, self.dev_code)
        if res.is_success:
            self.bbs_res["sign"] = True
            self.dna_sign.bbs_sign = DNASignStatus.BBS_SIGN
        elif res.code == 10000:
            self.bbs_res["sign"] = "skip"
            self.dna_sign.bbs_sign = DNASignStatus.BBS_SIGN
        else:
            self.bbs_res["sign"] = "failed"

    async def _bbs_detail(self):
        if not can_bbs_task("bbs_detail"):
            return

    async def _bbs_like(self):
        if not can_bbs_task("bbs_like"):
            return

    async def _bbs_share(self):
        if not can_bbs_task("bbs_share"):
            return

    async def _bbs_reply(self):
        if not can_bbs_task("bbs_reply"):
            return
