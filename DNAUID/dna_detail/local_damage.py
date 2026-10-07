"""纯本地伤害计算 —— 替代官方 H5 伤害接口，按 DOB 数据包直接结算技能面板

口径全部移植自 dna-builder（逐项与官方 H5 面板核对一致）：

1. **技能等级**：官方接口返回的等级 + 溯源「[技能名]等级+N」加成，封顶 12 级
   （官方面板显示 Lv.10、数值按 12 级结算，即含溯源加成）。
2. **字段取值**：逐档数组按等级下标取值（LeveledSkill）。
3. **字段缩放**（getFieldsWithAttr）：
   - 字段的 ``影响`` 声明吃哪个乘区（可逗号并列）：
     伤害类 × 技能威力、半径 × 技能范围、持续时间 × 技能耐久；
   - 名称含「伤害」的字段先 ×(1+技能倍率乘数)+技能倍率加数；
   - 「每秒神智消耗」随技能耐久 **相除**（持续变长消耗变慢）；
   - 技能效益参与时按 (2-效益)（与耐久并列时 ×max(0.25,(2-效益)/耐久)）；
   - 「神智消耗」向上取整。
4. **显示**（formatSkillProp + 官方单位语义）：
   神智消耗/回复、点数/层数/等级/数量 → 原值；
   半径 → 米（1 位小数）；时间/持续 → 秒（2 位小数）；其余 → 百分比（1 位小数）；
   带 ``格式`` 模板的字段按占位符顺序代入 值/值2。
"""

from __future__ import annotations

import re
from dataclasses import field, dataclass

from ..dna_mod import dob_loader
from .local_attribute import AttrContext, compute_attr_context

try:
    from gsuid_core.logger import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("dna_local_damage")


@dataclass(slots=True)
class LocalSkillPanel:
    """单个技能的字段面板（名称 + 显示等级 + 已缩放的字段行）"""

    名称: str
    显示等级: int
    rows: list[tuple[str, str]] = field(default_factory=list)


def _fmt_num(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _fmt_field(field: dict) -> str:
    """字段显示值：格式模板优先，否则按名称语义选单位"""
    value = field["值"]
    value2 = field.get("值2")
    fmt = field.get("格式")

    def fmt_pct(v: float) -> str:
        return f"{v * 100:.1f}%"

    if fmt:
        index = 0

        def _sub(match: re.Match) -> str:
            nonlocal index
            token = match.group(0)
            v = value if index == 0 else (value2 if value2 is not None else value)
            if "%" in token:
                index += 1
                return fmt_pct(v)
            # 占位符后紧跟的单位字符决定小数位：米 1 位（13.0米），秒 2 位（29.64秒）；
            # 其余（如 神智消耗 的 "{}"）走原值裁剪（与 dna-builder format1 口径一致）
            unit = fmt[match.end() : match.end() + 1]
            index += 1
            if unit == "米":
                return f"{v:.1f}"
            if unit == "秒":
                return f"{v:.2f}"
            text = f"{v:.2f}".rstrip("0").rstrip(".")
            return text or "0"

        return re.sub(r"\{%?\}", _sub, fmt)

    name = field["名称"]
    if "半径" in name:
        return f"{value:.1f}米"
    if "时间" in name or name in ("延迟", "卡肉", "取消", "连段"):
        return f"{value:.2f}秒"
    if "神智消耗" in name or name.endswith("神智回复"):
        return f"{value:g}"
    if any(key in name for key in ("点数", "层数", "等级", "数量")):
        return f"{value:g}"
    return fmt_pct(value)


def _resolve_levels(role_detail) -> dict[str, int]:
    """官方接口技能表 → {技能名: 结算等级}

    skills[].level 已含溯源加成（damage_service 发送官方请求时正是减去
    溯源加成得到基础等级），直接作为结算等级，封顶 12 级。
    """
    levels: dict[str, int] = {}
    for skill in role_detail.skills or []:
        name, level = getattr(skill, "skillName", None), getattr(skill, "level", None)
        if not name or not isinstance(level, int) or level <= 0:
            continue
        levels[name] = max(1, min(dob_loader.SKILL_MAX_LEVEL, level))
    return levels


def build_local_skill_panels(
    role_detail,
    ctx: AttrContext,
) -> list[LocalSkillPanel]:
    """本地结算全部技能字段（替代官方接口的 skills 返回）"""
    pack_skills = {s["名称"]: s for s in dob_loader.get_char_skills(role_detail.charId)}
    levels = _resolve_levels(role_detail)

    panels: list[LocalSkillPanel] = []
    for skill in role_detail.skills or []:
        name = getattr(skill, "skillName", None)
        pack = pack_skills.get(name)
        if not name or not pack or not pack.get("字段"):
            continue
        level = levels.get(name, 10)
        fields = dob_loader.resolve_skill_fields(pack, level, ctx.tt)
        panels.append(
            LocalSkillPanel(
                名称=name,
                显示等级=level,
                rows=[(f["名称"], _fmt_field(f)) for f in fields],
            )
        )
    if not panels:
        logger.warning(f"[DNA 面板] 角色 {role_detail.charName} 无可结算的技能字段（数据包未收录？）")
    return panels


def draw_local_damage_section(role_detail, con_weapon_detail=None):
    """绘制本地伤害计算区块：角色属性（基础 → 最终）+ 技能字段面板

    样式复用 damage_renderer 的官方面板绘制助手，口径与官方 H5 一致。
    """
    from PIL import Image, ImageDraw

    from .damage_renderer import (
        BODY_FILL,
        PANEL_FILL,
        VALUE_TEXT,
        HEADER_FILL,
        HEADER_TEXT,
        PANEL_WIDTH,
        DATA_COLUMNS,
        PANEL_PADDING,
        PANEL_BODY_GAP,
        SECONDARY_TEXT,
        DATA_ROW_HEIGHT,
        PANEL_HEADER_HEIGHT,
        _draw_round_rect,
    )
    from ..utils.fonts.dna_fonts import dna_font_22, dna_font_24

    ctx = compute_attr_context(role_detail, con_weapon_detail)
    panels = build_local_skill_panels(role_detail, ctx)

    # 角色属性：基础（官方 attribute 裸值）→ 最终（本地计算）
    attr = role_detail.attribute
    base_rate = {
        "技能威力": getattr(attr, "skillIntensity", "100%"),
        "技能范围": getattr(attr, "skillRange", "100%"),
        "技能耐久": getattr(attr, "skillSustain", "100%"),
        "技能效益": getattr(attr, "skillEfficiency", "100%"),
    }
    base_map = {
        "攻击": getattr(attr, "atk", None),
        "生命": getattr(attr, "maxHp", None),
        "护盾": getattr(attr, "maxES", None),
        "防御": getattr(attr, "defense", None),
        "最大神志": getattr(attr, "maxSp", None),
    }
    final_rate = {
        "技能威力": f"{ctx.tt['技能威力'] * 100:.0f}%",
        "技能范围": f"{ctx.tt['技能范围'] * 100:.0f}%",
        "技能耐久": f"{ctx.tt['技能耐久'] * 100:.0f}%",
        "技能效益": f"{ctx.tt['技能效益'] * 100:.0f}%",
    }
    final_rate["昂扬"] = f"{ctx.bonus.rate.get('昂扬', 0.0):.0f}%"
    final_rate["背水"] = f"{ctx.bonus.rate.get('背水', 0.0):.0f}%"

    def _base_num(name: str) -> str:
        v = base_map.get(name)
        return f"{float(v):,.2f}" if v is not None else "-"

    def _final_num(name: str) -> str:
        v = ctx.final_main.get(name)
        return f"{v:,.1f}" if v is not None else "-"

    def _base_rate(name: str) -> str:
        raw = str(base_rate.get(name, "100%")).replace("%", "")
        try:
            return f"{float(raw):.0f}%"
        except ValueError:
            return "100%"

    ordered = [
        ("攻击", _base_num("攻击"), _final_num("攻击")),
        ("生命", _base_num("生命"), _final_num("生命")),
        ("护盾", _base_num("护盾"), _final_num("护盾")),
        ("防御", _base_num("防御"), _final_num("防御")),
        ("最大神志", _base_num("最大神志"), _final_num("最大神志")),
        ("技能威力", _base_rate("技能威力"), final_rate["技能威力"]),
        ("技能范围", _base_rate("技能范围"), final_rate["技能范围"]),
        ("技能耐久", _base_rate("技能耐久"), final_rate["技能耐久"]),
        ("技能效益", _base_rate("技能效益"), final_rate["技能效益"]),
        ("昂扬", "0%", final_rate["昂扬"]),
        ("背水", "0%", final_rate["背水"]),
    ]

    def _panel_height(row_count: int) -> int:
        return PANEL_HEADER_HEIGHT + PANEL_BODY_GAP + row_count * DATA_ROW_HEIGHT + PANEL_PADDING

    attr_rows = (len(ordered) + DATA_COLUMNS - 1) // DATA_COLUMNS
    height = _panel_height(attr_rows) + PANEL_BODY_GAP
    for panel in panels:
        height += _panel_height((len(panel.rows) + DATA_COLUMNS - 1) // DATA_COLUMNS) + PANEL_BODY_GAP

    image = Image.new("RGBA", (PANEL_WIDTH, max(80, height)), (0, 0, 0, 0))
    _draw_round_rect(image, (0, 0, PANEL_WIDTH, image.height), 10, PANEL_FILL)
    draw = ImageDraw.Draw(image)

    def _draw_metrics(metrics: list[tuple[str, str]], y: int) -> int:
        row_count = (len(metrics) + DATA_COLUMNS - 1) // DATA_COLUMNS
        cell_width = (PANEL_WIDTH - PANEL_PADDING * 2) // DATA_COLUMNS
        for row in range(row_count):
            row_y = y + row * DATA_ROW_HEIGHT
            surface = Image.new("RGBA", (PANEL_WIDTH - PANEL_PADDING * 2, DATA_ROW_HEIGHT), BODY_FILL)
            image.alpha_composite(surface, (PANEL_PADDING, row_y))
            for column in range(DATA_COLUMNS):
                index = row * DATA_COLUMNS + column
                if index >= len(metrics):
                    continue
                label, value = metrics[index]
                draw.text(
                    (PANEL_PADDING + column * cell_width + 14, row_y + DATA_ROW_HEIGHT // 2),
                    label,
                    font=dna_font_22,
                    fill=SECONDARY_TEXT,
                    anchor="lm",
                )
                draw.text(
                    (PANEL_PADDING + (column + 1) * cell_width - 14, row_y + DATA_ROW_HEIGHT // 2),
                    value,
                    font=dna_font_22,
                    fill=VALUE_TEXT,
                    anchor="rm",
                )
        return y + row_count * DATA_ROW_HEIGHT

    y = PANEL_PADDING
    # 区块头
    draw.rectangle(
        (PANEL_PADDING, y, PANEL_WIDTH - PANEL_PADDING, y + PANEL_HEADER_HEIGHT - 12),
        fill=HEADER_FILL,
    )
    draw.text(
        (PANEL_PADDING + 14, y + (PANEL_HEADER_HEIGHT - 12) // 2),
        "伤害计算",
        font=dna_font_24,
        fill=HEADER_TEXT,
        anchor="lm",
    )
    draw.text(
        (PANEL_WIDTH - PANEL_PADDING - 14, y + (PANEL_HEADER_HEIGHT - 12) // 2),
        f"角色 {role_detail.charName}",
        font=dna_font_22,
        fill=SECONDARY_TEXT,
        anchor="rm",
    )
    y += PANEL_HEADER_HEIGHT + PANEL_BODY_GAP

    # 角色属性：基础 → 最终
    attr_metrics = [(name, f"{base} → {final}") for name, base, final in ordered]
    y = _draw_metrics(attr_metrics, y) + PANEL_BODY_GAP

    # 技能面板
    for panel in panels:
        header_h = PANEL_HEADER_HEIGHT - 12
        draw.rectangle((PANEL_PADDING, y, PANEL_WIDTH - PANEL_PADDING, y + header_h), fill=HEADER_FILL)
        draw.text(
            (PANEL_PADDING + 14, y + header_h // 2),
            f"“{panel.名称}”",
            font=dna_font_24,
            fill=HEADER_TEXT,
            anchor="lm",
        )
        draw.text(
            (PANEL_WIDTH - PANEL_PADDING - 14, y + header_h // 2),
            f"Lv.{panel.显示等级}",
            font=dna_font_22,
            fill=SECONDARY_TEXT,
            anchor="rm",
        )
        y += header_h + PANEL_BODY_GAP
        y = _draw_metrics(panel.rows, y) + PANEL_BODY_GAP

    return image


__all__ = ["LocalSkillPanel", "build_local_skill_panels", "draw_local_damage_section"]
