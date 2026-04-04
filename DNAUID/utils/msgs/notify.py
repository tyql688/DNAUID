from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ...utils.utils import get_using_id, is_uid_hidden, mask_uid_in_text

title = "[二重螺旋]\n"


async def send_dna_notify(
    bot: Bot,
    ev: Event,
    msg: str,
    need_at: bool = True,
    is_uid_list_view: bool = False,
):
    """发送DNA通知消息

    Args:
        bot: Bot实例
        ev: Event实例
        msg: 消息内容
        need_at: 是否需要@发送者
        is_uid_list_view: 是否为查看UID列表的请求（此时不脱敏）
    """
    # 检查是否需要脱敏（除非是查看UID列表）
    if not is_uid_list_view and ev.group_id:
        uid_hidden = await is_uid_hidden(ev.user_id, ev.bot_id, ev.group_id)
        if uid_hidden:
            msg = _mask_uid_in_message(msg)
    elif not is_uid_list_view:
        # 私聊场景
        uid_hidden = await is_uid_hidden(ev.user_id, ev.bot_id)
        if uid_hidden:
            msg = _mask_uid_in_message(msg)

    if need_at:
        at_sender = True if ev.group_id else False
    else:
        at_sender = False
    return await bot.send(f"{title}{msg}", at_sender=at_sender)


def _mask_uid_in_message(msg: str) -> str:
    """对消息中的UID进行脱敏处理

    使用共享的 mask_uid_in_text 工具函数进行脱敏。
    注意：此函数不再匹配独立的纯数字UID，以避免误伤其他数字。
    """
    return mask_uid_in_text(msg)


async def dna_uid_invalid(bot: Bot, ev: Event, need_at: bool = True):
    from ...dna_config.prefix import DNA_PREFIX

    is_use_other_id = await get_using_id(ev) != ev.user_id
    msg = (
        [
            "UID无效，请重新绑定",
            f"请重新输入命令【{DNA_PREFIX}绑定 UID】进行绑定",
        ]
        if not is_use_other_id
        else ["该用户的 UID 无效", f"请让该用户输入命令【{DNA_PREFIX}绑定 UID】进行绑定"]
    )
    msg = "\n".join(msg)
    return await send_dna_notify(bot, ev, msg, need_at)


async def dna_token_invalid(bot: Bot, ev: Event, need_at: bool = True):
    msg = ["Token无效，请重新登录"]
    is_use_other_id = await get_using_id(ev) != ev.user_id
    msg = "\n".join(msg) if not is_use_other_id else "该用户的 Token 无效"
    return await send_dna_notify(bot, ev, msg, need_at)


async def dna_not_found(bot: Bot, ev: Event, resource_name: str, need_at: bool = True):
    return await send_dna_notify(bot, ev, f"{resource_name}未找到，请检查是否正确", need_at)


async def dna_peek_blocked(bot: Bot, ev: Event, need_at: bool = True):
    from ...dna_config.dna_config import DNAConfig

    allow_config = DNAConfig.get_config("AllowAtQuery")
    if not allow_config or not allow_config.data:
        msg = "AT查询功能未开启，无法查看他人游戏信息"
    else:
        msg = "该用户开启了防偷窥，无法查看其游戏信息"
    return await send_dna_notify(bot, ev, msg, need_at)


async def dna_not_unlocked(bot: Bot, ev: Event, resource_name: str, need_at: bool = True):
    return await send_dna_notify(bot, ev, f"{resource_name}暂未拥有，无法查看", need_at)


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


async def dna_bind_uid_result(bot: Bot, ev: Event, uid: str = "", code: int = 0, need_at: bool = True):
    from ...dna_config.prefix import DNA_PREFIX

    code_map = {
        4: [
            "UID删除成功！",
        ],
        3: [
            "删除全部UID成功！",
        ],
        2: [
            f"绑定的UID列表为：\n{uid}",
        ],
        1: [
            "UID切换成功！",
        ],
        0: [
            "UID绑定成功！",
            f"当前仅支持查询部分信息，完整功能请使用【{DNA_PREFIX}登录】",
        ],
        -1: [
            "UID的位数不正确！",
            f"请重新输入命令【{DNA_PREFIX}绑定 UID】进行绑定",
        ],
        -2: [
            "该UID已经绑定过了！",
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

    # 查看UID列表时不脱敏（code=2）
    is_uid_list_view = code == 2
    return await send_dna_notify(bot, ev, "\n".join(code_map[code]), need_at=need_at, is_uid_list_view=is_uid_list_view)
