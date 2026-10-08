"""武器（同律/近战/远程）属性面板计算 —— 全本地，不依赖官方计算接口

口径（移植自 dna-builder）：

1. **攻击行**：数据包武器的 ``攻击`` 为 1 级白值，
   ``基础攻击 = 白值 × CommonLevelUp[等级-1]``（同律武器取角色数据包中的
   同律武器条目）；武器不在数据包内时显示「无法计算」。
   显示名按武器「伤害类型」渲染（贯穿攻击 / 切割攻击 / 震荡攻击 / 灾厄攻击），
   继承型同律武器没有自己的伤害类型，回退为「攻击」。
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

from typing import TYPE_CHECKING
from dataclasses import field, dataclass

from ..dna_mod import dob_loader
from ..utils.api.model import Mode, RoleDetail, WeaponDetail
from ..dna_mod.dob_types import WeaponRecord

if TYPE_CHECKING:
    from .local_attribute import AttributeBonus


def _resolve_weapon_record(
    weapon_detail: WeaponDetail,
    role_detail: RoleDetail,
) -> tuple[WeaponRecord | None, bool]:
    """按武器 id 取数据包记录，返回 (记录, 是否同律武器)

    优先查普通武器表，再查角色数据包中的同律武器条目。
    """
    weapon = dob_loader.get_weapon(weapon_detail.id)
    if weapon is not None:
        return weapon, False
    if role_detail.conWeaponId is not None:
        con = dob_loader.get_con_weapon(role_detail.charId, role_detail.conWeaponId)
        if con is not None:
            return con, True
    return None, False


def resolve_inherit_source(
    weapon_detail: WeaponDetail,
    role_detail: RoleDetail,
    close_weapon_detail: WeaponDetail | None = None,
    ranged_weapon_detail: WeaponDetail | None = None,
) -> WeaponDetail | None:
    """inherit 型同律武器 → 被继承的已装备武器（近战/远程）；非继承返回 None

    dna-builder ``calculateWeaponAttributes`` 对 inherit 武器直接把 weapon 换成
    被继承的那把，面板与伤害全部按被继承武器算（伤害类型也同步过去）。
    """
    record, _is_skill = _resolve_weapon_record(weapon_detail, role_detail)
    inherit = record.get("inherit") if record else None
    if inherit == "melee":
        return close_weapon_detail
    if inherit == "ranged":
        return ranged_weapon_detail
    return None


def resolve_weapon_level(weapon_detail: WeaponDetail, role_detail: RoleDetail, is_skill_weapon: bool) -> int | None:
    """武器成长等级：同律武器绑定角色取角色等级；普通武器取武器自身等级"""
    if is_skill_weapon:
        return role_detail.level or weapon_detail.level
    return weapon_detail.level


def resolve_weapon_base_attack(weapon_detail: WeaponDetail, role_detail: RoleDetail) -> float | None:
    """按等级解析武器基础攻击（1 级白值 × 等级倍率）

    数据包未收录（数据不足）返回 None，由调用方显示「无法计算」。
    """
    weapon, is_skill = _resolve_weapon_record(weapon_detail, role_detail)
    multiplier = dob_loader.level_multiplier(resolve_weapon_level(weapon_detail, role_detail, is_skill))
    if multiplier is None:
        return None
    if weapon is None:
        return None
    attack = weapon.get("攻击")
    if attack is None:
        return None
    return round(attack * multiplier, 2)


def resolve_weapon_mastery_ratio(weapon_detail: WeaponDetail, role_detail: RoleDetail) -> float:
    """武器攻击的精通倍率（命中 1.2 / 未命中 1.0；同律武器必然命中）"""
    weapon, _ = _resolve_weapon_record(weapon_detail, role_detail)
    return dob_loader.weapon_mastery_ratio(role_detail.charId, weapon)


@dataclass(slots=True)
class WeaponBonus:
    """武器魔之楔汇总加成（百分比）"""

    atk: float = 0.0
    physical: float = 0.0  # 物理（攻击的独立乘区，dna-builder attack *= 1 + physicalBonus）
    cri: float = 0.0  # 暴击率
    crd: float = 0.0  # 暴击伤害
    speed: float = 0.0  # 攻击速度
    trigger: float = 0.0  # 触发概率
    missing: list[int] = field(default_factory=list)


def collect_weapon_bonus(modes: list[Mode]) -> WeaponBonus:
    """汇总武器所有魔之楔的加成（每个 mod 按其等级取 DOB 数据线性缩放值）"""
    bonus = WeaponBonus()
    for mode in modes:
        if mode.id is None or mode.id <= 0:
            continue
        if not dob_loader.get_by_third_id(mode.id):
            bonus.missing.append(mode.id)
            continue
        attrs = dob_loader.get_weapon_mod_attrs(mode.id, mode.level, mode.quality)
        if not attrs:
            continue
        bonus.atk += attrs.get("攻击", 0.0)
        bonus.physical += attrs.get("物理", 0.0)
        bonus.cri += attrs.get("暴击率", 0.0)
        bonus.crd += attrs.get("暴击伤害", 0.0)
        bonus.speed += attrs.get("攻击速度", 0.0)
        bonus.trigger += attrs.get("触发概率", 0.0)
    return bonus


# 可从角色侧「穿透」到武器面板的属性（dna-builder CharBuild.attrAllowCharToWeapon）
# 常量集中在 dob_loader，供 collect_weapon_forge_bonus 过滤武器自身加成时共用
_CHAR_TO_WEAPON_KEYS = dob_loader.WEAPON_SCOPE_KEYS

# 攻速加成上限（百分比）：dna-builder ``CharBuild.ts:1624``
# ``attackSpeedBonus = Math.min(attackSpeedBonus, 2)`` —— 2 即 +200%
_ATK_SPEED_BONUS_CAP = 200.0


@dataclass(slots=True)
class WeaponScopeBonus:
    """角色侧对武器面板的加成（百分比）：角色自带加成 + 角色槽魔之楔"""

    cri: float = 0.0  # 暴击率
    crd: float = 0.0  # 暴击伤害
    trigger: float = 0.0  # 触发概率
    speed: float = 0.0  # 攻击速度


def collect_char_weapon_scope_bonus(
    role_detail: RoleDetail,
    bonus: AttributeBonus | None = None,
) -> WeaponScopeBonus:
    """取角色侧「可穿透到武器」的属性（暴击/暴伤/触发/攻速）

    dna-builder 的 ``getTotalBonus(键, 武器作用域)`` 会同时计入
    ``table.char``（角色加成，如 芙罗拉/刻舟被动 +50% 暴击）与 ``table.modsChar``
    （角色槽 MOD，**含条件生效块**，如 56163「专注」技能耐久≥2 → 暴击+99%）
    —— 白名单见 ``CharBuild.attrAllowCharToWeapon``。
    这些属性**不显示在角色面板**，只作用于武器面板与伤害结算。

    ``bonus`` 传已算好的角色加成汇总（``AttributeBonus``）时直接取用 ——
    它已含「角色自带加成 + 角色槽 MOD + 条件生效块」，是最完整的口径；
    不传则内部现算一次（多一轮不动点迭代，调用方持有 ctx 时建议传入）。
    """
    if bonus is None:
        from .local_attribute import collect_attribute_bonus

        bonus = collect_attribute_bonus(role_detail)

    out = WeaponScopeBonus()
    for zone in (bonus.extra, bonus.rate, bonus.main):
        for key, value in zone.items():
            if key not in _CHAR_TO_WEAPON_KEYS:
                continue
            amount = float(value)
            if key == "暴击":
                out.cri += amount
            elif key == "暴伤":
                out.crd += amount
            elif key == "触发":
                out.trigger += amount
            elif key == "攻速":
                out.speed += amount
    return out


@dataclass(slots=True)
class WeaponPanel:
    """武器最终面板数值（原始口径：攻击为绝对值，暴击/暴伤/触发为小数、攻速为倍率）"""

    attack: float | None
    cri: float
    crd: float
    speed: float
    trigger: float


def resolve_weapon_panel(
    weapon_detail: WeaponDetail,
    role_detail: RoleDetail,
    bonus: AttributeBonus | None = None,
    inherit_from: WeaponDetail | None = None,
) -> WeaponPanel:
    """武器最终面板：基础值 × (1 + 角色侧 + 武器自身加成 + 该武器槽 mod)

    dna-builder ``CharBuild.calculateWeaponAttributes`` 同口径 —— 暴击/暴伤/触发/攻速
    四个属性会吃到「角色自带加成（如被动技能）+ 角色槽 MOD + 武器自身加成 + 该武器槽 MOD」；
    攻击只吃「武器自身加成 + 该武器槽 MOD」（不吃角色侧），再乘一个独立的「物理」乘区。

    ``inherit_from`` 传 inherit 型同律武器所继承的那把武器时，整份面板按被继承武器算。
    """
    if inherit_from is not None:
        weapon_detail = inherit_from
    base = weapon_detail.attribute
    mod_bonus = collect_weapon_bonus(weapon_detail.modes)
    scope = collect_char_weapon_scope_bonus(role_detail, bonus)
    record, _is_skill = _resolve_weapon_record(weapon_detail, role_detail)
    forge = dob_loader.weapon_forge_bonus(record, weapon_detail.skillLevel)

    cri_bonus = mod_bonus.cri + scope.cri + float(forge.get("暴击", 0.0)) * 100
    crd_bonus = mod_bonus.crd + scope.crd + float(forge.get("暴伤", 0.0)) * 100
    # 攻速加成有 +200% 上限（dna-builder CharBuild.ts:1624），其余三项无上限
    speed_bonus = min(
        mod_bonus.speed + scope.speed + float(forge.get("攻速", 0.0)) * 100,
        _ATK_SPEED_BONUS_CAP,
    )
    trigger_bonus = mod_bonus.trigger + scope.trigger + float(forge.get("触发", 0.0)) * 100

    # 物理是与「攻击加成」并列的独立乘区（dna-builder: attack *= 1 + physicalBonus）
    physical_bonus = mod_bonus.physical + float(forge.get("物理", 0.0)) * 100
    base_atk = resolve_weapon_base_attack(weapon_detail, role_detail)
    mastery_ratio = resolve_weapon_mastery_ratio(weapon_detail, role_detail)
    if base_atk is None:
        attack = None
    else:
        attack = base_atk * (1 + mod_bonus.atk / 100) * (1 + physical_bonus / 100) * mastery_ratio
        attack = round(attack, 2)

    return WeaponPanel(
        attack=attack,
        cri=float(base.cri) * (1 + cri_bonus / 100),
        crd=float(base.crd) * (1 + crd_bonus / 100),
        speed=float(base.speed) * (1 + speed_bonus / 100),
        trigger=float(base.trigger) * (1 + trigger_bonus / 100),
    )


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
    bonus: AttributeBonus | None = None,
    inherit_from: WeaponDetail | None = None,
) -> WeaponAttributeRows:
    """计算武器属性面板（武器类型 / 震荡攻击 / 暴击率 / 暴击伤害 / 攻击速度 / 触发概率）

    - 副属性：本地算
    - 震荡攻击：本地按等级成长 + 魔之楔加成；数据不足时显示「无法计算」
    """
    panel = resolve_weapon_panel(weapon_detail, role_detail, bonus, inherit_from)

    own_rec, _ = _resolve_weapon_record(weapon_detail, role_detail)
    # 攻击行标签取被继承武器的伤害类型（dna-builder syncSkillWeaponDamageType 同口径）
    label_rec, _ = _resolve_weapon_record(inherit_from or weapon_detail, role_detail)

    rows: list[tuple[str, str]] = []
    # 官方接口对个别武器不返回 elementName（如 无声的嘶吼），回退数据包的武器类别
    type_label = weapon_detail.elementName or dob_loader.weapon_category(own_rec)
    rows.append(("武器类型", type_label or "未知"))

    # 攻击行标签按武器「伤害类型」显示（贯穿/切割/震荡/灾厄），与游戏口径一致
    dmg_type = label_rec.get("伤害类型") if label_rec else None
    atk_label = f"{dmg_type}攻击" if dmg_type else "攻击"

    # 基础攻击（按等级成长）× (1 + mod 攻击加成) × 精通倍率
    final_atk = panel.attack
    if final_atk is not None:
        rows.append((atk_label, f"{final_atk:,.2f}"))
    else:
        rows.append((atk_label, "无法计算"))

    # 副属性：基础值 × (1 + 角色侧 + 武器自身 + 该武器槽 mod)
    # 注意字段口径：attribute.cri=暴击率(0.2)、crd=暴击伤害(2.0)、speed=攻速、trigger=触发率
    rows.append(("暴击率", _fmt_pct(panel.cri * 100)))
    rows.append(("暴击伤害", _fmt_pct(panel.crd * 100)))
    rows.append(("攻击速度", _fmt_speed(panel.speed)))
    rows.append(("触发概率", _fmt_pct(panel.trigger * 100)))

    return WeaponAttributeRows(rows=rows, final_atk=final_atk)


__all__ = [
    "WeaponBonus",
    "WeaponPanel",
    "WeaponScopeBonus",
    "WeaponAttributeRows",
    "collect_char_weapon_scope_bonus",
    "collect_weapon_bonus",
    "compute_weapon_attribute",
    "resolve_weapon_base_attack",
    "resolve_weapon_level",
    "resolve_weapon_mastery_ratio",
    "resolve_weapon_panel",
]
