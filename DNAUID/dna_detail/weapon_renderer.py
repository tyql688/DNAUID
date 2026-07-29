from __future__ import annotations

from typing import Literal
from pathlib import Path

from PIL import Image, ImageDraw

from ..utils.image import (
    COLOR_WHITE,
    COLOR_FIRE_BRICK,
    COLOR_ORANGE_RED,
    COLOR_PALE_GOLDENROD,
    get_mod_img,
    get_weapon_img,
    get_smooth_drawer,
)
from ..utils.api.model import Mode, WeaponDetail
from ..utils.fonts.dna_fonts import dna_font_24, dna_font_26

TEXT_PATH = Path(__file__).parent / "texture2d"

SECTION_WIDTH = 1000
HEADER_HEIGHT = 52
FOUR_MODE_SECTION_HEIGHT = 490
EIGHT_MODE_SECTION_HEIGHT = 750
FOUR_MODE_INFO_Y = 310
EIGHT_MODE_INFO_Y = 570

_ModeSide = Literal["left", "right"]
_ModePlacement = tuple[Mode, _ModeSide, int, int]


def _open_rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def _mode_quality(mode: Mode) -> int:
    if mode.id == -1:
        return 1
    if mode.quality is None:
        raise RuntimeError(f"武器 Mod {mode.id} 缺少品质")
    return mode.quality


async def _draw_mode_card(
    mode: Mode,
    side: _ModeSide,
) -> Image.Image:
    quality = _mode_quality(mode)
    card = _open_rgba(
        TEXT_PATH / f"mod/mod_{side}_{quality}.png",
    )
    if mode.id == -1:
        return card
    if mode.id <= 0:
        raise RuntimeError(f"武器 Mod ID 非法: {mode.id}")
    if mode.name is None or mode.icon is None or mode.level is None:
        raise RuntimeError(f"武器 Mod {mode.id} 详情不完整")

    mod_image = await get_mod_img(mode.id, mode.icon)
    mod_image = mod_image.resize((180, 180))
    card.alpha_composite(mod_image, (35, 15))

    draw = ImageDraw.Draw(card)
    name_position = (115, 180) if side == "left" else (140, 180)
    draw.text(
        name_position,
        mode.name,
        COLOR_WHITE,
        dna_font_26,
        "mm",
    )
    if mode.level > 0:
        badge_box = (54, 30, 106, 60) if side == "left" else (134, 30, 186, 60)
        badge_position = (80, 44) if side == "left" else (160, 44)
        get_smooth_drawer().rounded_rectangle(
            badge_box,
            10,
            COLOR_ORANGE_RED,
            target=card,
        )
        draw.text(
            badge_position,
            f"+{mode.level}",
            COLOR_WHITE,
            dna_font_26,
            "mm",
        )
    return card


def _mode_layout(
    modes: list[Mode],
) -> tuple[list[_ModePlacement], int, int]:
    placements: list[_ModePlacement]
    if len(modes) == 4:
        indexes: tuple[tuple[int, _ModeSide], ...] = (
            (0, "left"),
            (2, "left"),
            (3, "right"),
            (1, "right"),
        )
        placements = [
            (modes[index], side, 40 + position * 220, HEADER_HEIGHT) for position, (index, side) in enumerate(indexes)
        ]
        return placements, FOUR_MODE_INFO_Y, FOUR_MODE_SECTION_HEIGHT

    if len(modes) == 8:
        left_indexes = (0, 2, 4, 6)
        right_indexes = (1, 3, 7, 5)
        placements = [
            (
                modes[index],
                "left",
                30 + position % 2 * 180,
                HEADER_HEIGHT + position // 2 * 250,
            )
            for position, index in enumerate(left_indexes)
        ]
        placements.extend(
            (
                modes[index],
                "right",
                530 + position % 2 * 180,
                HEADER_HEIGHT + position // 2 * 250,
            )
            for position, index in enumerate(right_indexes)
        )
        return placements, EIGHT_MODE_INFO_Y, EIGHT_MODE_SECTION_HEIGHT

    raise ValueError(
        f"武器 Mod 槽数量必须为 4 或 8，实际为 {len(modes)}",
    )


def _draw_section_title(
    section: Image.Image,
    title: str,
) -> None:
    draw = ImageDraw.Draw(section)
    draw.text(
        (50, 25),
        title,
        COLOR_PALE_GOLDENROD,
        dna_font_24,
        "lm",
    )
    line_start = 70 + int(dna_font_24.getlength(title))
    draw.line(
        (line_start, 25, 950, 25),
        fill=(255, 255, 255, 70),
        width=1,
    )


async def _draw_weapon_info(
    section: Image.Image,
    weapon_detail: WeaponDetail,
    info_y: int,
) -> None:
    weapon_background = _open_rgba(TEXT_PATH / "weapon_bg.png")
    weapon_image = await get_weapon_img(
        weapon_detail.id,
        weapon_detail.icon,
    )
    weapon_image = weapon_image.resize((180, 180))
    weapon_background.alpha_composite(weapon_image, (-10, -10))

    level_badge = Image.new("RGBA", (80, 35))
    get_smooth_drawer().rounded_rectangle(
        (0, 0, 80, 35),
        fill=COLOR_FIRE_BRICK,
        radius=7,
        target=level_badge,
    )
    ImageDraw.Draw(level_badge).text(
        (40, 17),
        f"Lv.{weapon_detail.level}",
        COLOR_WHITE,
        dna_font_26,
        "mm",
    )
    weapon_background.alpha_composite(level_badge, (150, 100))
    weapon_background = weapon_background.resize(
        (
            int(weapon_background.width * 0.8),
            int(weapon_background.height * 0.8),
        )
    )
    section.alpha_composite(weapon_background, (70, info_y))

    section_draw = ImageDraw.Draw(section)
    section_draw.text(
        (70, info_y + 135),
        weapon_detail.name,
        COLOR_WHITE,
        dna_font_26,
        "lm",
    )

    attribute_panel = _open_rgba(TEXT_PATH / "weapon_attr.png")
    attribute_draw = ImageDraw.Draw(attribute_panel)
    attributes = (
        ("武器类型", weapon_detail.elementName, "icon16.png"),
        ("攻击", f"{weapon_detail.attribute.atk:,}", "icon17.png"),
        ("暴击率", f"{weapon_detail.attribute.crd:.0%}", "icon13.png"),
        ("暴击伤害", f"{weapon_detail.attribute.cri:.0%}", "icon12.png"),
        ("攻击速度", f"{weapon_detail.attribute.speed:.0%}", "icon14.png"),
        ("触发率", f"{weapon_detail.attribute.trigger:.0%}", "icon15.png"),
    )
    for index, (label, value, icon_name) in enumerate(attributes):
        icon = _open_rgba(TEXT_PATH / f"icons/{icon_name}")
        column = index % 2
        row = index // 2
        attribute_panel.alpha_composite(icon, (column * 320, row * 53))
        attribute_draw.text(
            (53 + column * 320, 25 + row * 53),
            label,
            COLOR_WHITE,
            dna_font_26,
            "lm",
        )
        attribute_draw.text(
            (310 + column * 318, 25 + row * 53),
            value,
            COLOR_WHITE,
            dna_font_26,
            "rm",
        )
    section.alpha_composite(attribute_panel, (290, info_y))


async def draw_weapon_detail_section(
    weapon_detail: WeaponDetail,
    title: str,
) -> Image.Image:
    placements, info_y, section_height = _mode_layout(
        weapon_detail.modes,
    )
    section = Image.new(
        "RGBA",
        (SECTION_WIDTH, section_height),
        (0, 0, 0, 0),
    )
    _draw_section_title(section, title)
    for mode, side, x, y in placements:
        mode_card = await _draw_mode_card(mode, side)
        section.alpha_composite(mode_card, (x, y))
    await _draw_weapon_info(section, weapon_detail, info_y)
    return section
