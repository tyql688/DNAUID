from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils import dna_api
from .loadout import (
    WeaponNotFoundError,
    WeaponNotUnlockedError,
    WeaponSlotConflictError,
    resolve_weapon_loadout,
)
from ..utils.image import (
    COLOR_WHITE,
    COLOR_SALMON,
    COLOR_GOLDENROD,
    COLOR_FIRE_BRICK,
    COLOR_ORANGE_RED,
    get_div,
    add_footer,
    get_dna_bg,
    get_mod_img,
    get_attr_img,
    get_grade_img,
    get_paint_img,
    get_skill_img,
    get_smooth_drawer,
    get_role_panel_img,
    get_avatar_title_img,
)
from ..utils.utils import get_using_id, is_uid_hidden, is_peek_blocked
from .damage_service import RoleDamageBuild, calculate_role_damage
from .damage_renderer import draw_role_damage_section
from .weapon_renderer import draw_weapon_detail_section
from ..utils.api.model import (
    WeaponDetail,
    RoleInsForTool,
    DNARoleDetailRes,
    DNARoleForToolRes,
    DNAWeaponDetailRes,
)
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
from ..utils.fonts.dna_fonts import (
    dna_font_18,
    dna_font_24,
    dna_font_26,
    dna_font_30,
)
from ..utils.master_char_const import MASTER_CHAR_NAME_BY_ID, is_master_char_id

TEXT_PATH = Path(__file__).parent / "texture2d"
prop_info_bar1 = Image.open(TEXT_PATH / "prop_info_bar1.png")
prop_info_bar2 = Image.open(TEXT_PATH / "prop_info_bar2.png")
global_skill_bg = Image.open(TEXT_PATH / "skill_bg.png")
grade_lock_img = Image.open(TEXT_PATH / "grade_0.png")
grade_unlock_img = Image.open(TEXT_PATH / "grade_1.png")

attr_list = [
    ("atk", "攻击", "icon1.png"),
    ("maxHp", "生命", "icon10.png"),
    ("maxES", "护盾", "icon11.png"),
    ("defense", "防御", "icon9.png"),
    ("maxSp", "最大神志", "icon8.png"),
    ("skillIntensity", "技能威力", "icon7.png"),
    ("skillRange", "技能范围", "icon6.png"),
    ("skillSustain", "技能耐久", "icon5.png"),
    ("skillEfficiency", "技能效益", "icon4.png"),
    ("strongValue", "昂扬", "icon3.png"),
    ("enmityValue", "背水", "icon2.png"),
]


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

    con_weapon_detail: WeaponDetail | None = None
    if role_detail.conWeaponId is not None and role_detail.conWeaponEid is not None:
        con_weapon_detail = await _load_weapon_detail(
            dna_user,
            role_detail.conWeaponId,
            role_detail.conWeaponEid,
        )

    close_weapon_detail: WeaponDetail | None = None
    if weapon_loadout.close_weapon is not None:
        close_weapon_detail = await _load_weapon_detail(
            dna_user,
            weapon_loadout.close_weapon.weapon_id,
            weapon_loadout.close_weapon.weapon_eid,
        )
        if close_weapon_detail is None:
            await dna_not_found(
                bot,
                ev,
                f"近战武器【{weapon_loadout.close_weapon.name}】详情",
            )
            return

    ranged_weapon_detail: WeaponDetail | None = None
    if weapon_loadout.ranged_weapon is not None:
        ranged_weapon_detail = await _load_weapon_detail(
            dna_user,
            weapon_loadout.ranged_weapon.weapon_id,
            weapon_loadout.ranged_weapon.weapon_eid,
        )
        if ranged_weapon_detail is None:
            await dna_not_found(
                bot,
                ev,
                f"远程武器【{weapon_loadout.ranged_weapon.name}】详情",
            )
            return

    damage_build = RoleDamageBuild(
        role_detail=role_detail,
        con_weapon_detail=con_weapon_detail,
        close_weapon_detail=close_weapon_detail,
        lang_range_weapon_detail=ranged_weapon_detail,
    )
    damage_result = await calculate_role_damage(dna_user, damage_build)
    damage_section = draw_role_damage_section(damage_build, damage_result)
    weapon_sections: list[Image.Image] = []
    if con_weapon_detail is not None:
        weapon_sections.append(
            await draw_weapon_detail_section(
                con_weapon_detail,
                "同律武器",
            )
        )

    if close_weapon_detail is not None:
        weapon_sections.append(
            await draw_weapon_detail_section(
                close_weapon_detail,
                "近战武器",
            )
        )
    if ranged_weapon_detail is not None:
        weapon_sections.append(
            await draw_weapon_detail_section(
                ranged_weapon_detail,
                "远程武器",
            )
        )

    # 提前获取头像与分割线，用于计算总高度
    div_img = get_div()
    # 检查 UID 是否应该被隐藏
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
    avatar_title = avatar_title.resize((1000, 1000 * avatar_title.height // avatar_title.width))
    weapon_sections_height = sum(section.height for section in weapon_sections)
    total_h = (
        850
        + div_img.height
        + global_skill_bg.height
        + weapon_sections_height
        + div_img.height
        + damage_section.height
        + 40
        + avatar_title.height
        + 600
    )
    card = get_dna_bg(1000, total_h, "bg2")

    original_img_path: Path | None = None
    role_panel = get_role_panel_img(char_id)
    if role_panel is not None:
        original_img_path, role_panel_img = role_panel
        panel_size = (1000, 850)
        portrait_size = (600, 850)
        panel_fade = 72
        panel_img = Image.new("RGBA", panel_size)
        if role_panel_img.width >= role_panel_img.height:
            panel_img.alpha_composite(ImageOps.fit(role_panel_img, panel_size, method=Image.Resampling.LANCZOS))
        else:
            portrait_img = ImageOps.fit(role_panel_img, portrait_size, method=Image.Resampling.LANCZOS)
            panel_side_mask = Image.new("L", portrait_size, 255)
            panel_side_fade = Image.linear_gradient("L").rotate(270, expand=True).resize((panel_fade, portrait_size[1]))
            panel_side_mask.paste(panel_side_fade, (portrait_size[0] - panel_fade, 0))
            panel_img.alpha_composite(Image.composite(portrait_img, Image.new("RGBA", portrait_size), panel_side_mask))

        panel_mask = Image.new("L", panel_size, 255)
        panel_bottom_fade = ImageOps.invert(Image.linear_gradient("L")).resize((panel_size[0], panel_fade))
        panel_mask.paste(panel_bottom_fade, (0, panel_size[1] - panel_fade))
        panel_img = Image.composite(panel_img, Image.new("RGBA", panel_size), panel_mask)
        card.alpha_composite(panel_img, (0, 0))
    else:
        paint_img = await get_paint_img(char_id, role_detail.paint)
        paint_img = paint_img.resize((int(1320 * 0.8), int(1320 * 0.8)))
        card.alpha_composite(paint_img, (-280, -100))

    # 个人信息
    info_bg = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    info_bg_draw = ImageDraw.Draw(info_bg)
    # 名字
    point = Image.open(TEXT_PATH / "point.png")
    info_bg.alpha_composite(point, (10, 10))
    info_bg_draw.text((50, 25), char_name, COLOR_WHITE, dna_font_30, "lm")
    # 属性
    attr_img = await get_attr_img(char_id, role_detail.elementIcon)
    attr_img = attr_img.resize((attr_img.width // 2, attr_img.height // 2))
    info_bg.alpha_composite(attr_img, (10, 40))
    # 命座
    grade_img = get_grade_img(role_detail.gradeLevel)
    ellipse = Image.new("RGBA", (34, 35))
    get_smooth_drawer().rounded_rectangle((0, 0, 34, 35), fill=COLOR_FIRE_BRICK, radius=7, target=ellipse)
    ellipse.alpha_composite(grade_img, (0, 5))
    info_bg.alpha_composite(ellipse, (50, 60))
    # 等级
    ellipse = Image.new("RGBA", (80, 35))
    ellipse_draw = ImageDraw.Draw(ellipse)
    get_smooth_drawer().rounded_rectangle((0, 0, 80, 35), fill=COLOR_FIRE_BRICK, radius=7, target=ellipse)
    ellipse_draw.text((40, 17), f"Lv.{role_detail.level}", COLOR_WHITE, dna_font_26, "mm")
    info_bg.alpha_composite(ellipse, (100, 60))

    card.alpha_composite(info_bg, (550, 80))

    # 命座解锁：7 级满命画 7 格，其余按 6 格；首末位置固定，步长按格数均分
    grade_unlock_bg = Image.new("RGBA", (1000, 130), (0, 0, 0, 0))
    grade_total = 7 if role_detail.gradeLevel >= 7 else 6
    grade_step = 750 // (grade_total - 1)
    for i in range(1, grade_total + 1):
        grade_bg = grade_lock_img.copy() if i > role_detail.gradeLevel else grade_unlock_img.copy()
        grade_img = get_grade_img(i)
        grade_img = grade_img.resize((int(grade_img.width * 1.8), int(grade_img.height * 1.8)))
        grade_bg.alpha_composite(grade_img, (33, 37))
        grade_unlock_bg.alpha_composite(grade_bg, (100 + (i - 1) * grade_step, 0))

    grade_unlock_bg = grade_unlock_bg.resize((int(1000 * 0.5), int(130 * 0.5)))
    card.alpha_composite(grade_unlock_bg, (0, 750))

    # 属性
    attr_bg = Image.new("RGBA", (400, 583), (0, 0, 0, 128))
    for index, attrs in enumerate(attr_list):
        prop_info = prop_info_bar1.copy() if index % 2 == 0 else prop_info_bar2.copy()
        prop_info_draw = ImageDraw.Draw(prop_info)
        attr_value = f"{getattr(role_detail.attribute, attrs[0]) or ''}"

        icon = Image.open(TEXT_PATH / f"icons/{attrs[2]}")
        # icon
        prop_info.alpha_composite(icon, (0, 0))
        # 属性名
        prop_info_draw.text(
            (53, 25),
            attrs[1],
            COLOR_WHITE,
            font=dna_font_26,
            anchor="lm",
        )
        # 属性值
        prop_info_draw.text(
            (370, 25),
            (attr_value if "%" in attr_value or not attr_value.isdigit() else f"{int(attr_value):,}"),
            COLOR_WHITE,
            font=dna_font_26,
            anchor="rm",
        )
        attr_bg.alpha_composite(prop_info, (0, index * 53))

    card.alpha_composite(attr_bg, (550, 200))

    h_index = 850
    card.alpha_composite(div_img, (0, h_index))
    h_index += div_img.height

    # 技能
    for index, skill in enumerate(role_detail.skills[:3]):
        skill_bg = global_skill_bg.copy()
        skill_bg_draw = ImageDraw.Draw(skill_bg)

        skill_img = await get_skill_img(char_id, skill.skillName, skill.icon)
        skill_img = skill_img.resize((100, 100))
        skill_bg.alpha_composite(skill_img, (20, 30))

        # 技能名字
        if len(skill.skillName) <= 5:
            skill_bg_draw.text((120, 55), skill.skillName, COLOR_GOLDENROD, dna_font_24, "lm")
        else:
            skill_bg_draw.text(
                (120, 55),
                skill.skillName,
                COLOR_GOLDENROD,
                dna_font_18,
                "lm",
            )

        get_smooth_drawer().rounded_rectangle(
            (120, 80, 200, 110),
            10,
            COLOR_SALMON,
            target=skill_bg,
        )

        skill_bg_draw.text((160, 94), f"Lv.{skill.level}", COLOR_WHITE, dna_font_26, "mm")

        card.alpha_composite(skill_bg, (50 + index * 300, h_index))
    h_index += global_skill_bg.height

    for weapon_section in weapon_sections:
        card.alpha_composite(weapon_section, (0, h_index))
        h_index += weapon_section.height

    card.alpha_composite(div_img, (0, h_index))
    h_index += div_img.height

    # mod
    all_mod_bg = Image.new("RGBA", (1000, 500), (0, 0, 0, 0))
    # 左4
    left_list = [role_detail.modes[0], role_detail.modes[2], role_detail.modes[4], role_detail.modes[6]]
    for index, mod in enumerate(left_list):
        quality = mod.quality or 1
        mod_bg = Image.open(TEXT_PATH / f"mod/mod_left_{quality}.png")
        mod_bg_draw = ImageDraw.Draw(mod_bg)

        if mod.id != -1 and mod.name:
            mod_img = await get_mod_img(mod.id, mod.icon)
            mod_img = mod_img.resize((180, 180))
            mod_bg.alpha_composite(mod_img, (35, 15))
            mod_bg_draw.text((115, 180), mod.name, COLOR_WHITE, dna_font_26, "mm")

        if mod.id != -1 and mod.level:
            get_smooth_drawer().rounded_rectangle(
                (54, 30, 106, 60),
                10,
                COLOR_ORANGE_RED,
                target=mod_bg,
            )

            mod_bg_draw.text((80, 44), f"+{mod.level}", COLOR_WHITE, dna_font_26, "mm")

        # 2行2列，先左右，再上下
        all_mod_bg.alpha_composite(mod_bg, (30 + (index % 2) * 180, (index // 2) * 250))

    # 右4
    right_list = [role_detail.modes[1], role_detail.modes[3], role_detail.modes[7], role_detail.modes[5]]
    for index, mod in enumerate(right_list):
        quality = mod.quality or 1
        mod_bg = Image.open(TEXT_PATH / f"mod/mod_right_{quality}.png")
        mod_bg_draw = ImageDraw.Draw(mod_bg)

        if mod.id != -1 and mod.name:
            mod_img = await get_mod_img(mod.id, mod.icon)
            mod_img = mod_img.resize((180, 180))
            mod_bg.alpha_composite(mod_img, (35, 15))
            mod_bg_draw.text((140, 180), mod.name, COLOR_WHITE, dna_font_26, "mm")

        if mod.id != -1 and mod.level:
            get_smooth_drawer().rounded_rectangle(
                (134, 30, 186, 60),
                10,
                COLOR_ORANGE_RED,
                target=mod_bg,
            )

            mod_bg_draw.text((160, 44), f"+{mod.level}", COLOR_WHITE, dna_font_26, "mm")

        # 2行2列，先左右，再上下
        all_mod_bg.alpha_composite(mod_bg, (530 + (index % 2) * 180, (index // 2) * 250))

    # 中1
    center_list = role_detail.modes[-1]
    quality = center_list.quality or 1
    mod_bg = Image.open(TEXT_PATH / f"mod/mod_center_{quality}.png")
    mod_bg_draw = ImageDraw.Draw(mod_bg)
    if center_list.id != -1 and center_list.name:
        mod_img = await get_mod_img(center_list.id, center_list.icon)
        mod_img = mod_img.resize((150, 150))
        mod_bg.alpha_composite(mod_img, (5, 5))
        mod_bg_draw.text((80, 170), center_list.name, COLOR_WHITE, dna_font_26, "mm")

    if center_list.id != -1 and center_list.level:
        get_smooth_drawer().rounded_rectangle(
            (110, 110, 150, 140),
            10,
            COLOR_ORANGE_RED,
            target=mod_bg,
        )
        mod_bg_draw.text((130, 124), f"+{center_list.level}", COLOR_WHITE, dna_font_26, "mm")

    all_mod_bg.alpha_composite(mod_bg, (415, 100))

    card.alpha_composite(all_mod_bg, (0, h_index))
    h_index += 500

    card.alpha_composite(damage_section, (50, h_index + 20))
    h_index += damage_section.height + 40

    # 头像等（已在前面生成并用于计算总高度）
    card.alpha_composite(avatar_title, (0, h_index))

    card = add_footer(card, 600)
    card = await convert_img(card)
    message_ids = await bot.send(card, wait_recall=True)
    logger.debug(f"[DNA Detail] role panel message_ids={message_ids}")
    cache_original_image(message_ids, original_img_path)
