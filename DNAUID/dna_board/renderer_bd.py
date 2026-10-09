"""DOB 单构筑角色卡级大图：与角色面板同一套分节（立绘/属性表/技能/武器/mod/伤害/头像条/页脚）。

分节代码与 dna_detail/draw_role_card.py 同构（静态资源路径与行高公式照抄），
差异只在数据源：RoleDetail/WeaponDetail 由 service.synthesize_build 按 BD 自带值合成，
图标走同一套缓存（缺图画空框，不断整卡）；命座行 BD 无数据，整行省略。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.models import Event

from ..dna_sdk import version as dob_version_of
from ..utils.image import (
    COLOR_BLACK,
    COLOR_WHITE,
    COLOR_SALMON,
    COLOR_GOLDENROD,
    COLOR_ORANGE_RED,
    COLOR_PALE_GOLDENROD,
    get_div,
    add_footer,
    get_dna_bg,
    get_mod_img,
    get_attr_img,
    get_paint_img,
    get_skill_img,
    get_smooth_drawer,
    get_role_panel_img,
    get_avatar_title_img,
)
from ..utils.fonts.dna_fonts import dna_font_18, dna_font_24, dna_font_26, dna_font_30

TEXT_PATH = Path(__file__).parent.parent / "dna_detail" / "texture2d"

# 与角色卡完全一致的标准行（key, 显示名, 图标）与隐藏行图标
ATTR_LIST = [
    ("atk", "攻击", "icon1.png"),
    ("maxHp", "生命", "icon10.png"),
    ("maxES", "护盾", "icon11.png"),
    ("defense", "防御", "icon9.png"),
    ("maxSp", "最大神智", "icon8.png"),
    ("skillIntensity", "技能威力", "icon7.png"),
    ("skillRange", "技能范围", "icon6.png"),
    ("skillSustain", "技能耐久", "icon5.png"),
    ("skillEfficiency", "技能效益", "icon4.png"),
    ("skillRecharge", "充盈威力", "icon18.png"),
    ("strongValue", "昂扬", "icon3.png"),
    ("enmityValue", "背水", "icon2.png"),
]

HIDDEN_ATTR_ICONS = {
    "增伤": "icon19.png",
    "技能伤害": "icon20.png",
    "减伤": "icon21.png",
    "有效生命": "icon22.png",
}

DIM = (205, 205, 212)


def _clip_target(target_fn: str, limit: int = 12) -> str:
    """目标函数名裁剪（头像条键位宽度有限，超长加省略号）。"""
    text = target_fn or "目标DPS"
    return text if len(text) <= limit else text[:limit] + "…"


async def draw_bd_role_card(synth: dict, ev: Event, pack_version: str | None = None) -> Image.Image:
    """合成好的 BD（service.synthesize_build 产物）装成角色卡大图。"""
    from ..dna_detail.local_damage import draw_local_damage_section
    from ..dna_detail.local_attribute import compute_attr_context, compute_final_attribute
    from ..dna_detail.weapon_renderer import draw_weapon_detail_section

    build = synth["build"]
    role = build.role
    weapons = build.weapons
    char_id = role.charId

    ctx = compute_attr_context(build)
    final_attr = compute_final_attribute(build, ctx)
    damage_section = draw_local_damage_section(build, ctx)

    weapon_sections: list[Image.Image] = []
    if weapons.get("close") is not None:
        weapon_sections.append(await draw_weapon_detail_section(build, weapons["close"], "近战武器", "close"))
    if weapons.get("ranged") is not None:
        weapon_sections.append(await draw_weapon_detail_section(build, weapons["ranged"], "远程武器", "ranged"))

    div_img = get_div()
    author = synth.get("author") or "匿名"
    if len(author) > 12:
        author = author[:12] + "…"
    try:
        author_qq = int(synth.get("author_qq") or 0)
    except (TypeError, ValueError):
        author_qq = 0
    avatar_title = await get_avatar_title_img(
        ev,
        synth.get("bdid") or "",
        author,
        user_level=role.level,
        other_info=[
            (_clip_target(synth.get("target_fn") or ""), synth["dps"]),
            ("点赞", str(synth["likes"])),
            ("浏览", str(synth["views"])),
        ],
        avatar_user_id=str(author_qq) if author_qq > 0 else None,
        uid_hidden=True,
    )
    # 自绘 BD 徽章盖掉原来的 UID 徽章位（几何与角色卡一致）
    bd_draw = ImageDraw.Draw(avatar_title)
    get_smooth_drawer().rounded_rectangle(
        (320, 140, 320 + 330, 140 + 40), 15, COLOR_PALE_GOLDENROD, target=avatar_title
    )
    bd_draw.text((330, 160), f"BD {synth.get('bdid') or ''}", COLOR_BLACK, dna_font_30, "lm")
    avatar_title = avatar_title.resize((1000, 1000 * avatar_title.height // avatar_title.width))

    prop_info_bar1 = Image.open(TEXT_PATH / "prop_info_bar1.png")
    prop_info_bar2 = Image.open(TEXT_PATH / "prop_info_bar2.png")
    global_skill_bg = Image.open(TEXT_PATH / "skill_bg.png")

    weapon_sections_height = sum(section.height for section in weapon_sections)
    total_attr_rows = len(ATTR_LIST) + len(final_attr.hidden_rows)
    panel_h = max(850, 200 + 53 * total_attr_rows + 6 + 6)
    damage_h = damage_section.height + 40 if damage_section is not None else 0
    total_h = (
        panel_h
        + div_img.height
        + global_skill_bg.height
        + weapon_sections_height
        + div_img.height
        + damage_h
        + avatar_title.height
        + 600
    )
    card = get_dna_bg(1000, total_h, "bg2")

    # 立绘（自定义面板优先，否则缓存立绘，缺图即空白——与角色卡同管线）
    role_panel = get_role_panel_img(char_id)
    paint_offset = max(0, panel_h - 850)
    if role_panel is not None:
        _, role_panel_img = role_panel
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
        card.alpha_composite(panel_img, (0, paint_offset))
    else:
        paint_img = await get_paint_img(char_id, None)
        paint_img = paint_img.resize((int(1320 * 0.8), int(1320 * 0.8)))
        card.alpha_composite(paint_img, (-280, -100 + paint_offset))

    # 信息框：BD 标题 + 角色·等级（BD 无命座数据，不画命座徽章与命座行）
    info_bg = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    info_bg_draw = ImageDraw.Draw(info_bg)
    point = Image.open(TEXT_PATH / "point.png")
    info_bg.alpha_composite(point, (10, 10))
    title = synth["title"] or ""
    while title and info_bg_draw.textlength(title + "…", font=dna_font_30) > 330:
        title = title[:-1]
    info_bg_draw.text(
        (50, 30), title + ("…" if title != (synth["title"] or "") else ""), COLOR_WHITE, dna_font_30, "lm"
    )
    try:
        attr_img = await get_attr_img(char_id, "")
        attr_img = attr_img.resize((attr_img.width // 2, attr_img.height // 2))
        info_bg.alpha_composite(attr_img, (10, 62))
    except OSError:
        pass
    info_bg_draw.text((50, 92), f"{role.charName} · Lv.{role.level}", DIM, dna_font_24, "lm")
    card.alpha_composite(info_bg, (550, 80))

    # 属性表（标准 12 行 + 隐藏行，与角色卡同样式同图标）
    final_attr_map = dict(final_attr.rows)
    attribute = role.attribute
    official_values: dict[str, str] = {
        "atk": str(attribute.atk),
        "maxHp": str(attribute.maxHp),
        "maxES": str(attribute.maxES),
        "defense": str(attribute.defense),
        "maxSp": str(attribute.maxSp),
        "skillIntensity": attribute.skillIntensity,
        "skillRange": attribute.skillRange,
        "skillSustain": attribute.skillSustain,
        "skillEfficiency": attribute.skillEfficiency,
        "skillRecharge": "",
        "strongValue": attribute.strongValue,
        "enmityValue": attribute.enmityValue,
    }
    attr_bg = Image.new("RGBA", (400, 53 * total_attr_rows + 6), (0, 0, 0, 128))
    for index, attrs in enumerate(ATTR_LIST):
        prop_info = prop_info_bar1.copy() if index % 2 == 0 else prop_info_bar2.copy()
        prop_info_draw = ImageDraw.Draw(prop_info)
        attr_value = final_attr_map.get(attrs[1]) or official_values[attrs[0]]
        prop_info.alpha_composite(Image.open(TEXT_PATH / f"icons/{attrs[2]}"), (0, 0))
        prop_info_draw.text((53, 25), attrs[1], COLOR_WHITE, font=dna_font_26, anchor="lm")
        prop_info_draw.text(
            (370, 25),
            (attr_value if "%" in attr_value or not attr_value.isdigit() else f"{int(attr_value):,}"),
            COLOR_WHITE,
            font=dna_font_26,
            anchor="rm",
        )
        attr_bg.alpha_composite(prop_info, (0, index * 53))
    for offset, (hidden_name, hidden_value) in enumerate(final_attr.hidden_rows):
        index = len(ATTR_LIST) + offset
        prop_info = prop_info_bar1.copy() if index % 2 == 0 else prop_info_bar2.copy()
        prop_info_draw = ImageDraw.Draw(prop_info)
        prop_info.alpha_composite(
            Image.open(TEXT_PATH / "icons" / HIDDEN_ATTR_ICONS.get(hidden_name, "icon1.png")), (0, 0)
        )
        prop_info_draw.text((53, 25), hidden_name, COLOR_WHITE, font=dna_font_26, anchor="lm")
        prop_info_draw.text(
            (370, 25),
            (hidden_value if "%" in hidden_value or not hidden_value.isdigit() else f"{int(hidden_value):,}"),
            COLOR_WHITE,
            font=dna_font_26,
            anchor="rm",
        )
        attr_bg.alpha_composite(prop_info, (0, index * 53))
    card.alpha_composite(attr_bg, (550, 200))

    h_index = max(850, 200 + attr_bg.height + 6)
    card.alpha_composite(div_img, (0, h_index))
    h_index += div_img.height

    # 技能（图标走角色卡同一缓存，缺图空白）
    for index, skill in enumerate(role.skills[:3]):
        skill_bg = global_skill_bg.copy()
        skill_bg_draw = ImageDraw.Draw(skill_bg)
        skill_img = await get_skill_img(char_id, skill.skillName, None)
        skill_img = skill_img.resize((100, 100))
        skill_bg.alpha_composite(skill_img, (20, 30))
        if len(skill.skillName) <= 5:
            skill_bg_draw.text((120, 55), skill.skillName, COLOR_GOLDENROD, dna_font_24, "lm")
        else:
            skill_bg_draw.text((120, 55), skill.skillName, COLOR_GOLDENROD, dna_font_18, "lm")
        get_smooth_drawer().rounded_rectangle((120, 80, 200, 110), 10, COLOR_SALMON, target=skill_bg)
        skill_bg_draw.text((160, 94), f"Lv.{skill.level}", COLOR_WHITE, dna_font_26, "mm")
        card.alpha_composite(skill_bg, (50 + index * 300, h_index))
    h_index += global_skill_bg.height

    for weapon_section in weapon_sections:
        card.alpha_composite(weapon_section, (0, h_index))
        h_index += weapon_section.height

    card.alpha_composite(div_img, (0, h_index))
    h_index += div_img.height

    # mod（左4右4中1，槽位语义与角色卡一致；BD 自带等级）
    all_mod_bg = Image.new("RGBA", (1000, 500), (0, 0, 0, 0))
    left_list = [role.modes[0], role.modes[2], role.modes[6], role.modes[4]]
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
            get_smooth_drawer().rounded_rectangle((54, 30, 106, 60), 10, COLOR_ORANGE_RED, target=mod_bg)
            mod_bg_draw.text((80, 44), f"+{mod.level}", COLOR_WHITE, dna_font_26, "mm")
        all_mod_bg.alpha_composite(mod_bg, (30 + (index % 2) * 180, (index // 2) * 250))
    right_list = [role.modes[3], role.modes[1], role.modes[7], role.modes[5]]
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
            get_smooth_drawer().rounded_rectangle((134, 30, 186, 60), 10, COLOR_ORANGE_RED, target=mod_bg)
            mod_bg_draw.text((160, 44), f"+{mod.level}", COLOR_WHITE, dna_font_26, "mm")
        all_mod_bg.alpha_composite(mod_bg, (530 + (index % 2) * 180, (index // 2) * 250))
    center_list = role.modes[-1]
    quality = center_list.quality or 1
    mod_bg = Image.open(TEXT_PATH / f"mod/mod_center_{quality}.png")
    mod_bg_draw = ImageDraw.Draw(mod_bg)
    if center_list.id != -1 and center_list.name:
        mod_img = await get_mod_img(center_list.id, center_list.icon)
        mod_img = mod_img.resize((150, 150))
        mod_bg.alpha_composite(mod_img, (5, 5))
        mod_bg_draw.text((80, 170), center_list.name, COLOR_WHITE, dna_font_26, "mm")
    if center_list.id != -1 and center_list.level:
        get_smooth_drawer().rounded_rectangle((110, 110, 150, 140), 10, COLOR_ORANGE_RED, target=mod_bg)
        mod_bg_draw.text((130, 124), f"+{center_list.level}", COLOR_WHITE, dna_font_26, "mm")
    all_mod_bg.alpha_composite(mod_bg, (415, 100))
    card.alpha_composite(all_mod_bg, (0, h_index))
    h_index += 500

    if damage_section is not None:
        card.alpha_composite(damage_section, (50, h_index + 20))
        h_index += damage_section.height + 40

    card.alpha_composite(avatar_title, (0, h_index))

    version = pack_version if pack_version is not None else dob_version_of()
    source_line = "Data Source: DNA Builder (DOB)"
    if version:
        source_line += f" | Pack Version: {version}"
    if synth.get("bdid"):
        source_line += f" | BD:{synth['bdid']}"
    card = add_footer(card, 600, source_line=source_line)
    return card
