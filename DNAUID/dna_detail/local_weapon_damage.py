"""三类武器伤害本地计算 —— DNAUID 简化公式（dna-builder 口径的子集）+ 引擎输入。

- 敌人固定 dna-builder 默认目标「生命木桩130」：def=130、等级 80、抗性 0、
  血量类型「生命」；血量百分比 100%（昂扬满额、背水不生效）；
- 不含防御乘区（与 dna-builder 界面 expectedDamage 一致）；
- 角色项取引擎角色属性，同律/近战/远程武器项取引擎武器面板与槽位实例。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .local_attribute import AttrContext
from .local_weapon_attribute import (
    WeaponPanel,
    slot_damage_bonus,
    resolve_weapon_record,
)

if TYPE_CHECKING:
    from ..dna_sdk.build import SdkBuild
    from ..utils.api.model import RoleDetail, WeaponDetail

# ── 敌人：dna-builder 默认目标「生命木桩130」──────────────────
ENEMY_NAME = "生命木桩130"
ENEMY_DEF = 130.0
ENEMY_LEVEL = 80
ENEMY_RESISTANCE = 0.0
ENEMY_HP_TYPE = "生命"
ENEMY_HAS_SHIELD = False

# dna-builder CharBuild.hpTypeCoefficients / hpTypeDMG
HP_TYPE_COEFFICIENTS: dict[str, float] = {"生命": 0.5, "护盾": 1.0, "战姿": 1.0}
HP_TYPE_DAMAGE: dict[str, str] = {"生命": "贯穿", "护盾": "切割", "战姿": "震荡"}

# 昂扬/背水乘区用的血量百分比：1.0 = 满血（昂扬满额、背水不生效）
DEFAULT_HP_PERCENT = 1.0


def _trigger_multiplier(damage_type: str | None, trigger_bonus: float) -> float:
    """触发倍率加成：只有武器伤害类型命中敌人当前血量类型时才生效。"""
    if damage_type == "灾厄":
        return (1.0 + trigger_bonus) if ENEMY_RESISTANCE != 0 else 0.0
    if damage_type is not None and damage_type == HP_TYPE_DAMAGE.get(ENEMY_HP_TYPE):
        return HP_TYPE_COEFFICIENTS[ENEMY_HP_TYPE] + trigger_bonus
    return 0.0


def compute_weapon_damage(
    build: SdkBuild,
    slot: str,
    ctx: AttrContext,
    inherit_slot: str | None = None,
) -> float | None:
    """该武器一次攻击的期望伤害；数据不足返回 None。

    slot: close/ranged/con。inherit_slot 非空时按被继承武器结算。
    """
    char_atk = ctx.final_main.get("攻击")
    if not isinstance(char_atk, (int, float)) or isinstance(char_atk, bool) or char_atk <= 0:
        return None

    if inherit_slot is not None:
        panel_raw = build.engine.weapon_panel({"close": "melee", "ranged": "ranged"}.get(inherit_slot, inherit_slot))
        damage_slot = inherit_slot
    elif slot == "con":
        from .local_weapon_attribute import con_weapon_panel

        con = build.weapons.get("con")
        panel = con_weapon_panel(build, con) if con is not None else None
        panel_raw = (
            {"攻击": panel.attack, "暴击": panel.cri, "暴伤": panel.crd, "攻速": panel.speed, "触发": panel.trigger}
            if panel is not None and panel.attack is not None
            else None
        )
        damage_slot = "con"
    else:
        panel_raw = build.engine.weapon_panel({"close": "melee", "ranged": "ranged"}.get(slot, slot))
        damage_slot = slot
    if not panel_raw:
        return None
    weapon_atk = panel_raw.get("攻击")
    if not isinstance(weapon_atk, (int, float)) or weapon_atk <= 0:
        return None
    panel = WeaponPanel(
        attack=float(weapon_atk),
        cri=float(panel_raw.get("暴击") or 0.0),
        crd=float(panel_raw.get("暴伤") or 0.0),
        speed=float(panel_raw.get("攻速") or 0.0),
        trigger=float(panel_raw.get("触发") or 0.0),
    )

    total_attack = float(char_atk) + float(weapon_atk)

    role: RoleDetail = build.role
    weapon_detail: WeaponDetail | None = build.weapons.get(slot)
    inherit_detail: WeaponDetail | None = build.weapons.get(inherit_slot) if inherit_slot else None
    skill_record, _is_skill = resolve_weapon_record(weapon_detail, role) if weapon_detail is not None else (None, False)
    damage_record, _ = (
        resolve_weapon_record(inherit_detail or weapon_detail, role)
        if (inherit_detail or weapon_detail) is not None
        else (None, False)
    )
    damage_type: str | None = None
    inherit_all = False
    if skill_record is not None:
        inherit_all = bool(skill_record.get("inherit")) and skill_record.get("atk") == "all"
    if damage_record is not None:
        damage_type = damage_record.get("伤害类型")

    if damage_type == "灾厄" and not inherit_all:
        physical_ratio, element_ratio = 1.0, 0.0
    elif inherit_all:
        physical_ratio, element_ratio = 0.0, 1.0
    else:
        physical_ratio = float(weapon_atk) / total_attack
        element_ratio = float(char_atk) / total_attack

    resistance = max(0.0, 1.0 - ENEMY_RESISTANCE)
    elemental_part = element_ratio * resistance
    physical_base = physical_ratio

    crit_rate = float(panel.cri)
    crit_damage = float(panel.crd)
    trigger_rate = min(1.0, max(0.0, float(panel.trigger)))

    if damage_slot == "con":
        from .local_weapon_attribute import _con_mod_bonus_fractions

        con = build.weapons.get("con")
        fractions = _con_mod_bonus_fractions(con) if con is not None else {}
        weapon_damage_bonus = {
            k: float(fractions.get(k) or 0.0)
            for k in ("增伤", "元素增伤", "物理增伤", "武器伤害", "独立增伤", "追加伤害", "触发倍率")
        }
    else:
        weapon_damage_bonus = slot_damage_bonus(build, damage_slot)
    trigger_add = _trigger_multiplier(damage_type, weapon_damage_bonus["触发倍率"])

    parts: list[tuple[float, float, bool]] = []
    if inherit_all:
        if elemental_part > 0:
            parts.append((elemental_part, 0.0, True))
    else:
        if physical_base > 0:
            parts.append((physical_base, trigger_add, False))
        if elemental_part > 0:
            parts.append((elemental_part, 0.0, True))

    bonus = ctx.bonus
    char_increase = bonus.extra.get("增伤", 0.0) / 100
    weapon_increase = weapon_damage_bonus["增伤"]
    weapon_damage_inc = bonus.extra.get("武器伤害", 0.0) / 100 + weapon_damage_bonus["武器伤害"]
    element_increase = bonus.extra.get("元素增伤", 0.0) / 100 + weapon_damage_bonus["元素增伤"]
    physical_increase = bonus.extra.get("物理增伤", 0.0) / 100 + weapon_damage_bonus["物理增伤"]
    damage_increase_base = 1.0 + char_increase + weapon_increase + weapon_damage_inc

    def _part_increase(settles_element: bool) -> float:
        return damage_increase_base + (element_increase if settles_element else physical_increase)

    expected_trigger_part = sum(
        ratio * (1 + add * trigger_rate) * _part_increase(settles_element) for ratio, add, settles_element in parts
    )

    crit_expected = 1.0 + crit_rate * (crit_damage - 1.0)

    rate = bonus.rate
    hp_percent = max(0.0, min(1.0, DEFAULT_HP_PERCENT))
    boost = rate.get("昂扬", 0.0) / 100
    desperate = rate.get("背水", 0.0) / 100
    boost_multiplier = 1.0 + boost * hp_percent
    desperate_hp = max(0.25, min(1.0, hp_percent))
    desperate_multiplier = 1.0 + 4.0 * desperate * (1 - desperate_hp) * (1.5 - desperate_hp)
    hp_more = boost_multiplier * desperate_multiplier

    char_independent = bonus.extra.get("独立增伤", 0.0) / 100
    independent = (1.0 + char_independent) * (1.0 + weapon_damage_bonus["独立增伤"])
    char_additional = bonus.extra.get("追加伤害", 0.0) / 100
    additional_damage = 1.0 + char_additional
    penetration = max(0.0, 1.0 + bonus.extra.get("属性穿透", 0.0) / 100)
    other_more = independent * additional_damage * penetration

    expected = expected_trigger_part * crit_expected * hp_more * other_more
    return expected * total_attack


__all__ = [
    "DEFAULT_HP_PERCENT",
    "ENEMY_NAME",
    "compute_weapon_damage",
]
