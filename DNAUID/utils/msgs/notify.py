from gsuid_core.bot import Bot
from gsuid_core.models import Event

title = "[二重螺旋]\n"


async def send_dna_notify(bot: Bot, ev: Event, msg: str, need_at: bool = True):
    if need_at:
        at_sender = True if ev.group_id else False
    else:
        at_sender = False
    return await bot.send(f"{title} {msg}", at_sender=at_sender)


async def dna_login_fail(bot: Bot, ev: Event, need_at: bool = True):
    from ...dna_config.prefix import DNA_PREFIX

    msg = [
        "账号登录失败",
        f"请重新输入命令【{DNA_PREFIX}登录】进行登录",
    ]
    msg = "\n".join(msg)
    return await send_dna_notify(bot, ev, msg, need_at)


async def dna_login_timeout(bot: Bot, ev: Event, need_at: bool = True):
    msg = [
        "登录超时, 请重新登录",
    ]
    msg = "\n".join(msg)
    return await send_dna_notify(bot, ev, msg)


async def dna_code_login_fail(bot: Bot, ev: Event, need_at: bool = True):
    from ...dna_config.prefix import DNA_PREFIX

    msg = [
        "手机号+验证码登录失败",
        f"请重新输入命令【{DNA_PREFIX}登录 手机号,验证码】进行登录",
    ]
    msg = "\n".join(msg)
    return await send_dna_notify(bot, ev, msg, need_at)


async def dna_login_success(bot: Bot, ev: Event, need_at: bool = True):
    msg = [
        "登录成功",
    ]
    msg = "\n".join(msg)
    return await send_dna_notify(bot, ev, msg, need_at)
