"""武器（同律/近战/远程）属性面板计算 —— 全本地，不依赖官方计算接口

口径（移植自 dna-builder）：

1. **震荡攻击（基础攻击）**：数据包武器的 ``攻击`` 为 1 级白值，
   ``基础攻击 = 白值 × CommonLevelUp[等级-1]``（同律武器取角色数据包中的
   同律武器条目）；武器不在数据包内时显示「无法计算」。
2. **副属性（暴击率/暴击伤害/攻击速度/触发概率）**：与武器等级无关，
   ``基础值 × (1 + Σ mod加成%)``。
3. **魔之楔加成**：``dob_loader.get_weapon_mod_attrs``（键已映射为面板显示名：
   攻击 / 暴击率 / 暴击伤害 / 攻击速度 / 触发概率，值为百分比）。

已验证（莉兹贝尔 · 萨麦尔 lv80 · 4 mod 金+10，DNAUID 历史记录口径）：
- 暴击率   20% × (1+100%) =  40%   ✓
- 暴击伤害 200% × (1+100%) = 400%   ✓
- 攻击速度 1.0 × (1+50%)  = 1.5    ✓
- 触发概率  25% × (1+0)   =  25%   ✓
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..dna_mod import dob_loader
from ..utils.api.model import Mode, RoleDetail, WeaponDetail


def resolve_weapon_base_attack(weapon_detail: WeaponDetail, role_detail: RoleDetail) -> float | None:
    """按等级解析武器基础攻击（1 级白值 × 等级倍率）

    优先查普通武器表，再查角色数据包中的同律武器条目；
    两处均无（数据包未收录 / 数据不足）返回 None，由调用方显示「无法计算」。
    """
    multiplier = dob_loader.level_multiplier(getattr(weapon_detail, "level", None))
    if multiplier is None:
        return None
    weapon = dob_loader.get_weapon(weapon_detail.id)
    attack = weapon.get("攻击") if weapon else None
    if attack is None and getattr(role_detail, "conWeaponId", None) is not None:
        con = dob_loader.get_con_weapon(role_detail.charId, role_detail.conWeaponId)
        if con is not None:
            attack = con.get("攻击")
    if not isinstance(attack, (int, float)) or isinstance(attack, bool):
        return None
    return float(attack) * multiplier


@dataclass(slots=True)
class WeaponBonus:
    """武器魔之楔汇总加成（百分比）"""

    atk: float = 0.0
    cri: float = 0.0  # 暴击率
    crd: float = 0.0  # 暴击伤害
    speed: float = 0.0  # 攻击速度
    trigger: float = 0.0  # 触发概率
    missing: list[int] = field(default_factory=list)


def collect_weapon_bonus(modes: list[Mode] | None) -> WeaponBonus:
    """汇总武器所有魔之楔的加成（每个 mod 按其等级取 DOB 数据线性缩放值）"""
    bonus = WeaponBonus()
    if not modes:
        return bonus
    for mode in modes:
        if mode.id is None or mode.id <= 0:
            continue
        if not dob_loader.get_by_third_id(mode.id):
            bonus.missing.append(mode.id)
            continue
        attrs = dob_loader.get_weapon_mod_attrs(mode.id, mode.level, mode.quality) or {}
        bonus.atk += attrs.get("攻击", 0.0)
        bonus.cri += attrs.get("暴击率", 0.0)
        bonus.crd += attrs.get("暴击伤害", 0.0)
        bonus.speed += attrs.get("攻击速度", 0.0)
        bonus.trigger += attrs.get("触发概率", 0.0)
    return bonus


@dataclass(slots=True)
class WeaponAttributeRows:
    """武器属性面板的 (显示名, 显示值) 列表"""

    rows: list[tuple[str, str]]
    # 震荡攻击最终值（原始数值）；数据不足无法计算时为 None
    final_atk: float | None = None


def _fmt_pct(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return f"{int(round(value))}%"
    return f"{value:.1f}%"


def _fmt_speed(value: float) -> str:
    if abs(value - round(value, 1)) < 1e-6:
        # 1.0 → "1"，1.5 → "1.5"
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def compute_weapon_attribute(
    weapon_detail: WeaponDetail,
    role_detail: RoleDetail,
) -> WeaponAttributeRows:
    """计算武器属性面板（武器类型 / 震荡攻击 / 暴击率 / 暴击伤害 / 攻击速度 / 触发概率）

    - 副属性：本地算
    - 震荡攻击：本地按等级成长 + 魔之楔加成；数据不足时显示「无法计算」
    """
    base = weapon_detail.attribute
    bonus = collect_weapon_bonus(weapon_detail.modes)

    rows: list[tuple[str, str]] = []
    rows.append(("武器类型", weapon_detail.elementName))

    # 震荡攻击：基础攻击（本地按等级成长）× (1 + mod 攻击加成)
    base_atk = resolve_weapon_base_attack(weapon_detail, role_detail)
    final_atk: float | None = None
    if base_atk is not None:
        final_atk = base_atk * (1 + bonus.atk / 100)
        rows.append(("震荡攻击", f"{final_atk:,.2f}"))
    else:
        rows.append(("震荡攻击", "无法计算"))

    # 副属性：基础值 × (1 + 加成%)
    # 注意字段口径：attribute.cri=暴击率(0.2)、crd=暴击伤害(2.0)、speed=攻速、trigger=触发率
    rows.append(("暴击率", _fmt_pct(base.cri * 100 * (1 + bonus.cri / 100))))
    rows.append(("暴击伤害", _fmt_pct(base.crd * 100 * (1 + bonus.crd / 100))))
    rows.append(("攻击速度", _fmt_speed(base.speed * (1 + bonus.speed / 100))))
    rows.append(("触发概率", _fmt_pct(base.trigger * 100 * (1 + bonus.trigger / 100))))

    return WeaponAttributeRows(rows=rows, final_atk=final_atk)


__all__ = [
    "WeaponBonus",
    "WeaponAttributeRows",
    "collect_weapon_bonus",
    "compute_weapon_attribute",
    "resolve_weapon_base_attack",
]
