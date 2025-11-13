import re

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..dna_config.dna_config import DNAConfig
from ..utils.database.models import DNABind, DNAUser
from ..utils.msgs.notify import dna_bind_uid_result, dna_login_fail
from .login_router import get_cookie, page_login, token_login

sv_dna_login = SV("dna登录")
sv_dna_bind = SV("dna绑定")
sv_dna_get_ck = SV("dna获取ck", area="DIRECT")


@sv_dna_login.on_command(
    (
        "登录",
        "登陆",
        "登入",
        "登龙",
        "login",
    )
)
async def dna_login(bot: Bot, ev: Event):
    text = re.sub(r'["\n\t ]+', "", ev.text.strip())
    text = text.replace("，", ",")

    # 1.网页登录  -> dna登录
    # 2.手机+验证码登录 -> dna登录 手机号,验证码
    # 3.token登录 -> dna登录 token
    if text == "":
        return await page_login(bot, ev)

    if text.startswith("eyJh"):
        return await token_login(bot, ev, text)

    return await dna_login_fail(bot, ev)


@sv_dna_bind.on_command(
    (
        "绑定",
        "切换",
        "删除全部UID",
        "删除",
        "查看",
    ),
    block=True,
)
async def send_dna_bind_uid_msg(bot: Bot, ev: Event):
    uid = ev.text.strip().replace("uid", "").replace("UID", "")
    qid = ev.user_id

    if "绑定" in ev.command:
        if not uid:
            return await dna_bind_uid_result(bot, ev, uid, -3)
        uid_list = await DNABind.get_uid_list_by_game(qid, ev.bot_id)
        cookie_uid_list = await DNAUser.select_user_cookie_uids(qid)
        if uid_list and cookie_uid_list:
            difference_uid_list = set(uid_list).difference(set(cookie_uid_list))
            max_bind_num: int = DNAConfig.get_config("MaxBindNum").data
            if len(difference_uid_list) >= max_bind_num:
                return await dna_bind_uid_result(bot, ev, uid, -4)

        code = await DNABind.insert_uid(qid, ev.bot_id, uid, ev.group_id, lenth_limit=9)
        if code == 0 or code == -2:
            retcode = await DNABind.switch_uid_by_game(qid, ev.bot_id, uid)
        return await dna_bind_uid_result(bot, ev, uid, code)
    elif "切换" in ev.command:
        retcode = await DNABind.switch_uid_by_game(qid, ev.bot_id, uid)
        if retcode == 0:
            uid_list = await DNABind.get_uid_list_by_game(qid, ev.bot_id)
            if uid_list:
                return await dna_bind_uid_result(bot, ev, uid, 1)

        return await dna_bind_uid_result(bot, ev, uid, -5)
    elif "查看" in ev.command:
        uid_list = await DNABind.get_uid_list_by_game(qid, ev.bot_id)
        if uid_list:
            uids = "\n".join(uid_list)

            return await dna_bind_uid_result(bot, ev, uids, 2)
        else:
            return await dna_bind_uid_result(bot, ev, uid, -5)
    elif "删除全部" in ev.command:
        retcode = await DNABind.update_data(
            user_id=qid,
            bot_id=ev.bot_id,
            **{DNABind.get_gameid_name(None): None},
        )
        if retcode == 0:
            return await dna_bind_uid_result(bot, ev, code=3)
        else:
            return await dna_bind_uid_result(bot, ev, code=-5)
    else:
        if not uid:
            return await dna_bind_uid_result(bot, ev, uid, -6)
        data = await DNABind.delete_uid(qid, ev.bot_id, uid)
        return await dna_bind_uid_result(bot, ev, uid, data)


@sv_dna_get_ck.on_fullmatch(
    (
        "获取ck",
        "获取CK",
        "获取Token",
        "获取token",
        "获取TOKEN",
    ),
    block=True,
)
async def send_dna_get_ck_msg(bot: Bot, ev: Event):
    await bot.send(await get_cookie(bot, ev))
