from __future__ import annotations

import re

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from .service import DobFetchError, fetch_boards, bot_char_name, synthesize_build, fetch_char_builds
from .board_card import draw_board_card, draw_build_list_card
from .build_card import draw_build_card
from ..utils.dob.pack import DobPackError, sync, describe, check_update, ensure_data_ready
from ..utils.dob.build import DobBuildError
from ..dna_config.prefix import dna_prefix
from ..utils.name_convert import char_name_to_char_id
from ..utils.constants.constants import PATTERN

sv_dob_board = SV("dnaDOB榜单")
sv_dob_build = SV("dnaDOB构筑")
sv_dob_pack = SV("dna数据包")
sv_dob_pack_update = SV("dna数据包更新", pm=1)

BDID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
CHAR_BUILD_PATTERN = rf"^(?:DOB|dob)(?P<char>{PATTERN})构筑(?:[\s　]*(?P<idx>\d+))?$"
# 「法露茜构筑」与「法露茜面板」同形：未知角色必须放行（block=False），别吞其他插件的指令
BARE_BUILD_PATTERN = rf"^(?P<char>{PATTERN})构筑(?:[\s　]*(?P<idx>\d+))?$"


@sv_dob_board.on_fullmatch(("DOB榜单", "dob榜单"), block=True)
async def send_dob_board(bot: Bot, ev: Event) -> None:
    hint = await ensure_data_ready()
    if hint:
        await bot.send(hint)
        return
    try:
        boards = await fetch_boards()
    except DobFetchError as error:
        logger.warning(f"[DOB] 榜单获取失败: {error!r}")
        await bot.send("DOB 榜单获取失败，请稍后再试")
        return
    if not boards:
        await bot.send("DOB 暂无榜单")
        return
    await bot.send(await convert_img(await draw_board_card(boards)))


@sv_dob_build.on_prefix(("DOBBD", "dobbd", "DOB构筑", "dob构筑"), block=True)
async def send_dob_build(bot: Bot, ev: Event) -> None:
    bdid = ev.text.strip()
    if not BDID_PATTERN.match(bdid):
        prefix = dna_prefix()
        await bot.send(f"用法：{prefix}DOBBD <构筑ID>（如 {prefix}DOBBD Svmqw3LGoY）")
        return
    await _send_build_card(bot, ev, bdid)


@sv_dob_build.on_regex(CHAR_BUILD_PATTERN, block=True)
async def send_char_builds(bot: Bot, ev: Event) -> None:
    await _char_builds_flow(bot, ev, own_namespace=True)


@sv_dob_build.on_regex(BARE_BUILD_PATTERN, block=False)
async def send_char_builds_bare(bot: Bot, ev: Event) -> None:
    await _char_builds_flow(bot, ev, own_namespace=False)


async def _char_builds_flow(bot: Bot, ev: Event, *, own_namespace: bool) -> None:
    name = ev.regex_dict["char"].strip()
    found = char_name_to_char_id(name)
    if found is None:
        if own_namespace:
            await bot.send(f"未找到角色【{name}】")
        return
    hint = await ensure_data_ready()
    if hint:
        await bot.send(hint)
        return
    char_id = int(found)
    try:
        rows = await fetch_char_builds(char_id)
    except DobFetchError as error:
        logger.warning(f"[DOB] 角色 {char_id} 构筑列表获取失败: {error!r}")
        await bot.send("构筑列表获取失败，请稍后再试")
        return
    char_name = bot_char_name(char_id)
    if not rows:
        await bot.send(f"【{char_name}】暂无构筑")
        return
    # 序号是可选分组，没写时为 None
    idx_text = ev.regex_dict["idx"]
    if not idx_text:
        await bot.send(await convert_img(await draw_build_list_card(char_name, rows)))
        return
    idx = int(idx_text)
    if not 1 <= idx <= len(rows):
        await bot.send(f"序号范围 1~{len(rows)}，请重发「{dna_prefix()}DOB{name}构筑 序号」")
        return
    await _send_build_card(bot, ev, rows[idx - 1].bdid)


async def _send_build_card(bot: Bot, ev: Event, bdid: str) -> None:
    hint = await ensure_data_ready()
    if hint:
        await bot.send(hint)
        return
    try:
        card = await synthesize_build(bdid)
    except DobFetchError as error:
        logger.warning(f"[DOB] 构筑 {bdid} 获取失败: {error!r}")
        await bot.send("构筑获取失败，请稍后再试")
        return
    except DobBuildError as error:
        await bot.send(f"构筑计算失败：{error}")
        return
    if card is None:
        await bot.send(f"未找到构筑【{bdid}】")
        return
    await bot.send(await convert_img(await draw_build_card(card, ev)))


@sv_dob_pack_update.on_fullmatch(("更新数据包", "更新DOB数据包", "更新dob数据包"), block=True)
async def update_dob_pack(bot: Bot, ev: Event) -> None:
    await bot.send("开始拉取 DOB 数据包（dna-builder 数据源），请稍候…")
    try:
        _, message = await sync()
    except DobPackError as error:
        message = f"数据包更新失败：{error}"
    await bot.send(message)


@sv_dob_pack.on_fullmatch(("数据包状态", "DOB数据状态", "dob数据状态", "数据源状态"))
async def dob_pack_status(bot: Bot, ev: Event) -> None:
    status = describe()
    if status is None:
        await bot.send(f"DOB 数据包未加载，请联系 bot 主人发送「{dna_prefix()}更新数据包」")
        return
    await bot.send(f"DOB 数据包：{status}")


@scheduler.scheduled_job("interval", hours=1, id="dna_dob_auto_update", replace_existing=True)
async def dob_auto_update() -> None:
    await check_update("定时检查")
