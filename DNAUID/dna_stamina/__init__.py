from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.sv import SV

from .draw_stamina import draw_stamina_img

dna_stamina = SV("dna日常便签")


@dna_stamina.on_fullmatch(
    (
        "每日",
        "mr",
        "实时便笺",
        "便笺",
        "便签",
        "体力",
        "日常",
        "便签",
        "日常便签",
    )
)
async def send_daily_info_pic(bot: Bot, ev: Event):
    await draw_stamina_img(bot, ev)
