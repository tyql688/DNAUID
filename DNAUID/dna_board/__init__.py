"""DOB 榜单/构筑：榜单一览、单构筑卡（BDID）、角色构筑列表与序号点选。"""

from __future__ import annotations

import re
import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from .service import char_name, char_id_of, fetch_boards, synthesize_build, fetch_char_builds
from ..dna_sdk import version as dob_version_of, ensure_data_ready
from .renderer import draw_board_image, draw_build_list_image
from .renderer_bd import draw_bd_role_card
from ..utils.constants.constants import PATTERN

sv_dob_board = SV("dnaDOB榜单")
sv_dob_build = SV("dnaDOB构筑")

BDID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
CHAR_BUILD_PATTERN = rf"^DOB(?P<char>{PATTERN})构筑(?:[\s　]*(?P<idx>\d+))?$"
# 裸体 parallel 于“XX面板”：dna法露茜构筑。未知角色必须静默放行（block=False），
# 不能吞别家插件的同形触发；DOB 命名空间是自家的，可 block 并提示。
BARE_BUILD_PATTERN = rf"^(?P<char>{PATTERN})构筑(?:[\s　]*(?P<idx>\d+))?$"


@sv_dob_board.on_fullmatch("DOB榜单", block=True)
async def send_dob_board(bot: Bot, ev: Event):
    try:
        boards = await asyncio.to_thread(fetch_boards)
    except Exception as e:
        logger.warning(f"[DOB Board] 榜单获取失败: {e}")
        await bot.send("DOB 榜单获取失败，请稍后再试")
        return
    if not boards:
        await bot.send("DOB 暂无榜单")
        return
    card = await draw_board_image(boards, dob_version_of())
    await bot.send(card)


@sv_dob_build.on_prefix(("DOBBD", "DOB构筑"), block=True)
async def send_dob_build(bot: Bot, ev: Event):
    bdid = (ev.text or "").strip()
    if not BDID_PATTERN.match(bdid):
        await bot.send("用法：DOBBD <构筑ID>（如 DOBBD Svmqw3LGoY）")
        return
    await _send_build_card(bot, ev, bdid)


@sv_dob_build.on_regex(CHAR_BUILD_PATTERN, block=True)
async def send_char_builds(bot: Bot, ev: Event):
    await _char_builds_flow(bot, ev, own_namespace=True)


@sv_dob_build.on_regex(BARE_BUILD_PATTERN, block=False)
async def send_char_builds_bare(bot: Bot, ev: Event):
    await _char_builds_flow(bot, ev, own_namespace=False)


async def _char_builds_flow(bot: Bot, ev: Event, *, own_namespace: bool):
    name = ((ev.regex_dict or {}).get("char") or "").strip()
    idx_text = (ev.regex_dict or {}).get("idx")
    char_id = char_id_of(name)
    if char_id is None:
        if own_namespace:
            await bot.send(f"未找到角色【{name}】")
        return
    try:
        rows = await asyncio.to_thread(fetch_char_builds, char_id)
    except Exception as e:
        logger.warning(f"[DOB Board] 角色构筑列表获取失败: {e}")
        await bot.send("构筑列表获取失败，请稍后再试")
        return
    if not rows:
        await bot.send(f"【{char_name(char_id)}】暂无构筑")
        return
    if idx_text is None:
        card = await draw_build_list_image(char_name(char_id), rows, dob_version_of())
        await bot.send(card)
        return
    idx = int(idx_text)
    if idx < 1 or idx > len(rows):
        await bot.send(f"序号范围 1~{len(rows)}，请重发「DOB{name}构筑 序号」")
        return
    await _send_build_card(bot, ev, rows[idx - 1]["bdid"])


async def _send_build_card(bot: Bot, ev: Event, bdid: str):
    hint = await ensure_data_ready()
    if hint:
        await bot.send(hint)
        return
    try:
        synth = await asyncio.to_thread(synthesize_build, bdid)
    except Exception as e:
        logger.warning(f"[DOB Board] 构筑 {bdid} 获取失败: {e}")
        await bot.send("构筑获取失败，请稍后再试")
        return
    if synth is None:
        await bot.send(f"未找到构筑【{bdid}】")
        return
    card = await draw_bd_role_card(synth, ev, dob_version_of())
    card = await convert_img(card)
    await bot.send(card)
