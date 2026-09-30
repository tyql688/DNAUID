from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .set_config import set_config_func
from ..utils.msgs.notify import (
    dna_uid_invalid,
    send_dna_notify,
    dna_token_invalid,
)
from ..utils.database.models import DNABind

sv_dna_config = SV("DNAUID配置")


@sv_dna_config.on_prefix(("开启", "关闭"))
async def open_switch_func(bot: Bot, ev: Event):
    if ev.text != "自动签到":
        return

    uid = await DNABind.get_uid_by_game(ev.user_id, ev.bot_id)
    if not uid:
        return await dna_uid_invalid(bot, ev)

    from ..utils.dna_api import dna_api

    token = await dna_api.get_dna_user(uid, ev.user_id, ev.bot_id)
    if not token:
        return await dna_token_invalid(bot, ev)

    logger.info(f"[{ev.user_id}]尝试[{ev.command[0:2]}]了[{ev.text}]功能")

    im = await set_config_func(ev, uid)
    await send_dna_notify(bot, ev, im)
