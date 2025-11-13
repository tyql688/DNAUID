from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV, get_plugin_available_prefix

from ..utils.database.models import DNABind
from ..utils.msgs.notify import (
    dna_token_invalid,
    dna_uid_invalid,
    send_dna_notify,
)
from .set_config import set_config_func

sv_dna_config = SV("DNAUID配置")


DNA_PREFIX = get_plugin_available_prefix("DNAUID")


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
