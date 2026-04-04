import re

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils import dna_api
from ..utils.utils import is_uid_hidden
from .login_router import get_cookie, page_login
from ..utils.msgs.notify import (
    dna_login_fail,
    send_dna_notify,
    dna_bind_uid_result,
)
from ..dna_config.dna_config import DNAConfig
from ..utils.database.models import DNABind, DNAUser

sv_dna_login = SV("dna登录")
sv_dna_bind = SV("dna绑定")
sv_dna_get_ck = SV("dna获取ck", area="DIRECT")
sv_dna_logout = SV("dna退出登录")


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

    # if text.startswith("eyJh"):
    #     return await token_login(bot, ev, text)

    return await dna_login_fail(bot, ev)


@sv_dna_logout.on_fullmatch(("退出登录", "登出", "logout"), block=True)
async def send_dna_logout_msg(bot: Bot, ev: Event):
    uid = await DNABind.get_uid_by_game(ev.user_id, ev.bot_id)
    if not uid:
        await send_dna_notify(bot, ev, "当前并未登录")
        return
    else:
        await DNABind.delete_uid(ev.user_id, ev.bot_id, uid)

    dna_user = await dna_api.get_dna_user(uid, ev.user_id, ev.bot_id)
    if not dna_user:
        await send_dna_notify(bot, ev, "当前并未登录")
        return
    else:
        await DNAUser.delete_cookie(ev.user_id, ev.bot_id, uid)

    await send_dna_notify(bot, ev, "成功退出登录")


@sv_dna_bind.on_command(
    (
        "绑定",
        "切换",
        "删除全部UID",
        "删除全部uid",
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

        code = await DNABind.insert_uid(qid, ev.bot_id, uid, ev.group_id, lenth_limit=13)
        if code == 0 or code == -2:
            retcode = await DNABind.switch_uid_by_game(qid, ev.bot_id, uid)
        return await dna_bind_uid_result(bot, ev, uid, code)
    elif "切换" in ev.command:
        retcode = await DNABind.switch_uid_by_game(qid, ev.bot_id, uid)
        if retcode == 0:
            uid_list = await DNABind.get_uid_list_by_game(qid, ev.bot_id)
            if uid_list:
                return await dna_bind_uid_result(bot, ev, uid_list[0], 1)

        return await dna_bind_uid_result(bot, ev, uid, -5)
    elif "查看" in ev.command:
        # 检查 UID 是否应该被隐藏（优先群级设置，其次个人设置）
        uid_hidden = await is_uid_hidden(qid, ev.bot_id, ev.group_id)

        if uid_hidden:
            return await bot.send("您已开启UID隐藏，无法查看UID列表~")

        uid_list = await DNABind.get_uid_list_by_game(qid, ev.bot_id)
        if uid_list:
            uids = "\n".join(uid_list)

            return await dna_bind_uid_result(bot, ev, uids, 2)
        else:
            return await dna_bind_uid_result(bot, ev, uid, -5)
    elif "删除全部" in ev.command:
        retcode = await DNABind.delete_all_uid(
            user_id=qid,
            bot_id=ev.bot_id,
        )
        if retcode == 0:
            return await dna_bind_uid_result(bot, ev, code=3)
        else:
            return await dna_bind_uid_result(bot, ev, code=-5)
    else:
        if not uid:
            return await dna_bind_uid_result(bot, ev, uid, -6)
        data = await DNABind.delete_uid(qid, ev.bot_id, uid)
        if data == -1:
            return await dna_bind_uid_result(bot, ev, uid, -6)
        return await dna_bind_uid_result(bot, ev, uid, 4)


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
