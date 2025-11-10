from gsuid_core.bot import Bot
from gsuid_core.models import Event

title = "[二重螺旋]\n"


async def send_dna_notify(bot: Bot, ev: Event, msg: str, need_at: bool = True):
    if need_at:
        at_sender = True if ev.group_id else False
    else:
        at_sender = False
    return await bot.send(f"{title}{msg}", at_sender=at_sender)


async def dna_uid_invalid(bot: Bot, ev: Event, need_at: bool = True):
    from ...dna_config.prefix import DNA_PREFIX

    msg = [
        "UID无效，请重新绑定",
        f"请重新输入命令【{DNA_PREFIX}绑定 UID】进行绑定",
    ]
    msg = "\n".join(msg)
    return await send_dna_notify(bot, ev, msg, need_at)


async def dna_token_invalid(bot: Bot, ev: Event, need_at: bool = True):
    msg = ["Token无效，请重新登录"]
    msg = "\n".join(msg)
    return await send_dna_notify(bot, ev, msg, need_at)


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


async def dna_bind_uid_result(
    bot: Bot, ev: Event, uid: str = "", code: int = 0, need_at: bool = True
):
    from ...dna_config.prefix import DNA_PREFIX

    code_map = {
        4: [
            f"UID: [{uid}]删除成功！",
        ],
        3: [
            "删除全部UID成功！",
        ],
        2: [
            f"绑定的UID列表为：\n{uid}",
        ],
        1: [
            f"UID: [{uid}]切换成功！",
        ],
        0: [
            f"UID: [{uid}]绑定成功！",
            f"当前仅支持查询部分信息，完整功能请使用【{DNA_PREFIX}登录】",
        ],
        -1: [
            f"UID: [{uid}]的位数不正确！",
            f"请重新输入命令【{DNA_PREFIX}绑定 UID】进行绑定",
        ],
        -2: [
            f"UID: [{uid}]已经绑定过了！",
            f"请重新输入命令【{DNA_PREFIX}绑定 UID】进行绑定",
        ],
        -3: [
            "你输入了错误的格式!",
            f"请重新输入命令【{DNA_PREFIX}绑定 UID】进行绑定",
        ],
        -4: [
            "绑定UID达到上限!",
        ],
        -5: [
            "尚未绑定任何UID!",
        ],
        -6: [
            "删除失败！",
            "该命令末尾需要跟正确的UID!",
            "例如【{DNA_PREFIX}删除123456】",
        ],
        -99: [
            "绑定失败",
            f"请重新输入命令【{DNA_PREFIX}绑定 UID】进行绑定",
        ],
    }
    if code not in code_map:
        raise ValueError(f"Invalid code: {code}")
    return await send_dna_notify(bot, ev, "\n".join(code_map[code]), need_at=need_at)
