from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .upload_card import (
    list_role_panel_imgs,
    upload_role_panel_img,
    compress_role_panel_imgs,
    delete_all_role_panel_imgs,
    delete_role_panel_img_by_id,
    delete_original_role_panel_img,
)
from ..utils.constants.constants import PATTERN

dna_role_panel_upload = SV("dna上传角色面板图", pm=0)
dna_role_panel_delete_original = SV("dna原图删除", pm=0)
dna_role_panel_delete = SV("dna删除角色面板图", pm=0)
dna_role_panel_list = SV("dna角色面板图列表", pm=0)
dna_role_panel_compress = SV("dna压缩角色面板图", pm=0)


@dna_role_panel_upload.on_regex(
    rf"^上传(?P<char_name>{PATTERN})面板图$",
    block=True,
)
async def upload_role_panel_card(bot: Bot, ev: Event):
    char_name = ev.regex_dict.get("char_name", "")
    await upload_role_panel_img(bot, ev, char_name)


@dna_role_panel_delete_original.on_fullmatch("原图删除", block=True)
async def delete_original_role_panel_card(bot: Bot, ev: Event):
    await delete_original_role_panel_img(bot, ev)


@dna_role_panel_delete.on_regex(
    rf"^删除(?P<char_name>{PATTERN})面板图(?P<image_id>\S+)$",
    block=True,
)
async def delete_role_panel_card_by_id(bot: Bot, ev: Event):
    char_name = ev.regex_dict.get("char_name", "")
    image_id = ev.regex_dict.get("image_id", "")
    await delete_role_panel_img_by_id(bot, ev, char_name, image_id)


@dna_role_panel_delete.on_regex(
    rf"^删除(?P<char_name>{PATTERN})全部面板图$",
    block=True,
)
async def delete_all_role_panel_card(bot: Bot, ev: Event):
    char_name = ev.regex_dict.get("char_name", "")
    await delete_all_role_panel_imgs(bot, ev, char_name)


@dna_role_panel_list.on_regex(
    rf"^(?P<char_name>{PATTERN})面板图列表$",
    block=True,
)
async def list_role_panel_card(bot: Bot, ev: Event):
    char_name = ev.regex_dict.get("char_name", "")
    await list_role_panel_imgs(bot, ev, char_name)


@dna_role_panel_compress.on_fullmatch("压缩面板图", block=True)
async def compress_role_panel_card(bot: Bot, ev: Event):
    await compress_role_panel_imgs(bot, ev)
