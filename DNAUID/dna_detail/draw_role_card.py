from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from .loadout import (
    WeaponNotFoundError,
    WeaponNotUnlockedError,
    WeaponSlotConflictError,
    resolve_weapon_loadout,
)
from .role_card import grade_badge, level_badge, render_role_card
from ..utils.image import COLOR_WHITE, get_attr_img, get_avatar_title_img
from ..utils.utils import get_using_id, is_uid_hidden, is_peek_blocked
from ..utils.dna_api import dna_api
from ..utils.dob.pack import source_line, ensure_data_ready
from ..utils.api.model import (
    RoleDetail,
    WeaponDetail,
    RoleInsForTool,
    DNARoleDetailRes,
    DNARoleForToolRes,
    DNAWeaponDetailRes,
)
from ..utils.dob.build import WeaponSlot, DobBuildError, build_engine
from ..utils.dob.panel import compute_panel
from ..utils.msgs.notify import (
    dna_not_found,
    dna_uid_invalid,
    send_dna_notify,
    dna_not_unlocked,
    dna_peek_blocked,
    dna_token_invalid,
)
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..utils.original_image import cache_original_image
from ..utils.database.models import DNABind, DNAUser
from ..utils.fonts.dna_fonts import dna_font_30
from ..utils.master_char_const import MASTER_CHAR_NAME_BY_ID, is_master_char_id

TEXT_PATH = Path(__file__).parent / "texture2d"


async def _info_box(role: RoleDetail, char_name: str) -> Image.Image:
    box = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    with Image.open(TEXT_PATH / "point.png") as point:
        box.alpha_composite(point.convert("RGBA"), (10, 10))
    ImageDraw.Draw(box).text((50, 25), char_name, COLOR_WHITE, dna_font_30, "lm")
    element = await get_attr_img(role.charId, role.elementIcon)
    box.alpha_composite(element.resize((element.width // 2, element.height // 2)), (10, 40))
    box.alpha_composite(grade_badge(role.gradeLevel), (50, 60))
    box.alpha_composite(level_badge(role.level), (100, 60))
    return box


async def _load_weapon_detail(
    dna_user: DNAUser,
    weapon_id: int,
    weapon_eid: str,
) -> WeaponDetail | None:
    response = await dna_api.get_weapon_detail(
        dna_user,
        weapon_id,
        weapon_eid,
    )
    if not response.is_success:
        return None
    if response.data is None:
        raise RuntimeError(
            f"武器详情成功响应缺少 data: weapon_id={weapon_id}",
        )
    return DNAWeaponDetailRes.model_validate(response.data).weaponDetail


async def draw_role_card(
    bot: Bot,
    ev: Event,
    char_name: str,
    *,
    weapon_names: tuple[str, ...] = (),
) -> None:
    user_id = await get_using_id(ev)
    if is_peek_blocked(ev, user_id):
        await dna_peek_blocked(bot, ev)
        return
    uid = await DNABind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        await dna_uid_invalid(bot, ev)
        return

    dna_user = await dna_api.get_dna_user(uid, user_id, ev.bot_id)
    if not dna_user:
        await dna_token_invalid(bot, ev)
        return

    real_char_name = alias_to_char_name(char_name)
    if not real_char_name:
        await dna_not_found(bot, ev, f"角色别名【{char_name}】")
        return

    char_id = char_name_to_char_id(real_char_name)
    if not char_id:
        await dna_not_found(bot, ev, f"角色【{char_name}】的CharId")
        return
    char_name = real_char_name

    # on_core_start 只在后台检查更新，数据包未就绪时在这里等，先于官方请求失败得快
    dob_error = await ensure_data_ready()
    if dob_error is not None:
        await send_dna_notify(bot, ev, dob_error)
        return

    default_role = await dna_api.get_default_role_for_tool(dna_user)
    if not default_role.is_success:
        await dna_not_found(bot, ev, "角色列表信息")
        return

    default_role = DNARoleForToolRes.model_validate(default_role.data)
    role_show = default_role.roleInfo.roleShow

    try:
        weapon_loadout = resolve_weapon_loadout(
            role_show.closeWeapons,
            role_show.langRangeWeapons,
            weapon_names,
        )
    except WeaponNotFoundError as error:
        await dna_not_found(
            bot,
            ev,
            f"展柜武器【{error.weapon_name}】",
        )
        return
    except WeaponNotUnlockedError as error:
        await dna_not_unlocked(
            bot,
            ev,
            f"当前展柜武器【{error.weapon_name}】",
        )
        return
    except WeaponSlotConflictError as error:
        await send_dna_notify(
            bot,
            ev,
            f"不能同时携带两把{error.slot.value}武器",
        )
        return

    if is_master_char_id(char_id):
        role_char_simple: RoleInsForTool | None = next(
            (i for i in role_show.roleChars if is_master_char_id(i.charId)), None
        )
        if role_char_simple is not None:
            char_id = str(role_char_simple.charId)
            char_name = MASTER_CHAR_NAME_BY_ID.get(char_id, char_name)
    else:
        role_char_simple = next((i for i in role_show.roleChars if str(i.charId) == char_id), None)
    if not role_char_simple:
        await dna_not_found(bot, ev, f"展柜角色【{char_name}】")
        return

    if not role_char_simple.unLocked or not role_char_simple.charEid:
        await dna_not_unlocked(bot, ev, f"当前展柜角色【{char_name}】")
        return

    role_detail = await dna_api.get_role_detail(
        dna_user,
        char_id,
        role_char_simple.charEid,
    )
    if not role_detail.is_success:
        await dna_not_found(bot, ev, f"角色【{char_name}】详情")
        return

    role_detail = DNARoleDetailRes.model_validate(role_detail.data)
    role_detail = role_detail.charDetail

    selected = {WeaponSlot.MELEE: weapon_loadout.close_weapon, WeaponSlot.RANGED: weapon_loadout.ranged_weapon}
    requests = {slot: (weapon.weapon_id, weapon.weapon_eid) for slot, weapon in selected.items() if weapon is not None}
    if role_detail.conWeaponId is not None and role_detail.conWeaponEid is not None:
        requests[WeaponSlot.SKILL] = (role_detail.conWeaponId, role_detail.conWeaponEid)
    details = await asyncio.gather(*(_load_weapon_detail(dna_user, *ids) for ids in requests.values()))
    weapons: dict[WeaponSlot, WeaponDetail] = {}
    for slot, detail in zip(requests, details):
        if detail is not None:
            weapons[slot] = detail
            continue
        # 同律武器拿不到只是少画一节；用户指定的展柜武器拿不到要明确告知
        chosen = selected.get(slot)
        if chosen is not None:
            await dna_not_found(bot, ev, f"{slot.value}武器【{chosen.name}】详情")
            return

    try:
        build = build_engine(role_detail, weapons)
    except DobBuildError as error:
        await send_dna_notify(bot, ev, f"面板计算失败：{error}")
        return

    uid_hidden = await is_uid_hidden(user_id, ev.bot_id, ev.group_id)
    avatar_title = await get_avatar_title_img(
        ev,
        role_show.roleId,
        role_show.roleName,
        user_level=role_show.level,
        other_info=[(i.paramKey, i.paramValue) for i in role_show.params if i.paramKey in ("总活跃天数", "游戏时长")],
        avatar_user_id=user_id,
        uid_hidden=uid_hidden,
    )
    card, portrait_path = await render_role_card(
        build,
        compute_panel(build),
        info_box=await _info_box(role_detail, char_name),
        avatar_title=avatar_title,
        footer_line=source_line(),
        grade_level=role_detail.gradeLevel,
    )
    message_ids = await bot.send(await convert_img(card), wait_recall=True)
    logger.debug(f"[DNA Detail] role panel message_ids={message_ids}")
    cache_original_image(message_ids, portrait_path)
