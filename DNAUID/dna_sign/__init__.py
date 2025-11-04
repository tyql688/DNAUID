from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV

from .sign import manual_sign

sv_dna_sign = SV("dna签到", priority=1)


@sv_dna_sign.on_fullmatch(
    (
        "签到",
        "社区签到",
        "每日任务",
        "社区任务",
        "库街区签到",
        "sign",
    ),
    block=True,
)
async def rover_user_sign(bot: Bot, ev: Event):
    await manual_sign(bot, ev)
