"""三类武器伤害本地计算 —— 移植 dna-builder ``CharBuild.calculateWeaponDamage``

用途
----
``draw_local_damage_section`` 的「近战 / 远程 / 同律」三列展示该武器**一次攻击的
期望伤害**（对齐 dna-builder 伤害页 ``expectedDamage`` 的口径）。

口径（2026-10-08 与用户确认：按 dna-builder，打默认木桩）
--------------------------------------------------------
- 敌人固定为 dna-builder 的默认目标 **生命木桩130**：``def=130``、等级 80、
  抗性 0、血量类型「生命」、无护盾；无环境增益、无克制、无失衡。
- 血量百分比 100%（昂扬满额生效、背水不生效），见 ``DEFAULT_HP_PERCENT``。
- **不含防御乘区** —— 与 dna-builder 界面的 ``expectedDamage`` 一致
  （它把防御放在 ``calculateRandomDamage`` 里）。木桩130 / 角色80 的防御乘区为
  ``1 − 130/(300+130) ≈ 0.6977``。
- **属性穿透**取自角色侧汇总（``AttrContext.bonus.extra``，含角色加成、角色槽
  MOD 与近战/远程武器自身的「加成」），按 ``max(0, 1 + 属性穿透)`` 整体相乘
  （dna-builder ``CharBuild.ts:2349`` 的 ``resistancePenetration``）。
- 数据包目前**没有**「元素增伤 / 物理增伤 / 武器伤害 / 无视防御 / 失衡易伤 /
  转xx」这些键，公式保留结构但取 0/1，将来数据包补齐即自动生效。

公式（无转换子集，dna-builder ``CharBuild.ts:2298-2465``）
----------------------------------------------------------
``总攻击 = 角色攻击 + 武器攻击``；物理分量占比 = 武器攻击/总攻击，
元素分量占比 = 角色攻击/总攻击 × (1 − 敌人抗性)；灾厄伤害类型整份转物理分量。

``期望伤害 = Σ分量 × (1 + 触发倍率 × min(1, 触发率)) × 增伤乘区
             × 暴击期望 × 昂扬背水乘区 × 独立增伤 × 追加伤害 × 属性穿透``

``武器伤害 = 期望伤害 × 总攻击``

其中「触发倍率」只在武器伤害类型**命中敌人当前血量类型**时才有值
（血量类型「生命」↔ 伤害类型「贯穿」，系数 0.5），灾厄类型需敌人有抗性才触发。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..dna_mod import dob_loader
from ..utils.api.model import Mode, RoleDetail, WeaponDetail
from .local_weapon_attribute import resolve_weapon_panel, resolve_weapon_record

if TYPE_CHECKING:
    from .local_attribute import AttrContext

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

# 该武器槽 mod 的伤害相关加成键（小数；数据包有的键已覆盖，其余为 0）
_DAMAGE_BONUS_KEYS = (
    "增伤",
    "元素增伤",
    "物理增伤",
    "武器伤害",
    "独立增伤",
    "追加伤害",
    "触发倍率",
)


def collect_weapon_damage_bonus(modes: list[Mode]) -> dict[str, float]:
    """汇总某武器槽 mod 的伤害相关加成（小数，多来源相加）

    与 ``local_weapon_attribute.collect_weapon_bonus`` 同源，但保留伤害乘区键
    （增伤 / 独立增伤 / 追加伤害 / 触发倍率 …），供武器伤害结算使用。
    """
    out: dict[str, float] = {key: 0.0 for key in _DAMAGE_BONUS_KEYS}
    for mode in modes:
        if mode.id is None or mode.id <= 0:
            continue
        attrs = dob_loader.get_mod_attrs(mode.id, mode.level, mode.quality)
        if not attrs:
            continue
        for key in _DAMAGE_BONUS_KEYS:
            value = attrs.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[key] += float(value)
    return out


def _trigger_multiplier(damage_type: str | None, trigger_bonus: float) -> float:
    """触发倍率加成（dna-builder ``calculateWeaponDamage.getTriggerMultiplier``）

    只有武器伤害类型命中敌人**当前血量类型**时才生效：
    生命 ↔ 贯穿（系数 0.5）、护盾 ↔ 切割（1）、战姿 ↔ 震荡（1）；
    灾厄类型需敌人存在抗性才触发，木桩抗性为 0 → 恒 0。
    """
    if damage_type == "灾厄":
        return (1.0 + trigger_bonus) if ENEMY_RESISTANCE != 0 else 0.0
    if damage_type is not None and damage_type == HP_TYPE_DAMAGE.get(ENEMY_HP_TYPE):
        return HP_TYPE_COEFFICIENTS[ENEMY_HP_TYPE] + trigger_bonus
    return 0.0


def compute_weapon_damage(
    weapon_detail: WeaponDetail,
    role_detail: RoleDetail,
    ctx: AttrContext,
    inherit_from: WeaponDetail | None = None,
) -> float | None:
    """该武器一次攻击的期望伤害（口径见模块 docstring）；数据不足返回 None

    ``ctx`` 为 ``local_attribute.AttrContext``（用其 ``final_main`` 取角色攻击、
    ``bonus.extra`` 取增伤/独立增伤、``bonus.rate`` 取昂扬/背水）。
    """
    char_atk = ctx.final_main.get("攻击")
    if not isinstance(char_atk, (int, float)) or isinstance(char_atk, bool) or char_atk <= 0:
        return None

    panel = resolve_weapon_panel(weapon_detail, role_detail, ctx.bonus, inherit_from)
    weapon_atk = panel.attack
    if weapon_atk is None or weapon_atk <= 0:
        return None

    total_attack = float(char_atk) + float(weapon_atk)

    # 伤害类型取被继承武器（dna-builder syncSkillWeaponDamageType）；
    # atk=all 判定留在同律武器自己的记录上
    skill_record, _is_skill = resolve_weapon_record(weapon_detail, role_detail)
    damage_record, _ = resolve_weapon_record(inherit_from or weapon_detail, role_detail)
    damage_type: str | None = None
    inherit_all = False
    if skill_record is not None:
        inherit_all = bool(skill_record.get("inherit")) and skill_record.get("atk") == "all"
    if damage_record is not None:
        damage_type = damage_record.get("伤害类型")

    # ── 分量占比（灾厄整份转物理；inherit+all 整份元素）──
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

    # ── 武器面板数值（角色侧 + 武器自身 + 该武器槽 mod 都已计入）──
    crit_rate = float(panel.cri)
    crit_damage = float(panel.crd)
    trigger_rate = min(1.0, max(0.0, float(panel.trigger)))

    # 继承型同律武器复用被继承武器的面板，其伤害词条也从被继承武器读取
    # （dna-builder calculateWeaponDamage 里 weapon 已被换成被继承的那把）
    damage_mods = (inherit_from or weapon_detail).modes
    weapon_damage_bonus = collect_weapon_damage_bonus(damage_mods)
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

    # ── 增伤乘区（元素/物理分量分别加算）──
    extra = ctx.bonus.extra
    char_increase = float(extra.get("增伤", 0.0)) / 100
    weapon_increase = weapon_damage_bonus["增伤"]
    weapon_damage_inc = float(extra.get("武器伤害", 0.0)) / 100 + weapon_damage_bonus["武器伤害"]
    element_increase = float(extra.get("元素增伤", 0.0)) / 100 + weapon_damage_bonus["元素增伤"]
    physical_increase = float(extra.get("物理增伤", 0.0)) / 100 + weapon_damage_bonus["物理增伤"]
    damage_increase_base = 1.0 + char_increase + weapon_increase + weapon_damage_inc

    def _part_increase(settles_element: bool) -> float:
        return damage_increase_base + (element_increase if settles_element else physical_increase)

    expected_trigger_part = sum(
        ratio * (1 + add * trigger_rate) * _part_increase(settles_element) for ratio, add, settles_element in parts
    )

    # ── 暴击期望 ──
    crit_expected = 1.0 + crit_rate * (crit_damage - 1.0)

    # ── 昂扬 / 背水乘区 ──
    rate = ctx.bonus.rate
    hp_percent = max(0.0, min(1.0, DEFAULT_HP_PERCENT))
    boost = float(rate.get("昂扬", 0.0)) / 100
    desperate = float(rate.get("背水", 0.0)) / 100
    boost_multiplier = 1.0 + boost * hp_percent
    desperate_hp = max(0.25, min(1.0, hp_percent))
    desperate_multiplier = 1.0 + 4.0 * desperate * (1 - desperate_hp) * (1.5 - desperate_hp)
    hp_more = boost_multiplier * desperate_multiplier

    # ── 独立增伤（乘法聚合）× 追加伤害 × 属性穿透 ──
    char_independent = float(extra.get("独立增伤", 0.0)) / 100
    independent = (1.0 + char_independent) * (1.0 + weapon_damage_bonus["独立增伤"])
    # 追加伤害是「角色作用域」属性：dna-builder 用 getTotalBonus("追加伤害")（默认前缀「角色」），
    # 而 sumModsFromTable 对不在 attrAllowCharToWeapon 白名单里的属性只取 modsByScope["角色"]，
    # 即「角色自带加成 + 近战/远程武器自身加成 + 角色槽 MOD」，**不含武器槽 MOD**。
    char_additional = float(extra.get("追加伤害", 0.0)) / 100
    additional_damage = 1.0 + char_additional
    # 属性穿透对所有结算类型整体相乘（dna-builder CharBuild.ts:2349 resistancePenetration）
    penetration = max(0.0, 1.0 + float(extra.get("属性穿透", 0.0)) / 100)
    other_more = independent * additional_damage * penetration

    expected = expected_trigger_part * crit_expected * hp_more * other_more
    return expected * total_attack


__all__ = [
    "DEFAULT_HP_PERCENT",
    "ENEMY_NAME",
    "collect_weapon_damage_bonus",
    "compute_weapon_damage",
]
