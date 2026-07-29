from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from ..utils.image import COLOR_WHITE, get_smooth_drawer
from .damage_service import (
    RoleDamageBuild,
    get_skill_extend_level,
    get_calculation_skill_levels,
)
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
from ..utils.api.damage_model import (
    SkillResult,
    AttributeBag,
    RestraintType,
    CharacterCalculateData,
)
from ..utils.api.request_util import DNAApiResp

PANEL_WIDTH = 900
PANEL_PADDING = 20
CONTENT_WIDTH = PANEL_WIDTH - PANEL_PADDING * 2
HEADER_HEIGHT = 64
LINEUP_TOP_GAP = 10
LINEUP_ROW_HEIGHT = 34
LINEUP_ROW_GAP = 2
LINEUP_ITEM_GAP = 28
SECTION_GAP = 20
PANEL_HEADER_HEIGHT = 48
PANEL_BODY_GAP = 6
CHILD_SKILL_TOP_GAP = 8
CHILD_SKILL_HEADER_HEIGHT = 36
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


@dataclass(frozen=True, slots=True, kw_only=True)
class _LineupItem:
    label: str
    name: str

    @property
    def width(self) -> int:
        return int(dna_font_18.getlength(self.label) + 10 + dna_font_20.getlength(self.name))


@dataclass(frozen=True, slots=True, kw_only=True)
class _AttributeMetric:
    label: str
    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _WeaponMetric:
    label: str
    name: str
    value: str


@dataclass(frozen=True, slots=True, kw_only=True)
class _SkillPanel:
    skill: SkillResult
    children: tuple[SkillResult, ...]
    level: int


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


def _format_number(value: int | float, *, percent: bool) -> str:
    number = float(value)
    if number.is_integer():
        text = f"{int(number):,}"
    else:
        text = f"{number:,.2f}".rstrip("0").rstrip(".")
    if percent:
        return f"{text}%"
    return text


def _format_metric(
    base_value: int | float | None,
    final_value: int | float | None,
    *,
    percent: bool,
) -> str | None:
    if base_value is None and final_value is None:
        return None
    if final_value is None:
        if base_value is None:
            raise RuntimeError("属性值同时为空")
        return _format_number(base_value, percent=percent)
    final_text = _format_number(final_value, percent=percent)
    if base_value is None or base_value == final_value:
        return final_text
    base_text = _format_number(base_value, percent=percent)
    return f"{base_text} → {final_text}"


def _build_attribute_metrics(
    base: AttributeBag,
    final: AttributeBag,
) -> list[_AttributeMetric]:
    raw_metrics = [
        ("攻击", base.atk, final.atk, False),
        ("生命", base.hp, final.hp, False),
        ("护盾", base.es, final.es, False),
        ("防御", base.def_, final.def_, False),
        ("最大神志", base.sp, final.sp, False),
        ("技能威力", base.si, final.si, True),
        ("技能范围", base.sr, final.sr, True),
        ("技能耐久", base.ss, final.ss, True),
        ("技能效益", base.se, final.se, True),
        ("昂扬", base.sv, final.sv, True),
        ("背水", base.ev, final.ev, True),
    ]
    metrics: list[_AttributeMetric] = []
    for label, base_value, final_value, percent in raw_metrics:
        value = _format_metric(
            base_value,
            final_value,
            percent=percent,
        )
        if value is not None:
            metrics.append(_AttributeMetric(label=label, value=value))
    return metrics


def _format_skill_value(
    value: str | int | float | None,
    environment_value: str | int | float | None,
) -> str:
    if value is None:
        base_text = "—"
    else:
        base_text = str(value)
    if environment_value is None or environment_value == value:
        return base_text
    return f"{base_text} → {environment_value}"


def _build_lineup(build: RoleDamageBuild) -> list[_LineupItem]:
    lineup = [
        _LineupItem(
            label="角色",
            name=build.role_detail.charName,
        )
    ]
    if build.close_weapon_detail is not None:
        lineup.append(
            _LineupItem(
                label="近战",
                name=build.close_weapon_detail.name,
            )
        )
    if build.lang_range_weapon_detail is not None:
        lineup.append(
            _LineupItem(
                label="远程",
                name=build.lang_range_weapon_detail.name,
            )
        )
    if build.con_weapon_detail is not None:
        lineup.append(
            _LineupItem(
                label="同律",
                name=build.con_weapon_detail.name,
            )
        )
    lineup.extend(
        _LineupItem(
            label="协战",
            name=companion.name,
        )
        for companion in build.companions
    )
    return lineup


def _layout_lineup(
    lineup: list[_LineupItem],
) -> list[list[_LineupItem]]:
    rows: list[list[_LineupItem]] = []
    current_row: list[_LineupItem] = []
    current_width = 0
    for item in lineup:
        required_width = item.width if not current_row else item.width + LINEUP_ITEM_GAP
        if current_row and current_width + required_width > CONTENT_WIDTH:
            rows.append(current_row)
            current_row = []
            current_width = 0
            required_width = item.width
        current_row.append(item)
        current_width += required_width
    if current_row:
        rows.append(current_row)
    return rows


def _enemy_text(build: RoleDamageBuild) -> str:
    if build.enemy_config_id == 59:
        return "剧目-无尽 · 第31轮"
    return f"敌人配置 {build.enemy_config_id}"


def _restraint_text(build: RoleDamageBuild) -> str:
    return {
        RestraintType.UNRESTRAINED: "非克制",
        RestraintType.NONE: "无克制",
        RestraintType.RESTRAINED: "克制",
    }[build.restraint_type]


def _weapon_value(
    damage: str,
    environment_damage: str | None,
) -> str:
    if environment_damage is None or environment_damage == damage:
        return damage
    return f"{damage} → {environment_damage}"


def _build_weapon_metrics(
    build: RoleDamageBuild,
    calculation: CharacterCalculateData,
) -> list[_WeaponMetric]:
    damage = calculation.damage
    metrics: list[_WeaponMetric] = []
    if damage.close_weapon_damage is not None:
        name = "近战武器" if build.close_weapon_detail is None else build.close_weapon_detail.name
        metrics.append(
            _WeaponMetric(
                label="近战",
                name=name,
                value=_weapon_value(
                    damage.close_weapon_damage,
                    damage.close_weapon_damage_with_environment,
                ),
            )
        )
    if damage.lang_range_weapon_damage is not None:
        name = "远程武器" if build.lang_range_weapon_detail is None else build.lang_range_weapon_detail.name
        metrics.append(
            _WeaponMetric(
                label="远程",
                name=name,
                value=_weapon_value(
                    damage.lang_range_weapon_damage,
                    damage.lang_range_weapon_damage_with_environment,
                ),
            )
        )
    if damage.con_weapon_damage is not None:
        name = "同律武器" if build.con_weapon_detail is None else build.con_weapon_detail.name
        metrics.append(
            _WeaponMetric(
                label="同律",
                name=name,
                value=_weapon_value(
                    damage.con_weapon_damage,
                    damage.con_weapon_damage_with_environment,
                ),
            )
        )
    return metrics


def _build_skill_metrics(skill: SkillResult) -> list[_AttributeMetric]:
    attributes = skill.normal_skill_attributes + skill.damage_skill_attributes
    if not attributes:
        return [
            _AttributeMetric(
                label="技能参数",
                value="暂无",
            )
        ]
    return [
        _AttributeMetric(
            label=attribute.key,
            value=_format_skill_value(
                attribute.value,
                attribute.environment_value,
            ),
        )
        for attribute in attributes
    ]


def _skill_row_count(skill: SkillResult) -> int:
    attribute_count = len(skill.normal_skill_attributes + skill.damage_skill_attributes)
    return max(1, (attribute_count + DATA_COLUMNS - 1) // DATA_COLUMNS)


def _build_skill_panels(
    build: RoleDamageBuild,
    skills: list[SkillResult],
) -> list[_SkillPanel]:
    skills_by_id = {skill.id: skill for skill in skills}
    children_by_parent: dict[int, list[SkillResult]] = {skill.id: [] for skill in skills}
    root_skills: list[SkillResult] = []
    for skill in skills:
        if skill.parent_id is None:
            root_skills.append(skill)
            continue
        if skill.parent_id not in skills_by_id:
            raise RuntimeError(f"派生技能 {skill.id} 缺少父技能 {skill.parent_id}")
        children_by_parent[skill.parent_id].append(skill)

    skill_levels = get_calculation_skill_levels(build.role_detail)
    panels: list[_SkillPanel] = []
    for skill in root_skills:
        if skill.id not in skill_levels:
            raise RuntimeError(f"主技能 {skill.id} 缺少角色技能等级")
        panels.append(
            _SkillPanel(
                skill=skill,
                children=tuple(children_by_parent[skill.id]),
                level=skill_levels[skill.id],
            )
        )
    return panels


def _skill_height(panel: _SkillPanel) -> int:
    height = PANEL_HEADER_HEIGHT + PANEL_BODY_GAP
    height += _skill_row_count(panel.skill) * DATA_ROW_HEIGHT
    for child in panel.children:
        height += CHILD_SKILL_TOP_GAP + CHILD_SKILL_HEADER_HEIGHT
        height += _skill_row_count(child) * DATA_ROW_HEIGHT
    return height


def _draw_header(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    build: RoleDamageBuild,
) -> int:
    _draw_header_surface(
        image,
        (
            PANEL_PADDING,
            PANEL_PADDING,
            PANEL_WIDTH - PANEL_PADDING,
            PANEL_PADDING + HEADER_HEIGHT,
        ),
    )
    draw.rectangle(
        (
            PANEL_PADDING + 16,
            PANEL_PADDING + 20,
            PANEL_PADDING + 20,
            PANEL_PADDING + 44,
        ),
        fill=HEADER_TEXT,
    )
    draw.text(
        (PANEL_PADDING + 34, PANEL_PADDING + HEADER_HEIGHT // 2),
        "伤害计算",
        HEADER_TEXT,
        dna_font_30,
        "lm",
    )
    draw.text(
        (PANEL_WIDTH - PANEL_PADDING - 16, PANEL_PADDING + 23),
        _enemy_text(build),
        COLOR_WHITE,
        dna_font_22,
        "rm",
    )
    draw.text(
        (PANEL_WIDTH - PANEL_PADDING - 16, PANEL_PADDING + 47),
        _restraint_text(build),
        SECONDARY_TEXT,
        dna_font_18,
        "rm",
    )
    return PANEL_PADDING + HEADER_HEIGHT + LINEUP_TOP_GAP


def _draw_lineup(
    draw: ImageDraw.ImageDraw,
    rows: list[list[_LineupItem]],
    y: int,
) -> int:
    for row_index, row in enumerate(rows):
        x = PANEL_PADDING
        for item in row:
            draw.text(
                (x, y + LINEUP_ROW_HEIGHT // 2),
                item.label,
                DATA_TEXT,
                dna_font_18,
                "lm",
            )
            label_width = int(dna_font_18.getlength(item.label))
            draw.text(
                (
                    x + label_width + 10,
                    y + LINEUP_ROW_HEIGHT // 2,
                ),
                item.name,
                COLOR_WHITE,
                dna_font_20,
                "lm",
            )
            x += item.width + LINEUP_ITEM_GAP
        y += LINEUP_ROW_HEIGHT
        if row_index < len(rows) - 1:
            y += LINEUP_ROW_GAP
    return y


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
    metrics: list[_AttributeMetric],
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
            metric = metrics[index]
            x = PANEL_PADDING + column * cell_width
            label_font, value_font = _fit_row_fonts(
                metric.label,
                metric.value,
                cell_width,
            )
            draw.text(
                (x + 18, row_y + DATA_ROW_HEIGHT // 2),
                metric.label,
                label_color,
                label_font,
                "lm",
            )
            draw.text(
                (
                    x + cell_width - 18,
                    row_y + DATA_ROW_HEIGHT // 2,
                ),
                metric.value,
                value_color,
                value_font,
                "rm",
            )
    return y + row_count * DATA_ROW_HEIGHT


def _draw_weapon_footer(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    metrics: list[_WeaponMetric],
    y: int,
) -> int:
    footer = Image.new(
        "RGBA",
        (CONTENT_WIDTH, WEAPON_FOOTER_HEIGHT),
        FOOTER_FILL,
    )
    image.alpha_composite(footer, (PANEL_PADDING, y))
    column_width = CONTENT_WIDTH // len(metrics)
    for index, metric in enumerate(metrics):
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
            metric.value,
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
            metric.value,
            VALUE_TEXT,
            value_font,
            "mm",
        )
        label = f"{metric.label}武器伤害 · {metric.name}"
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


def _draw_child_skill_header(
    draw: ImageDraw.ImageDraw,
    title: str,
    color: tuple[int, int, int, int],
    y: int,
) -> int:
    center_y = y + CHILD_SKILL_HEADER_HEIGHT // 2
    text_x = PANEL_PADDING + 18
    draw.text(
        (text_x, center_y),
        title,
        color,
        dna_font_20,
        "lm",
    )
    line_x = text_x + int(dna_font_20.getlength(title)) + 16
    draw.line(
        (
            line_x,
            center_y,
            PANEL_WIDTH - PANEL_PADDING - 18,
            center_y,
        ),
        fill=DIVIDER,
        width=1,
    )
    return y + CHILD_SKILL_HEADER_HEIGHT


def _draw_skill(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    panel: _SkillPanel,
    element_color: tuple[int, int, int, int],
    y: int,
) -> int:
    height = _skill_height(panel)
    extend_level = get_skill_extend_level(panel.level)
    progress_text = f"Lv.{panel.level}"
    if extend_level > 0:
        progress_text = f"{progress_text} · 小技能 {extend_level}/2"
    data_y = _draw_panel_header(
        image,
        draw,
        panel.skill.name,
        progress_text,
        element_color,
        SECONDARY_TEXT,
        y,
    )
    data_y += PANEL_BODY_GAP

    data_y = _draw_data_rows(
        image,
        draw,
        _build_skill_metrics(panel.skill),
        element_color,
        VALUE_TEXT,
        data_y,
    )
    for child in panel.children:
        data_y += CHILD_SKILL_TOP_GAP
        data_y = _draw_child_skill_header(
            draw,
            child.name,
            element_color,
            data_y,
        )
        data_y = _draw_data_rows(
            image,
            draw,
            _build_skill_metrics(child),
            element_color,
            VALUE_TEXT,
            data_y,
        )
    return y + height


def _success_height(
    lineup_rows: list[list[_LineupItem]],
    attributes: list[_AttributeMetric],
    weapons: list[_WeaponMetric],
    skill_panels: list[_SkillPanel],
) -> int:
    height = PANEL_PADDING + HEADER_HEIGHT + LINEUP_TOP_GAP
    height += len(lineup_rows) * LINEUP_ROW_HEIGHT
    height += max(0, len(lineup_rows) - 1) * LINEUP_ROW_GAP
    height += SECTION_GAP + PANEL_HEADER_HEIGHT + PANEL_BODY_GAP
    attribute_rows = (len(attributes) + DATA_COLUMNS - 1) // DATA_COLUMNS
    height += attribute_rows * DATA_ROW_HEIGHT
    if weapons:
        height += PANEL_BODY_GAP + WEAPON_FOOTER_HEIGHT
    height += sum(SECTION_GAP + _skill_height(panel) for panel in skill_panels)
    height += PANEL_PADDING
    return height


def _draw_success(
    build: RoleDamageBuild,
    calculation: CharacterCalculateData,
) -> Image.Image:
    lineup_rows = _layout_lineup(_build_lineup(build))
    attributes = _build_attribute_metrics(
        calculation.base_attribute,
        calculation.final_attribute,
    )
    weapons = _build_weapon_metrics(build, calculation)
    skill_panels = _build_skill_panels(build, calculation.skills)
    height = _success_height(
        lineup_rows,
        attributes,
        weapons,
        skill_panels,
    )
    image = Image.new("RGBA", (PANEL_WIDTH, height), (0, 0, 0, 0))
    _draw_round_rect(
        image,
        (0, 0, PANEL_WIDTH, height),
        10,
        PANEL_FILL,
    )
    draw = ImageDraw.Draw(image)
    y = _draw_header(image, draw, build)
    y = _draw_lineup(draw, lineup_rows, y)

    y += SECTION_GAP
    y = _draw_panel_header(
        image,
        draw,
        "角色属性",
        "基础 → 最终",
        HEADER_TEXT,
        SECONDARY_TEXT,
        y,
    )
    y += PANEL_BODY_GAP
    y = _draw_data_rows(
        image,
        draw,
        attributes,
        DATA_TEXT,
        VALUE_TEXT,
        y,
    )
    if weapons:
        y += PANEL_BODY_GAP
        y = _draw_weapon_footer(image, draw, weapons, y)

    element_color = ELEMENT_TEXT_COLORS[build.role_detail.elementName]
    for panel in skill_panels:
        y += SECTION_GAP
        y = _draw_skill(
            image,
            draw,
            panel,
            element_color,
            y,
        )
    return image


def _draw_error(
    build: RoleDamageBuild,
    message: str,
) -> Image.Image:
    lineup_rows = _layout_lineup(_build_lineup(build))
    height = (
        PANEL_PADDING
        + HEADER_HEIGHT
        + LINEUP_TOP_GAP
        + len(lineup_rows) * LINEUP_ROW_HEIGHT
        + max(0, len(lineup_rows) - 1) * LINEUP_ROW_GAP
        + SECTION_GAP
        + PANEL_HEADER_HEIGHT
        + PANEL_BODY_GAP
        + DATA_ROW_HEIGHT
        + PANEL_PADDING
    )
    image = Image.new("RGBA", (PANEL_WIDTH, height), (0, 0, 0, 0))
    _draw_round_rect(
        image,
        (0, 0, PANEL_WIDTH, height),
        10,
        PANEL_FILL,
    )
    draw = ImageDraw.Draw(image)
    y = _draw_header(image, draw, build)
    y = _draw_lineup(draw, lineup_rows, y)
    y += SECTION_GAP
    y = _draw_panel_header(
        image,
        draw,
        "计算状态",
        None,
        HEADER_TEXT,
        SECONDARY_TEXT,
        y,
    )
    y += PANEL_BODY_GAP
    _draw_row_surface(
        image,
        (
            PANEL_PADDING,
            y,
            PANEL_WIDTH - PANEL_PADDING,
            y + DATA_ROW_HEIGHT,
        ),
        0,
    )
    draw.text(
        (PANEL_WIDTH // 2, y + DATA_ROW_HEIGHT // 2),
        message,
        VALUE_TEXT,
        dna_font_24,
        "mm",
    )
    return image


def draw_role_damage_section(
    build: RoleDamageBuild,
    response: DNAApiResp[CharacterCalculateData],
) -> Image.Image:
    if not response.is_success:
        return _draw_error(build, response.msg)
    if response.data is None:
        raise RuntimeError("伤害计算成功响应缺少 data")
    return _draw_success(build, response.data)
