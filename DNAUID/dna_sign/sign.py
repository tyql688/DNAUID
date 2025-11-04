from typing import List

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.database.models import DNAUser
from ..utils.msgs.notify import send_dna_notify
from .sign_service import SignService, can_bbs_sign, can_sign

SIGN_STATUS = {
    True: "✅ 已完成",
    False: "❌ 未完成",
    "skip": "🚫 请勿重复签到",
}


async def manual_sign(bot: Bot, ev: Event):
    if not can_sign() and not can_bbs_sign():
        return await send_dna_notify(bot, ev, "签到功能未开启")

    dna_users: List[DNAUser] = await DNAUser.select_dna_users(ev.user_id, ev.bot_id)
    if not dna_users:
        return await send_dna_notify(bot, ev, "请检查登录有效性")

    expire_uids = []
    result_msgs = []
    for dna_user in dna_users:
        if not dna_user.cookie or dna_user.status == "无效":
            expire_uids.append(dna_user.uid)
            continue

        ss = SignService(dna_user.uid, dna_user.cookie, dna_user.dev_code)
        if await ss.check_status():
            result_msgs.append(ss.turn_msg())
            continue

        await ss.do_sign()
        await ss.do_bbs_sign()

        result_msgs.append(ss.turn_msg())

        await ss.save_sign_data()

    for uid in expire_uids:
        result_msgs.append(f"失效UID: {uid}")

    if result_msgs:
        await send_dna_notify(bot, ev, "\n".join(result_msgs))


async def auto_sign():
    pass
