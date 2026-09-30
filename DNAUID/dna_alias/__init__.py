import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .alias_ops import (
    char_alias_list,
    action_char_alias,
    weapon_alias_list,
    action_weapon_alias,
    all_char_list_alias,
    all_weapon_list_alias,
)
from ..utils.name_convert import load_alias_data, refresh_name_convert
from ..utils.constants.constants import PATTERN

sv_alias = SV("dna别名", pm=0, priority=0)
sv_recover_alias = SV("dna别名恢复", pm=0)
sv_list_alias = SV("dna别名列表")
sv_all_list_alias = SV("dna角色/武器列表")


@sv_alias.on_regex(
    rf"^(?P<action>添加|删除)(?P<alias_type>角色|武器)?(?P<name>{PATTERN})别名(?P<new_alias>{PATTERN})$",
    block=True,
)
async def handle_add_alias(bot: Bot, ev: Event):
    action = ev.regex_dict.get("action", "")
    alias_type = ev.regex_dict.get("alias_type")
    is_weapon = alias_type == "武器"
    name = ev.regex_dict.get("name", "").strip()
    new_alias = ev.regex_dict.get("new_alias", "").strip()
    if not name or not new_alias:
        return await bot.send("名称或别名不能为空")

    if is_weapon:
        msg = await action_weapon_alias(action, name, new_alias)
    else:
        msg = await action_char_alias(action, name, new_alias)

    if "成功" in msg:
        await asyncio.to_thread(load_alias_data)
    await bot.send(msg)


@sv_list_alias.on_regex(rf"^(?P<alias_type>角色|武器)?(?P<name>{PATTERN})别名(列表)?$", block=True)
async def handle_list_alias(bot: Bot, ev: Event):
    alias_type = ev.regex_dict.get("alias_type")
    is_weapon = alias_type == "武器"
    name = ev.regex_dict.get("name")
    if not name:
        return await bot.send("名称不能为空")
    name = name.strip()

    if is_weapon:
        msg = await weapon_alias_list(name)
    else:
        msg = await char_alias_list(name)
    await bot.send(msg)


@sv_recover_alias.on_fullmatch(("恢复别名", "强制恢复别名"))
async def handle_recover_alias(bot: Bot, ev: Event):
    is_force = True if "强制" in ev.command else False
    success, msg = await refresh_name_convert(is_force=is_force)
    await bot.send(msg)


@sv_all_list_alias.on_fullmatch(("角色列表", "武器列表"))
async def handle_all_list_alias(bot: Bot, ev: Event):
    alias_type = ev.command
    if alias_type == "角色列表":
        msg = await all_char_list_alias()
    else:
        msg = await all_weapon_list_alias()
    await bot.send(msg)
