from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .upload_card import upload_role_panel_img
from ..utils.constants.constants import PATTERN

dna_role_panel_upload = SV("dna上传角色面板图", pm=0)


@dna_role_panel_upload.on_regex(
    rf"^上传(?P<char_name>{PATTERN})面板图$",
    block=True,
)
async def upload_role_panel_card(bot: Bot, ev: Event):
    char_name = ev.regex_dict.get("char_name", "")
    await upload_role_panel_img(bot, ev, char_name)
