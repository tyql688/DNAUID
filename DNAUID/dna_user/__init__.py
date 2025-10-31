import re

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.msgs.notify import dna_login_fail
from .page_login_router import page_login

sv_dna_login = SV("dna登录")


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
        return

    return await dna_login_fail(bot, ev)
