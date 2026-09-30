from PIL import Image

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.help.utils import register_help

from .get_help import ICON, get_help
from ..dna_config.prefix import dna_prefix

sv_dna_help = SV("dna帮助")


@sv_dna_help.on_fullmatch("帮助")
async def send_help_img(bot: Bot, ev: Event):
    await bot.send_option(await get_help(ev.user_pm))


register_help("DNAUID", f"{dna_prefix()}帮助", Image.open(ICON))
