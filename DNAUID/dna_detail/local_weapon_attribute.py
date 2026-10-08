"""武器（同律/近战/远程）属性面板 —— dobsdk 引擎面板 + DNAUID 显示行组装。

口径以 dna-builder TS 为准：面板数值全部取引擎 ``weapon_panel``（数据包基值，
含精通/锻造/各类加成）；显示名按武器「伤害类型」渲染；数据包未收录显示「无法计算」。
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from dataclasses import field, dataclass

from ..dna_sdk import tables
from ..dna_sdk.build import SdkBuild

if TYPE_CHECKING:
    from ..utils.api.model import RoleDetail, WeaponDetail

__all__ = [
    "WeaponPanel",
    "WeaponAttributeRows",
    "con_weapon_panel",
    "resolve_inherit_source",
    "resolve_weapon_record",
    "slot_damage_bonus",
    "weapon_panel_for",
    "compute_weapon_attribute",
]


def resolve_weapon_record(
    weapon_detail: WeaponDetail,
    role_detail: RoleDetail,
) -> tuple[dict | None, bool]:
    """按请求 id 取数据包记录，返回 (记录, 是否同律武器)。

    先查普通武器表；查不到时，只有请求 id 恰好等于角色的同律武器 id 才去查
    角色的同律武器条目 —— 不允许拿角色的同律武器顶替另一把查不到的武器。
    """
    weapon = tables.weapon_record(weapon_detail.id)
    if weapon is not None:
        return weapon, False
    con_id = role_detail.conWeaponId
    if con_id is not None and str(weapon_detail.id) == str(con_id):
        con = tables.con_weapon_record(role_detail.charId, con_id)
        if con is not None:
            return con, True
    return None, False


def resolve_inherit_source(
    weapon_detail: WeaponDetail,
    role_detail: RoleDetail,
    close_weapon_detail: WeaponDetail | None = None,
    ranged_weapon_detail: WeaponDetail | None = None,
) -> WeaponDetail | None:
    """inherit 型同律武器 → 被继承的已装备武器（近战/远程）；非继承返回 None。"""
    record, _is_skill = resolve_weapon_record(weapon_detail, role_detail)
    inherit = record.get("inherit") if record else None
    if inherit == "melee":
        return close_weapon_detail
    if inherit == "ranged":
        return ranged_weapon_detail
    return None


@dataclass(slots=True)
class WeaponPanel:
    """武器最终面板数值（原始口径：攻击绝对值，暴击/暴伤/触发小数，攻速倍率）。"""

    attack: float | None
    cri: float
    crd: float
    speed: float
    trigger: float


def _panel_of(raw: dict | None) -> WeaponPanel | None:
    if not raw:
        return None
    attack = raw.get("攻击")
    return WeaponPanel(
        attack=float(attack) if isinstance(attack, (int, float)) else None,
        cri=float(raw.get("暴击") or 0.0),
        crd=float(raw.get("暴伤") or 0.0),
        speed=float(raw.get("攻速") or 0.0),
        trigger=float(raw.get("触发") or 0.0),
    )


def weapon_panel_for(build: SdkBuild, slot: str) -> WeaponPanel | None:
    """主装配的近战/远程武器面板（slot: close/ranged）。"""
    kind = {"close": "melee", "ranged": "ranged"}.get(slot, slot)
    try:
        return _panel_of(build.engine.weapon_panel(kind))
    except (KeyError, ValueError):
        return None


def _char_scope(build: SdkBuild) -> dict[str, float]:
    """角色侧穿透到武器面板的属性（暴击/暴伤/触发/攻速，百分比，与旧口径一致）。"""
    attrs = build.engine.calculate_attributes()
    out: dict[str, float] = {}
    for key in ("暴击", "暴伤", "触发", "攻速"):
        value = attrs.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[key] = float(value) * 100
    return out


def _con_mod_bonus_fractions(con_detail: WeaponDetail) -> dict[str, float]:
    """同律槽 mod 加成（小数，数据包键；引擎结算值）。"""
    out: dict[str, float] = {}
    for mode in con_detail.modes or []:
        if mode is None or mode.id is None or mode.id <= 0:
            continue
        attrs = tables.leveled_mod_attrs(mode.id, mode.level)
        if not attrs:
            continue
        for key, fraction in attrs.items():
            out[key] = out.get(key, 0.0) + fraction
    return out


def _con_mod_bonus(con_detail: WeaponDetail) -> dict[str, float]:
    """同律槽 mod 加成（百分比，键为武器面板显示名）。"""
    out: dict[str, float] = {}
    for key, fraction in _con_mod_bonus_fractions(con_detail).items():
        display = tables.WEAPON_ATTR_MAP.get(key)
        if display:
            out[display] = out.get(display, 0.0) + fraction * 100
    return out


def _forge_effective(role: RoleDetail, record: dict | None) -> bool:
    """熔炼潜能是否生效：无熔炉恒生效，否则按角色精通判定（同律绑定角色必然命中）。"""
    if record is None or not record.get("熔炉"):
        return True
    return tables.is_weapon_mastered(role.charId, record)


def _con_base_attack(record: dict, role: RoleDetail) -> float | None:
    """同律武器基础攻击（1 级白值 × 角色等级倍率；同律绑定角色等级）。"""
    attack = record.get("攻击")
    if attack is None:
        return None
    multiplier = tables.level_multiplier(role.level or 80)
    if multiplier is None:
        return None
    return round(float(attack) * multiplier, 2)


def con_weapon_panel(build: SdkBuild, con_detail: WeaponDetail) -> WeaponPanel | None:
    """同律武器面板（SDK 无 con 槽概念，按 TS 公式就地结算，全数据包基值）。

    基础值 × (1 + 角色侧 + 同律槽 mod + 自身锻造)；攻击另 × 精通倍率
    （同律 1.4，TS 口径）。
    """
    role = build.role
    record, _is_skill = resolve_weapon_record(con_detail, role)
    if record is None:
        return None
    scope = _char_scope(build)
    mod_bonus = _con_mod_bonus(con_detail)
    forge = (
        tables.weapon_forge_bonus(record, con_detail.skillLevel)
        if _forge_effective(role, record)
        else {}
    )

    cri_bonus = (
        mod_bonus.get("暴击率", 0.0) + scope.get("暴击", 0.0)
        + float(forge.get("暴击", 0.0)) * 100
    )
    crd_bonus = (
        mod_bonus.get("暴击伤害", 0.0) + scope.get("暴伤", 0.0)
        + float(forge.get("暴伤", 0.0)) * 100
    )
    speed_bonus = min(
        mod_bonus.get("攻击速度", 0.0) + scope.get("攻速", 0.0)
        + float(forge.get("攻速", 0.0)) * 100,
        200.0,
    )
    trigger_bonus = (
        mod_bonus.get("触发概率", 0.0) + scope.get("触发", 0.0)
        + float(forge.get("触发", 0.0)) * 100
    )
    physical_bonus = mod_bonus.get("物理", 0.0) + float(forge.get("物理", 0.0)) * 100
    atk_bonus = mod_bonus.get("攻击", 0.0)

    base_atk = _con_base_attack(record, role)
    if base_atk is None:
        attack = None
    else:
        attack = base_atk * (1 + atk_bonus / 100) * (1 + physical_bonus / 100) * 1.4
        attack = round(attack, 2)
    official = con_detail.attribute

    def _base(raw_key: str, official_value: float | None) -> float:
        raw_value = record.get(raw_key)
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            return float(raw_value)
        if isinstance(official_value, (int, float)):
            return float(official_value)
        return 0.0

    return WeaponPanel(
        attack=attack,
        cri=_base("暴击", official.cri) * (1 + cri_bonus / 100),
        crd=_base("暴伤", official.crd) * (1 + crd_bonus / 100),
        speed=_base("攻速", official.speed) * (1 + speed_bonus / 100),
        trigger=_base("触发", official.trigger) * (1 + trigger_bonus / 100),
    )


_DAMAGE_BONUS_KEYS = (
    "增伤",
    "元素增伤",
    "物理增伤",
    "武器伤害",
    "独立增伤",
    "追加伤害",
    "触发倍率",
)


def slot_damage_bonus(build: SdkBuild, slot: str) -> dict[str, float]:
    """某武器槽 mod 的伤害相关加成（小数，多来源相加；引擎结算值）。"""
    key = {"close": "meleeMods", "ranged": "rangedMods"}.get(slot)
    out: dict[str, float] = {name: 0.0 for name in _DAMAGE_BONUS_KEYS}
    if key is None:
        return out
    state = build.engine.s if hasattr(build.engine, "s") else {}
    for mod in state.get(key) or []:
        if not mod:
            continue
        for name in _DAMAGE_BONUS_KEYS:
            value = mod.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[name] += float(value)
    return out


@dataclass(slots=True)
class WeaponAttributeRows:
    """武器属性面板的 (显示名, 显示值) 列表"""

    rows: list[tuple[str, str]]
    final_atk: float | None = None


def _fmt_pct(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return f"{int(round(value))}%"
    return f"{value:.1f}%"


def _fmt_speed(value: float) -> str:
    if abs(value - round(value, 1)) < 1e-6:
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def compute_weapon_attribute(
    build: SdkBuild,
    weapon_detail: WeaponDetail,
    slot: str,
    inherit_slot: str | None = None,
) -> WeaponAttributeRows:
    """计算武器属性面板（武器类型 / 伤害攻击 / 暴击率 / 暴击伤害 / 攻击速度 / 触发概率）。

    slot: close/ranged/con。inherit_slot 非空时整份面板按被继承武器算
    （攻击行标签取被继承武器的伤害类型，武器类型仍取自己的）。
    数据不足（未收录）时攻击显示「无法计算」。
    """
    label_detail = weapon_detail
    if inherit_slot is not None:
        panel = weapon_panel_for(build, inherit_slot)
        label_detail = build.weapons.get(inherit_slot) or weapon_detail
    elif slot == "con":
        panel = con_weapon_panel(build, weapon_detail)
    else:
        panel = weapon_panel_for(build, slot)

    own_rec, _ = resolve_weapon_record(weapon_detail, build.role)
    label_rec, _ = resolve_weapon_record(label_detail, build.role)

    rows: list[tuple[str, str]] = []
    type_label = weapon_detail.elementName or tables.weapon_category(own_rec)
    rows.append(("武器类型", type_label or "未知"))

    dmg_type = label_rec.get("伤害类型") if label_rec else None
    atk_label = f"{dmg_type}攻击" if dmg_type else "攻击"

    final_atk = panel.attack if panel else None
    if final_atk is not None:
        rows.append((atk_label, f"{final_atk:,.2f}"))
    else:
        rows.append((atk_label, "无法计算"))

    if panel is None:
        panel = WeaponPanel(attack=None, cri=0.0, crd=0.0, speed=0.0, trigger=0.0)
    rows.append(("暴击率", _fmt_pct(panel.cri * 100)))
    rows.append(("暴击伤害", _fmt_pct(panel.crd * 100)))
    rows.append(("攻击速度", _fmt_speed(panel.speed)))
    rows.append(("触发概率", _fmt_pct(panel.trigger * 100)))

    return WeaponAttributeRows(rows=rows, final_atk=final_atk)
