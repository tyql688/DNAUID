from __future__ import annotations

import re
import math
from dataclasses import dataclass

from dna_builder_sdk.calc.damage import DamageContext

from gsuid_core.logger import logger

from . import records
from .build import DobBuild, WeaponSlot
from ..api.model import RoleDetail, WeaponDetail

SKILL_MAX_LEVEL = 12
_ELEMENTS = ("光", "暗", "水", "火", "雷", "风")
_MAIN_ATTRS = (("攻击", "攻击"), ("生命", "生命"), ("护盾", "护盾"), ("防御", "防御"), ("神智", "最大神智"))
# 率类属性是 1 起始倍率；范围/耐久/效益按游戏面板上限截断
_RATE_CAPS = {"技能威力": math.inf, "技能范围": 2.8, "技能耐久": 4.0, "技能效益": 1.75}
# 0 起始的百分比属性，面板固定显示
_ZERO_BASED = ("充盈威力", "昂扬", "背水")
# 有值才显示的隐藏属性
_HIDDEN_ATTRS = tuple(
    sorted(
        (
            "元素增伤",
            "物理增伤",
            "武器伤害",
            "独立增伤",
            "属性穿透",
            "无视防御",
            "技能无视防御",
            "追加伤害",
            "多重",
            "歧视",
            "物理",
            "触发倍率",
            "攻击范围",
            "技能倍率乘数",
            "技能倍率加数",
        )
    )
)
_PLACEHOLDER_RE = re.compile(r"\{%?\}")
# 数据包没收录的武器按空面板显示，攻击行显示「无法计算」
_EMPTY_PANEL = {"攻击": 0.0, "暴击": 0.0, "暴伤": 0.0, "攻速": 0.0, "触发": 0.0}


@dataclass(frozen=True, slots=True, kw_only=True)
class WeaponView:
    detail: WeaponDetail
    rows: list[tuple[str, str]]
    damage: float | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SkillView:
    name: str
    level: int
    rows: list[tuple[str, str]]


@dataclass(frozen=True, slots=True, kw_only=True)
class PanelView:
    """角色卡要显示的全部结算结果（已格式化）。"""

    attr_rows: list[tuple[str, str]]
    hidden_rows: list[tuple[str, str]]
    compare_rows: list[tuple[str, str, str]]
    weapons: dict[WeaponSlot, WeaponView]
    skills: list[SkillView]


def compute_panel(build: DobBuild) -> PanelView:
    """面板与伤害全部取引擎结算值，这里只负责挑选与格式化。"""
    engine = build.engine
    attrs = engine.calculate_weapon_attributes()
    rates = {key: min(attrs[key], cap) for key, cap in _RATE_CAPS.items()}
    damage_ctx = engine.damage_context(attrs)
    damage_types = {slot: info["伤害类型"] for slot, info in engine.weapons_info().items() if info}
    return PanelView(
        attr_rows=_attr_rows(build.role, attrs, rates),
        hidden_rows=_hidden_rows(attrs),
        compare_rows=_compare_rows(build.role, attrs, rates),
        weapons={
            slot: _weapon_view(build.role, slot, detail, attrs["攻击"], damage_ctx, damage_types.get(slot))
            for slot, detail in build.weapons.items()
        },
        skills=_skill_views(build),
    )


def _fmt_num(value: float) -> str:
    return f"{round(value):,}" if abs(value - round(value)) < 1e-6 else f"{value:,.1f}"


def _fmt_pct(percent: float) -> str:
    return f"{round(percent)}%" if abs(percent - round(percent)) < 1e-6 else f"{percent:.1f}%"


def _fmt_speed(value: float) -> str:
    if abs(value - round(value, 1)) < 1e-6:
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _atk_label(role: RoleDetail) -> str:
    element = next((name for name in _ELEMENTS if name in role.elementName), "")
    return f"{element}属性攻击" if element else "攻击"


def _main_label(role: RoleDetail, key: str, label: str) -> str:
    return _atk_label(role) if key == "攻击" else label


def _attr_rows(role: RoleDetail, attrs: dict, rates: dict[str, float]) -> list[tuple[str, str]]:
    rows = [(_main_label(role, key, label), _fmt_num(attrs[key])) for key, label in _MAIN_ATTRS]
    rows += [(key, _fmt_pct(rate * 100)) for key, rate in rates.items()]
    rows += [(key, _fmt_pct(attrs[key] * 100)) for key in _ZERO_BASED]
    return rows


def _hidden_rows(attrs: dict) -> list[tuple[str, str]]:
    hp, defense, shield, reduce = attrs["生命"], attrs["防御"], attrs["护盾"], attrs["减伤"]
    rows = [
        ("增伤", _fmt_pct(attrs["增伤"] * 100)),
        ("技能伤害", _fmt_pct(attrs["技能伤害"] * 100)),
        ("减伤", _fmt_pct(reduce * 100)),
    ]
    if hp > 0 and defense >= 0:
        ehp = (hp / (1 - defense / (300 + defense)) + shield) / (1 - reduce)
        rows.append(("有效生命", _fmt_num(ehp)))
    rows += [(key, _fmt_pct(attrs[key] * 100)) for key in _HIDDEN_ATTRS if abs(attrs.get(key, 0.0)) > 1e-11]
    return rows


def _base_rate(text: str) -> str:
    raw = text.removesuffix("%")
    return f"{float(raw):.0f}%" if raw.replace(".", "", 1).isdigit() else "100%"


def _compare_rows(role: RoleDetail, attrs: dict, rates: dict[str, float]) -> list[tuple[str, str, str]]:
    """伤害区块的「基础 → 最终」：基础取官方裸值，最终取引擎结算。"""
    base = role.attribute
    base_main = {"攻击": base.atk, "生命": base.maxHp, "护盾": base.maxES, "防御": base.defense, "神智": base.maxSp}
    base_rates = {
        "技能威力": base.skillIntensity,
        "技能范围": base.skillRange,
        "技能耐久": base.skillSustain,
        "技能效益": base.skillEfficiency,
    }
    rows = [
        (_main_label(role, key, label), f"{base_main[key]:,.2f}", f"{attrs[key]:,.1f}") for key, label in _MAIN_ATTRS
    ]
    rows += [(key, _base_rate(base_rates[key]), f"{rate * 100:.0f}%") for key, rate in rates.items()]
    rows += [(key, "0%", f"{attrs[key] * 100:.0f}%") for key in _ZERO_BASED]
    return rows


def _weapon_category(role: RoleDetail, slot: WeaponSlot, detail: WeaponDetail) -> str:
    """武器类型：官方字段优先，个别武器官方不返回时取数据包里的类别。"""
    if detail.elementName:
        return detail.elementName
    record = records.con_weapon_record(role.charId) if slot is WeaponSlot.SKILL else records.weapon_record(detail.id)
    return records.weapon_category(record) if record else "未知"


def _weapon_view(
    role: RoleDetail,
    slot: WeaponSlot,
    detail: WeaponDetail,
    char_attack: float,
    damage_ctx: DamageContext,
    damage_type: str | None,
) -> WeaponView:
    # 继承型同律武器的面板就是被继承武器的面板，由引擎处理
    panel = damage_ctx.panels.get(slot, _EMPTY_PANEL)
    attack = panel["攻击"]
    rows = [
        ("武器类型", _weapon_category(role, slot, detail)),
        (f"{damage_type}攻击" if damage_type else "攻击", f"{attack:,.2f}" if attack > 0 else "无法计算"),
        ("暴击率", _fmt_pct(panel["暴击"] * 100)),
        ("暴击伤害", _fmt_pct(panel["暴伤"] * 100)),
        ("攻击速度", _fmt_speed(panel["攻速"])),
        ("触发概率", _fmt_pct(panel["触发"] * 100)),
    ]
    # 引擎给的是期望伤害倍率（敌人为默认木桩、满血），乘总攻击即一次攻击的期望伤害
    damage = None
    if attack > 0 and char_attack > 0:
        damage = damage_ctx.get_damage(slot, None, None, None)["expectedDamage"] * (char_attack + attack)
    return WeaponView(detail=detail, rows=rows, damage=damage)


def _skill_views(build: DobBuild) -> list[SkillView]:
    views = [
        SkillView(
            name=skill.skillName,
            level=min(max(skill.level, 1), SKILL_MAX_LEVEL),
            rows=[(field["名称"], _fmt_field(field)) for field in fields],
        )
        for skill in build.role.skills
        if (fields := build.engine.skill_fields(skill.skillName))
    ]
    if not views:
        logger.warning(f"[DNA 面板] 角色 {build.role.charName} 没有可结算的技能字段")
    return views


def _fmt_field(field: dict) -> str:
    """技能字段显示值：有「格式」模板时依次代入 值/值2，否则按字段名选单位。"""
    value = field["值"]
    fmt = field.get("格式")
    if fmt:
        second = field.get("值2")
        values = iter([value])
        rest = value if second is None else second

        def _sub(match: re.Match[str]) -> str:
            number = next(values, rest)
            if "%" in match.group(0):
                return f"{number * 100:.1f}%"
            # 占位符后的单位决定小数位：米 1 位、秒 2 位，其余去掉末尾 0
            unit = fmt[match.end() : match.end() + 1]
            if unit == "米":
                return f"{number:.1f}"
            if unit == "秒":
                return f"{number:.2f}"
            return f"{number:.2f}".rstrip("0").rstrip(".") or "0"

        return _PLACEHOLDER_RE.sub(_sub, fmt)

    name = field["名称"]
    if "半径" in name:
        return f"{value:.1f}米"
    if "时间" in name or name in ("延迟", "卡肉", "取消", "连段"):
        return f"{value:.2f}秒"
    if "神智消耗" in name or name.endswith("神智回复") or any(key in name for key in ("点数", "层数", "等级", "数量")):
        return f"{value:g}"
    return f"{value * 100:.1f}%"
