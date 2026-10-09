from __future__ import annotations

from typing import Literal
from pathlib import Path

from PIL import Image, ImageOps, ImageDraw

from ..utils.image import (
    COLOR_WHITE,
    COLOR_SALMON,
    COLOR_GOLDENROD,
    COLOR_FIRE_BRICK,
    COLOR_ORANGE_RED,
    COLOR_PALE_GOLDENROD,
    get_div,
    add_footer,
    get_dna_bg,
    get_mod_img,
    get_grade_img,
    get_paint_img,
    get_skill_img,
    get_weapon_img,
    get_smooth_drawer,
    get_role_panel_img,
)
from .damage_renderer import draw_damage_section
from ..utils.api.model import Mode, RoleDetail
from ..utils.dob.build import DobBuild, WeaponSlot
from ..utils.dob.panel import PanelView, WeaponView
from ..utils.dob.records import mod_name, mod_quality
from ..utils.fonts.dna_fonts import dna_font_18, dna_font_24, dna_font_26

TEXT_PATH = Path(__file__).parent / "texture2d"
CARD_WIDTH = 1000
PORTRAIT_HEIGHT = 850
ATTR_ROW_HEIGHT = 53
MOD_GRID_HEIGHT = 500

# 面板 12 行属性的图标，顺序与 PanelView.attr_rows 一致
_ATTR_ICONS = (
    "icon1.png",
    "icon10.png",
    "icon11.png",
    "icon9.png",
    "icon8.png",
    "icon7.png",
    "icon6.png",
    "icon5.png",
    "icon4.png",
    "icon18.png",
    "icon3.png",
    "icon2.png",
)
# 武器属性 6 行的图标：类型/攻击/暴击率/暴击伤害/攻击速度/触发概率
_WEAPON_ATTR_ICONS = ("icon16.png", "icon17.png", "icon13.png", "icon12.png", "icon14.png", "icon15.png")
_WEAPON_TITLES = ((WeaponSlot.SKILL, "同律武器"), (WeaponSlot.MELEE, "近战武器"), (WeaponSlot.RANGED, "远程武器"))

ModSide = Literal["left", "right", "center"]
# 每种 mod 卡底图的 (图标边长, 图标位置, 名称位置, 等级徽章框, 等级文字位置)
_MOD_GEOMETRY: dict[
    ModSide, tuple[int, tuple[int, int], tuple[int, int], tuple[int, int, int, int], tuple[int, int]]
] = {
    "left": (180, (35, 15), (115, 180), (54, 30, 106, 60), (80, 44)),
    "right": (180, (35, 15), (140, 180), (134, 30, 186, 60), (160, 44)),
    "center": (150, (5, 5), (80, 170), (110, 110, 150, 140), (130, 124)),
}
# 角色 8 槽在左右两列的摆放顺序（游戏内槽位 ↔ modes 下标）
_CHAR_MOD_LEFT = (0, 2, 6, 4)
_CHAR_MOD_RIGHT = (3, 1, 7, 5)


def _open_rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


_PROP_BARS = (_open_rgba(TEXT_PATH / "prop_info_bar1.png"), _open_rgba(TEXT_PATH / "prop_info_bar2.png"))
_SKILL_BG = _open_rgba(TEXT_PATH / "skill_bg.png")
_GRADE_LOCKED = _open_rgba(TEXT_PATH / "grade_0.png")
_GRADE_UNLOCKED = _open_rgba(TEXT_PATH / "grade_1.png")


async def _mod_card(mode: Mode, side: ModSide) -> Image.Image:
    """mod 卡：官方缺名称/品质时回退数据包，空槽只画底框。"""
    is_empty = mode.id <= 0
    quality = 1 if is_empty else (mode.quality or mod_quality(mode.id))
    card = _open_rgba(TEXT_PATH / f"mod/mod_{side}_{quality}.png")
    if is_empty:
        return card
    icon_size, icon_pos, name_pos, badge_box, badge_pos = _MOD_GEOMETRY[side]
    icon = await get_mod_img(mode.id, mode.icon)
    card.alpha_composite(icon.resize((icon_size, icon_size)), icon_pos)
    draw = ImageDraw.Draw(card)
    name = mode.name or mod_name(mode.id)
    if name:
        draw.text(name_pos, name, COLOR_WHITE, dna_font_26, "mm")
    if mode.level:
        get_smooth_drawer().rounded_rectangle(badge_box, 10, COLOR_ORANGE_RED, target=card)
        draw.text(badge_pos, f"+{mode.level}", COLOR_WHITE, dna_font_26, "mm")
    return card


def _badge(text: str, width: int) -> Image.Image:
    badge = Image.new("RGBA", (width, 35))
    get_smooth_drawer().rounded_rectangle((0, 0, width, 35), fill=COLOR_FIRE_BRICK, radius=7, target=badge)
    ImageDraw.Draw(badge).text((width // 2, 17), text, COLOR_WHITE, dna_font_26, "mm")
    return badge


def level_badge(level: int) -> Image.Image:
    return _badge(f"Lv.{level}", 80)


def grade_badge(grade_level: int) -> Image.Image:
    badge = Image.new("RGBA", (34, 35))
    get_smooth_drawer().rounded_rectangle((0, 0, 34, 35), fill=COLOR_FIRE_BRICK, radius=7, target=badge)
    badge.alpha_composite(get_grade_img(grade_level), (0, 5))
    return badge


def _weapon_mod_layout(modes: list[Mode]) -> tuple[list[tuple[Mode, ModSide, int, int]], int, int]:
    """武器 mod 摆放，返回 (摆放, 武器信息行 y, 区块高度)。"""
    if len(modes) == 4:
        order: tuple[tuple[int, ModSide], ...] = ((0, "left"), (2, "left"), (3, "right"), (1, "right"))
        return [(modes[i], side, 40 + pos * 220, 52) for pos, (i, side) in enumerate(order)], 310, 490
    if len(modes) == 8:
        placements: list[tuple[Mode, ModSide, int, int]] = []
        for pos, i in enumerate((0, 2, 4, 6)):
            placements.append((modes[i], "left", 30 + pos % 2 * 180, 52 + pos // 2 * 250))
        for pos, i in enumerate((1, 3, 7, 5)):
            placements.append((modes[i], "right", 530 + pos % 2 * 180, 52 + pos // 2 * 250))
        return placements, 570, 750
    raise ValueError(f"武器 Mod 槽数量必须为 4 或 8，实际为 {len(modes)}")


async def _weapon_section(weapon: WeaponView, title: str) -> Image.Image:
    detail = weapon.detail
    placements, info_y, height = _weapon_mod_layout(detail.modes)
    section = Image.new("RGBA", (CARD_WIDTH, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(section)
    draw.text((50, 25), title, COLOR_PALE_GOLDENROD, dna_font_24, "lm")
    draw.line((70 + int(dna_font_24.getlength(title)), 25, 950, 25), fill=(255, 255, 255, 70), width=1)
    for mode, side, x, y in placements:
        section.alpha_composite(await _mod_card(mode, side), (x, y))

    weapon_bg = _open_rgba(TEXT_PATH / "weapon_bg.png")
    weapon_img = await get_weapon_img(detail.id, detail.icon)
    weapon_bg.alpha_composite(weapon_img.resize((180, 180)), (-10, -10))
    weapon_bg.alpha_composite(level_badge(detail.level), (150, 100))
    weapon_bg = weapon_bg.resize((int(weapon_bg.width * 0.8), int(weapon_bg.height * 0.8)))
    section.alpha_composite(weapon_bg, (70, info_y))
    draw.text((70, info_y + 135), detail.name, COLOR_WHITE, dna_font_26, "lm")

    attr_panel = _open_rgba(TEXT_PATH / "weapon_attr.png")
    attr_draw = ImageDraw.Draw(attr_panel)
    for index, ((label, value), icon) in enumerate(zip(weapon.rows, _WEAPON_ATTR_ICONS)):
        column, row = index % 2, index // 2
        attr_panel.alpha_composite(_open_rgba(TEXT_PATH / "icons" / icon), (column * 320, row * 53))
        attr_draw.text((53 + column * 320, 25 + row * 53), label, COLOR_WHITE, dna_font_26, "lm")
        attr_draw.text((310 + column * 318, 25 + row * 53), value, COLOR_WHITE, dna_font_26, "rm")
    section.alpha_composite(attr_panel, (290, info_y))
    return section


def _attr_table(view: PanelView) -> Image.Image:
    rows = [(*row, icon) for row, icon in zip(view.attr_rows, _ATTR_ICONS)]
    table = Image.new("RGBA", (400, ATTR_ROW_HEIGHT * len(rows) + 6), (0, 0, 0, 128))
    for index, (label, value, icon) in enumerate(rows):
        bar = _PROP_BARS[index % 2].copy()
        bar.alpha_composite(_open_rgba(TEXT_PATH / "icons" / icon), (0, 0))
        bar_draw = ImageDraw.Draw(bar)
        bar_draw.text((53, 25), label, COLOR_WHITE, dna_font_26, "lm")
        bar_draw.text((370, 25), value, COLOR_WHITE, dna_font_26, "rm")
        table.alpha_composite(bar, (0, index * ATTR_ROW_HEIGHT))
    return table


async def _draw_portrait(card: Image.Image, role: RoleDetail) -> Path | None:
    """立绘：自定义面板图优先（返回其路径供「原图」使用），否则用游戏立绘。"""
    custom = get_role_panel_img(role.charId)
    if custom is None:
        paint = await get_paint_img(role.charId, role.paint)
        card.alpha_composite(paint.resize((1056, 1056)), (-280, -100))
        return None
    path, image = custom
    size, portrait_size, fade = (CARD_WIDTH, PORTRAIT_HEIGHT), (600, PORTRAIT_HEIGHT), 72
    panel = Image.new("RGBA", size)
    if image.width >= image.height:
        panel.alpha_composite(ImageOps.fit(image, size, method=Image.Resampling.LANCZOS))
    else:
        # 竖图放左侧，右边缘渐隐
        portrait = ImageOps.fit(image, portrait_size, method=Image.Resampling.LANCZOS)
        side_mask = Image.new("L", portrait_size, 255)
        side_fade = Image.linear_gradient("L").rotate(270, expand=True).resize((fade, portrait_size[1]))
        side_mask.paste(side_fade, (portrait_size[0] - fade, 0))
        panel.alpha_composite(Image.composite(portrait, Image.new("RGBA", portrait_size), side_mask))
    mask = Image.new("L", size, 255)
    mask.paste(ImageOps.invert(Image.linear_gradient("L")).resize((size[0], fade)), (0, size[1] - fade))
    card.alpha_composite(Image.composite(panel, Image.new("RGBA", size), mask), (0, 0))
    return path


def _grade_row(grade_level: int) -> Image.Image:
    """溯源解锁行：满溯源画 7 格，否则 6 格。"""
    total = 7 if grade_level >= 7 else 6
    step = 750 // (total - 1)
    row = Image.new("RGBA", (CARD_WIDTH, 130), (0, 0, 0, 0))
    for i in range(1, total + 1):
        cell = (_GRADE_UNLOCKED if i <= grade_level else _GRADE_LOCKED).copy()
        grade = get_grade_img(i)
        cell.alpha_composite(grade.resize((int(grade.width * 1.8), int(grade.height * 1.8))), (33, 37))
        row.alpha_composite(cell, (100 + (i - 1) * step, 0))
    return row.resize((500, 65))


async def _skill_row(role: RoleDetail) -> Image.Image:
    row = Image.new("RGBA", (CARD_WIDTH, _SKILL_BG.height), (0, 0, 0, 0))
    for index, skill in enumerate(role.skills[:3]):
        cell = _SKILL_BG.copy()
        cell_draw = ImageDraw.Draw(cell)
        icon = await get_skill_img(role.charId, skill.skillName, skill.icon)
        cell.alpha_composite(icon.resize((100, 100)), (20, 30))
        font = dna_font_24 if len(skill.skillName) <= 5 else dna_font_18
        cell_draw.text((120, 55), skill.skillName, COLOR_GOLDENROD, font, "lm")
        get_smooth_drawer().rounded_rectangle((120, 80, 200, 110), 10, COLOR_SALMON, target=cell)
        cell_draw.text((160, 94), f"Lv.{skill.level}", COLOR_WHITE, dna_font_26, "mm")
        row.alpha_composite(cell, (50 + index * 300, 0))
    return row


async def _char_mod_grid(role: RoleDetail) -> Image.Image:
    grid = Image.new("RGBA", (CARD_WIDTH, MOD_GRID_HEIGHT), (0, 0, 0, 0))
    for pos, index in enumerate(_CHAR_MOD_LEFT):
        grid.alpha_composite(await _mod_card(role.modes[index], "left"), (30 + pos % 2 * 180, pos // 2 * 250))
    for pos, index in enumerate(_CHAR_MOD_RIGHT):
        grid.alpha_composite(await _mod_card(role.modes[index], "right"), (530 + pos % 2 * 180, pos // 2 * 250))
    grid.alpha_composite(await _mod_card(role.modes[-1], "center"), (415, 100))
    return grid


async def render_role_card(
    build: DobBuild,
    view: PanelView,
    *,
    info_box: Image.Image,
    avatar_title: Image.Image,
    footer_line: str,
    grade_level: int | None,
) -> tuple[Image.Image, Path | None]:
    """角色卡（面板与 DOB 构筑共用），返回 (卡片, 自定义立绘路径)。

    grade_level 为 None 时不画溯源行（DOB 构筑没有溯源数据）。
    """
    role = build.role
    attr_table = _attr_table(view)
    skill_row = await _skill_row(role)
    weapon_sections = [
        await _weapon_section(view.weapons[slot], title) for slot, title in _WEAPON_TITLES if slot in view.weapons
    ]
    mod_grid = await _char_mod_grid(role)
    damage = draw_damage_section(view, role)
    avatar_title = avatar_title.resize((CARD_WIDTH, CARD_WIDTH * avatar_title.height // avatar_title.width))
    div = get_div()

    blocks = [div, skill_row, *weapon_sections, div, mod_grid]
    total = PORTRAIT_HEIGHT + sum(b.height for b in blocks) + 20 + damage.height + 20 + avatar_title.height + 100
    card = get_dna_bg(CARD_WIDTH, total, "bg2")

    portrait_path = await _draw_portrait(card, role)
    card.alpha_composite(info_box, (550, 80))
    if grade_level is not None:
        card.alpha_composite(_grade_row(grade_level), (0, 750))
    card.alpha_composite(attr_table, (550, 200))

    y = PORTRAIT_HEIGHT
    for block in blocks:
        card.alpha_composite(block, (0, y))
        y += block.height
    card.alpha_composite(damage, (50, y + 20))
    y += damage.height + 40
    card.alpha_composite(avatar_title, (0, y))
    return add_footer(card, 600, source_line=footer_line), portrait_path
