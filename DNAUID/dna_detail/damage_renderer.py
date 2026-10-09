from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from ..utils.image import get_smooth_drawer
from ..utils.api.model import RoleDetail
from ..utils.dob.build import WeaponSlot
from ..utils.dob.panel import PanelView
from ..utils.fonts.dna_fonts import (
    dna_font_18,
    dna_font_20,
    dna_font_22,
    dna_font_24,
    dna_font_26,
    dna_font_28,
    dna_font_30,
    dna_font_34,
    dna_font_36,
)

PANEL_WIDTH = 900
PANEL_PADDING = 20
CONTENT_WIDTH = PANEL_WIDTH - PANEL_PADDING * 2
HEADER_HEIGHT = 64
SECTION_GAP = 20
PANEL_HEADER_HEIGHT = 48
PANEL_BODY_GAP = 6
DATA_COLUMNS = 2
DATA_ROW_HEIGHT = 48
WEAPON_FOOTER_HEIGHT = 88

PANEL_FILL = (16, 16, 19, 196)
HEADER_FILL = (38, 38, 40, 184)
BODY_FILL = (9, 9, 10, 56)
FOOTER_FILL = (255, 255, 255, 14)
HEADER_TEXT = (255, 247, 207, 255)
DATA_TEXT = (244, 213, 141, 255)
SECONDARY_TEXT = (230, 226, 216, 255)
VALUE_TEXT = (255, 255, 255, 255)
DIVIDER = (255, 255, 255, 28)

ELEMENT_TEXT_COLORS = {
    "暗": (198, 198, 224, 255),
    "光": (246, 236, 213, 255),
    "水": (225, 231, 253, 255),
    "火": (252, 188, 184, 255),
    "雷": (216, 177, 244, 255),
    "风": (203, 243, 214, 255),
}


def _draw_round_rect(
    image: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int] | None = None,
    width: int = 0,
) -> None:
    get_smooth_drawer().rounded_rectangle(
        box,
        radius,
        fill,
        outline,
        width,
        target=image,
    )


def _draw_header_surface(
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    surface = Image.new("RGBA", (width, height), HEADER_FILL)
    fade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fade_draw = ImageDraw.Draw(fade)
    segment_width = max(1, width // 8)
    for segment in range(8):
        alpha = 24 * (8 - segment) // 8
        segment_left = segment * segment_width
        segment_right = width if segment == 7 else (segment + 1) * segment_width
        fade_draw.rectangle(
            (segment_left, 0, segment_right, height),
            fill=(255, 255, 255, alpha),
        )
    texture = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    texture_draw = ImageDraw.Draw(texture)
    for offset in range(-height, width, 22):
        texture_draw.line(
            (offset, height, offset + height, 0),
            fill=(255, 255, 255, 9),
            width=1,
        )
    surface.alpha_composite(fade)
    surface.alpha_composite(texture)
    image.alpha_composite(surface, (left, top))


def _draw_row_surface(
    image: Image.Image,
    box: tuple[int, int, int, int],
    row_index: int,
) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    surface = Image.new("RGBA", (width, height), BODY_FILL)
    fade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    fade_draw = ImageDraw.Draw(fade)
    max_alpha = 15 if row_index % 2 == 0 else 9
    segment_width = max(1, width // 8)
    for segment in range(8):
        alpha = max_alpha * (8 - segment) // 8
        segment_left = segment * segment_width
        segment_right = width if segment == 7 else (segment + 1) * segment_width
        fade_draw.rectangle(
            (segment_left, 0, segment_right, height),
            fill=(255, 255, 255, alpha),
        )
    surface.alpha_composite(fade)
    image.alpha_composite(surface, (left, top))


def _fit_font(
    text: str,
    max_width: int,
    candidates: tuple[ImageFont.FreeTypeFont, ...],
) -> ImageFont.FreeTypeFont:
    for font in candidates:
        if font.getlength(text) <= max_width:
            return font
    return candidates[-1]


def _fit_row_fonts(
    label: str,
    value: str,
    cell_width: int,
) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    label_fonts = (dna_font_22, dna_font_20, dna_font_18)
    value_fonts = (dna_font_24, dna_font_22, dna_font_20, dna_font_18)
    available_width = cell_width - 36
    for label_font in label_fonts:
        for value_font in value_fonts:
            occupied_width = label_font.getlength(label) + value_font.getlength(value) + 28
            if occupied_width <= available_width:
                return label_font, value_font
    return label_fonts[-1], value_fonts[-1]


def _draw_panel_header(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    title: str,
    meta: str | None,
    title_color: tuple[int, int, int, int],
    meta_color: tuple[int, int, int, int],
    y: int,
) -> int:
    _draw_header_surface(
        image,
        (
            PANEL_PADDING,
            y,
            PANEL_WIDTH - PANEL_PADDING,
            y + PANEL_HEADER_HEIGHT,
        ),
    )
    draw.rectangle(
        (
            PANEL_PADDING + 14,
            y + 15,
            PANEL_PADDING + 18,
            y + 33,
        ),
        fill=title_color,
    )
    draw.text(
        (PANEL_PADDING + 30, y + PANEL_HEADER_HEIGHT // 2),
        title,
        title_color,
        dna_font_26,
        "lm",
    )
    if meta is not None:
        draw.text(
            (
                PANEL_WIDTH - PANEL_PADDING - 16,
                y + PANEL_HEADER_HEIGHT // 2,
            ),
            meta,
            meta_color,
            dna_font_20,
            "rm",
        )
    return y + PANEL_HEADER_HEIGHT


def _draw_data_rows(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    metrics: list[tuple[str, str]],
    label_color: tuple[int, int, int, int],
    value_color: tuple[int, int, int, int],
    y: int,
) -> int:
    row_count = max(1, (len(metrics) + DATA_COLUMNS - 1) // DATA_COLUMNS)
    cell_width = CONTENT_WIDTH // DATA_COLUMNS
    for row in range(row_count):
        row_y = y + row * DATA_ROW_HEIGHT
        _draw_row_surface(
            image,
            (
                PANEL_PADDING,
                row_y,
                PANEL_WIDTH - PANEL_PADDING,
                row_y + DATA_ROW_HEIGHT,
            ),
            row,
        )
        for column in range(DATA_COLUMNS):
            index = row * DATA_COLUMNS + column
            if index >= len(metrics):
                continue
            label, value = metrics[index]
            x = PANEL_PADDING + column * cell_width
            label_font, value_font = _fit_row_fonts(label, value, cell_width)
            draw.text(
                (x + 18, row_y + DATA_ROW_HEIGHT // 2),
                label,
                label_color,
                label_font,
                "lm",
            )
            draw.text(
                (
                    x + cell_width - 18,
                    row_y + DATA_ROW_HEIGHT // 2,
                ),
                value,
                value_color,
                value_font,
                "rm",
            )
    return y + row_count * DATA_ROW_HEIGHT


def _draw_weapon_footer(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    metrics: list[tuple[str, str, str]],
    y: int,
) -> int:
    footer = Image.new(
        "RGBA",
        (CONTENT_WIDTH, WEAPON_FOOTER_HEIGHT),
        FOOTER_FILL,
    )
    image.alpha_composite(footer, (PANEL_PADDING, y))
    column_width = CONTENT_WIDTH // len(metrics)
    for index, (slot_label, weapon_name, damage_text) in enumerate(metrics):
        x = PANEL_PADDING + index * column_width
        center_x = x + column_width // 2
        if index > 0:
            draw.line(
                (
                    x,
                    y + 16,
                    x,
                    y + WEAPON_FOOTER_HEIGHT - 16,
                ),
                fill=DIVIDER,
                width=1,
            )
        value_font = _fit_font(
            damage_text,
            column_width - 36,
            (
                dna_font_36,
                dna_font_34,
                dna_font_30,
                dna_font_28,
                dna_font_26,
                dna_font_24,
                dna_font_22,
            ),
        )
        draw.text(
            (center_x, y + 31),
            damage_text,
            VALUE_TEXT,
            value_font,
            "mm",
        )
        label = f"{slot_label}武器伤害 · {weapon_name}"
        label_font = _fit_font(
            label,
            column_width - 36,
            (dna_font_20, dna_font_18),
        )
        draw.text(
            (center_x, y + 66),
            label,
            SECONDARY_TEXT,
            label_font,
            "mm",
        )
    return y + WEAPON_FOOTER_HEIGHT


def _rows_height(count: int) -> int:
    return max(1, (count + DATA_COLUMNS - 1) // DATA_COLUMNS) * DATA_ROW_HEIGHT


def draw_damage_section(view: PanelView, role: RoleDetail) -> Image.Image:
    """伤害计算区块：角色属性（基础 → 最终）+ 武器期望伤害 + 隐藏属性 + 技能字段。"""
    attr_rows = [(label, f"{base} → {final}") for label, base, final in view.compare_rows]
    weapon_rows = [
        (slot.value, weapon.detail.name, f"{weapon.damage:,.0f}" if weapon.damage is not None else "无法计算")
        for slot in (WeaponSlot.MELEE, WeaponSlot.RANGED, WeaponSlot.SKILL)
        if (weapon := view.weapons.get(slot)) is not None
    ]
    element_color = ELEMENT_TEXT_COLORS.get(role.elementName, HEADER_TEXT)

    height = PANEL_PADDING + HEADER_HEIGHT
    height += SECTION_GAP + PANEL_HEADER_HEIGHT + PANEL_BODY_GAP + _rows_height(len(attr_rows))
    if weapon_rows:
        height += PANEL_BODY_GAP + WEAPON_FOOTER_HEIGHT
    height += SECTION_GAP + PANEL_HEADER_HEIGHT + PANEL_BODY_GAP + _rows_height(len(view.hidden_rows))
    for skill in view.skills:
        height += SECTION_GAP + PANEL_HEADER_HEIGHT + PANEL_BODY_GAP + _rows_height(len(skill.rows))
    height += PANEL_PADDING

    image = Image.new("RGBA", (PANEL_WIDTH, max(80, height)), (0, 0, 0, 0))
    _draw_round_rect(image, (0, 0, PANEL_WIDTH, image.height), 10, PANEL_FILL)
    draw = ImageDraw.Draw(image)

    y = PANEL_PADDING
    _draw_header_surface(image, (PANEL_PADDING, y, PANEL_WIDTH - PANEL_PADDING, y + HEADER_HEIGHT))
    draw.rectangle((PANEL_PADDING + 16, y + 20, PANEL_PADDING + 20, y + 44), fill=HEADER_TEXT)
    draw.text((PANEL_PADDING + 34, y + HEADER_HEIGHT // 2), "伤害计算", HEADER_TEXT, dna_font_30, "lm")
    draw.text(
        (PANEL_WIDTH - PANEL_PADDING - 16, y + HEADER_HEIGHT // 2),
        f"角色 {role.charName}",
        VALUE_TEXT,
        dna_font_22,
        "rm",
    )
    y += HEADER_HEIGHT

    y += SECTION_GAP
    y = _draw_panel_header(image, draw, "角色属性", "基础 → 最终", HEADER_TEXT, SECONDARY_TEXT, y)
    y += PANEL_BODY_GAP
    y = _draw_data_rows(image, draw, attr_rows, DATA_TEXT, VALUE_TEXT, y)

    if weapon_rows:
        y += PANEL_BODY_GAP
        y = _draw_weapon_footer(image, draw, weapon_rows, y)

    y += SECTION_GAP
    y = _draw_panel_header(image, draw, "隐藏属性", None, HEADER_TEXT, SECONDARY_TEXT, y)
    y += PANEL_BODY_GAP
    y = _draw_data_rows(image, draw, view.hidden_rows, DATA_TEXT, VALUE_TEXT, y)

    for skill in view.skills:
        y += SECTION_GAP
        y = _draw_panel_header(image, draw, f"“{skill.name}”", f"Lv.{skill.level}", element_color, SECONDARY_TEXT, y)
        y += PANEL_BODY_GAP
        y = _draw_data_rows(image, draw, skill.rows, element_color, VALUE_TEXT, y)

    return image
