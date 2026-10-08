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
from typing import TYPE_CHECKING
from dataclasses import field, dataclass

from ..dna_sdk.build import SdkBuild
from .local_attribute import (
    AttrContext,
    _role_element_cn,
    compute_attr_context,
)
from ..dna_sdk.tables import SKILL_MAX_LEVEL

if TYPE_CHECKING:
    from PIL import Image

    from ..utils.api.model import RoleDetail, WeaponDetail

from gsuid_core.logger import logger


@dataclass(slots=True)
class LocalSkillPanel:
    """单个技能的字段面板（名称 + 显示等级 + 已缩放的字段行）"""

    名称: str
    显示等级: int
    rows: list[tuple[str, str]] = field(default_factory=list)


def _fmt_field(field: dict) -> str:
    """字段显示值：格式模板优先，否则按名称语义选单位"""
    value = field.get("值")
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

    name = field.get("名称") or ""
    if "半径" in name:
        return f"{value:.1f}米"
    if "时间" in name or name in ("延迟", "卡肉", "取消", "连段"):
        return f"{value:.2f}秒"
    if "神智消耗" in name or name.endswith("神智回复"):
        return f"{value:g}"
    if any(key in name for key in ("点数", "层数", "等级", "数量")):
        return f"{value:g}"
    return fmt_pct(value)


def build_local_skill_panels(
    build: SdkBuild,
    ctx: AttrContext,
) -> list[LocalSkillPanel]:
    """本地结算全部技能字段（引擎 skill_fields，显示等级取官方等级）。"""
    role = build.role
    panels: list[LocalSkillPanel] = []
    for skill in role.skills:
        fields = build.engine.skill_fields(skill.skillName)
        if not fields:
            continue
        level = max(1, min(SKILL_MAX_LEVEL, skill.level))
        panels.append(
            LocalSkillPanel(
                名称=skill.skillName,
                显示等级=level,
                rows=[(f.get("名称") or "", _fmt_field(f)) for f in fields],
            )
        )
    if not panels:
        logger.warning(f"[DNA 面板] 角色 {role.charName} 无可结算的技能字段（数据包未收录？）")
    return panels


def draw_local_damage_section(
    build: SdkBuild,
    ctx: AttrContext | None = None,
) -> Image.Image:
    """绘制本地伤害计算区块：角色属性（基础 → 最终）+ 三类武器伤害 + 技能字段面板。"""
    from PIL import Image, ImageDraw

    from .damage_renderer import (
        DATA_TEXT,
        PANEL_FILL,
        VALUE_TEXT,
        HEADER_TEXT,
        PANEL_WIDTH,
        SECTION_GAP,
        DATA_COLUMNS,
        HEADER_HEIGHT,
        PANEL_PADDING,
        PANEL_BODY_GAP,
        SECONDARY_TEXT,
        DATA_ROW_HEIGHT,
        ELEMENT_TEXT_COLORS,
        PANEL_HEADER_HEIGHT,
        WEAPON_FOOTER_HEIGHT,
        _WeaponMetric,
        _draw_data_rows,
        _AttributeMetric,
        _draw_round_rect,
        _draw_panel_header,
        _draw_weapon_footer,
        _draw_header_surface,
    )
    from .local_weapon_damage import compute_weapon_damage
    from ..utils.fonts.dna_fonts import dna_font_22, dna_font_30
    from .local_weapon_attribute import resolve_inherit_source

    role_detail = build.role
    weapons = build.weapons
    close_weapon_detail = weapons.get("close")
    ranged_weapon_detail = weapons.get("ranged")
    con_weapon_detail = weapons.get("con")
    if ctx is None:
        ctx = compute_attr_context(build)
    panels = build_local_skill_panels(build, ctx)

    # 角色属性：基础（官方 attribute 裸值）→ 最终（本地计算）
    attr = role_detail.attribute
    base_rate = {
        "技能威力": attr.skillIntensity,
        "技能范围": attr.skillRange,
        "技能耐久": attr.skillSustain,
        "技能效益": attr.skillEfficiency,
    }
    base_map = {
        "攻击": attr.atk,
        "生命": attr.maxHp,
        "护盾": attr.maxES,
        "防御": attr.defense,
        "神智": attr.maxSp,
    }
    final_rate = {
        "技能威力": f"{ctx.tt['技能威力'] * 100:.0f}%",
        "技能范围": f"{ctx.tt['技能范围'] * 100:.0f}%",
        "技能耐久": f"{ctx.tt['技能耐久'] * 100:.0f}%",
        "技能效益": f"{ctx.tt['技能效益'] * 100:.0f}%",
    }
    final_rate["昂扬"] = f"{ctx.bonus.rate.get('昂扬', 0.0):.0f}%"
    final_rate["背水"] = f"{ctx.bonus.rate.get('背水', 0.0):.0f}%"
    # 充盈威力 0 起始（TS：totalFullness 从 0 累加，界面 val*100；+1 只在充盈伤害乘区现用）
    fullness = ctx.bonus.rate.get("充盈威力", 0.0) + ctx.bonus.extra.get("充盈威力", 0.0)
    final_rate["充盈威力"] = f"{fullness:.0f}%"

    def _base_num(name: str) -> str:
        return f"{base_map[name]:,.2f}"

    def _final_num(name: str) -> str:
        v = ctx.final_main.get(name)
        return f"{v:,.1f}" if v is not None else "-"

    def _base_rate(name: str) -> str:
        raw = base_rate[name].removesuffix("%")
        return f"{float(raw):.0f}%" if raw.replace(".", "", 1).isdigit() else "100%"

    elem_cn = _role_element_cn(role_detail)
    atk_label = f"{elem_cn}属性攻击" if elem_cn else "攻击"
    ordered = [
        (atk_label, _base_num("攻击"), _final_num("攻击")),
        ("生命", _base_num("生命"), _final_num("生命")),
        ("护盾", _base_num("护盾"), _final_num("护盾")),
        ("防御", _base_num("防御"), _final_num("防御")),
        ("最大神智", _base_num("神智"), _final_num("神智")),
        ("技能威力", _base_rate("技能威力"), final_rate["技能威力"]),
        ("技能范围", _base_rate("技能范围"), final_rate["技能范围"]),
        ("技能耐久", _base_rate("技能耐久"), final_rate["技能耐久"]),
        ("技能效益", _base_rate("技能效益"), final_rate["技能效益"]),
        ("充盈威力", "0%", final_rate["充盈威力"]),
        ("昂扬", "0%", final_rate["昂扬"]),
        ("背水", "0%", final_rate["背水"]),
    ]
    attr_metrics = [_AttributeMetric(label=name, value=f"{base} → {final}") for name, base, final in ordered]

    # 三类武器伤害（近战/远程/同律）：本地期望伤害（dna-builder 口径，打生命木桩130）
    # inherit 型同律武器按被继承的近战/远程武器结算
    con_inherit_slot: str | None = None
    if con_weapon_detail is not None:
        inherit_detail = resolve_inherit_source(
            con_weapon_detail, role_detail, close_weapon_detail, ranged_weapon_detail)
        if inherit_detail is close_weapon_detail:
            con_inherit_slot = "close"
        elif inherit_detail is ranged_weapon_detail:
            con_inherit_slot = "ranged"
    weapon_metrics: list[_WeaponMetric] = []
    for label, slot, inherit_slot in (
        ("近战", "close", None),
        ("远程", "ranged", None),
        ("同律", "con", con_inherit_slot),
    ):
        weapon_detail = weapons.get(slot)
        if weapon_detail is None:
            continue
        damage = compute_weapon_damage(build, slot, ctx, inherit_slot)
        value = f"{damage:,.0f}" if damage is not None else "无法计算"
        weapon_metrics.append(_WeaponMetric(label=label, name=weapon_detail.name, value=value))

    skill_panels = [
        (
            panel.名称,
            panel.显示等级,
            [_AttributeMetric(label=label, value=value) for label, value in panel.rows],
        )
        for panel in panels
    ]

    element_color = ELEMENT_TEXT_COLORS.get(role_detail.elementName, HEADER_TEXT)

    def _row_count(metrics: list[_AttributeMetric]) -> int:
        return max(1, (len(metrics) + DATA_COLUMNS - 1) // DATA_COLUMNS)

    # 高度与绘制逐段一一对应，不再在面板底部留空
    height = PANEL_PADDING + HEADER_HEIGHT
    height += SECTION_GAP + PANEL_HEADER_HEIGHT + PANEL_BODY_GAP + _row_count(attr_metrics) * DATA_ROW_HEIGHT
    if weapon_metrics:
        height += PANEL_BODY_GAP + WEAPON_FOOTER_HEIGHT
    for _, _, rows in skill_panels:
        height += SECTION_GAP + PANEL_HEADER_HEIGHT + PANEL_BODY_GAP + _row_count(rows) * DATA_ROW_HEIGHT
    height += PANEL_PADDING

    image = Image.new("RGBA", (PANEL_WIDTH, max(80, height)), (0, 0, 0, 0))
    _draw_round_rect(image, (0, 0, PANEL_WIDTH, image.height), 10, PANEL_FILL)
    draw = ImageDraw.Draw(image)

    # 主标题：渐变底纹 + 金色竖条
    y = PANEL_PADDING
    _draw_header_surface(
        image,
        (PANEL_PADDING, y, PANEL_WIDTH - PANEL_PADDING, y + HEADER_HEIGHT),
    )
    draw.rectangle((PANEL_PADDING + 16, y + 20, PANEL_PADDING + 20, y + 44), fill=HEADER_TEXT)
    draw.text(
        (PANEL_PADDING + 34, y + HEADER_HEIGHT // 2),
        "伤害计算",
        HEADER_TEXT,
        dna_font_30,
        "lm",
    )
    draw.text(
        (PANEL_WIDTH - PANEL_PADDING - 16, y + HEADER_HEIGHT // 2),
        f"角色 {role_detail.charName}",
        VALUE_TEXT,
        dna_font_22,
        "rm",
    )
    y += HEADER_HEIGHT

    # 角色属性：基础 → 最终
    y += SECTION_GAP
    y = _draw_panel_header(image, draw, "角色属性", "基础 → 最终", HEADER_TEXT, SECONDARY_TEXT, y)
    y += PANEL_BODY_GAP
    y = _draw_data_rows(image, draw, attr_metrics, DATA_TEXT, VALUE_TEXT, y)

    # 三类武器伤害（近战/远程/同律）
    if weapon_metrics:
        y += PANEL_BODY_GAP
        y = _draw_weapon_footer(image, draw, weapon_metrics, y)

    # 技能面板
    for name, level, rows in skill_panels:
        y += SECTION_GAP
        y = _draw_panel_header(image, draw, f"“{name}”", f"Lv.{level}", element_color, SECONDARY_TEXT, y)
        y += PANEL_BODY_GAP
        y = _draw_data_rows(image, draw, rows, element_color, VALUE_TEXT, y)

    return image


__all__ = ["LocalSkillPanel", "build_local_skill_panels", "draw_local_damage_section"]
