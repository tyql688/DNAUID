"""武器（同律/近战/远程）属性面板计算 —— 副属性本地算，震荡攻击基础值走官方接口

背景
----
面板图里武器区块的属性面板原本直接画 ``getWeaponDetail.attribute`` 的裸身白值
（萨麦尔 atk=15 / cri=0.2 / crd=2.0 / speed=1.0 / trigger=0.25），
没有叠加武器魔之楔的加成，导致与游戏里的「属性总值」对不上
（游戏：震荡攻击 564.85 / 暴击率 40% / 暴击伤害 400% / 攻击速度 1.5 / 触发概率 25%）。

两层来源
--------
1. **副属性（暴击率/暴击伤害/攻击速度/触发概率）**：与武器等级无关（lv1~80 恒定），
   直接 ``基础值 × (1 + Σ mod加成%)`` 本地可算。
   基础值 = ``getWeaponDetail.attribute`` 的 cri / crd / speed / trigger。
   （注意：该 attribute 的字段含义与 panel 显示名的对应见下方注释）

2. **震荡攻击（atk）**：基础值随武器等级成长，官方 attribute.atk 是 1 级白值，
   本地成长表与官方口径尚有出入（数据包白值 × 等级倍率算出的 80 级值与官方
   ``calculateWeapon`` 结果不一致），因此维持调 ``/role/build/calculateWeapon``
   （空 mods）取基础攻击，再 ``×(1 + Σ mod攻击%)``；接口失败回退 1 级白值。

已验证（莉兹贝尔 · 萨麦尔 lv80 · 4 mod 金+10）
--------------------------------------------
- 攻击  225.94 × (1+150%) = 564.85 ✓（截图 564.85）
- 暴击率   20% × (1+100%) =  40%   ✓
- 暴击伤害 200% × (1+100%) = 400%   ✓
- 攻击速度 1.0 × (1+50%)  = 1.5    ✓
- 触发概率  25% × (1+0)   =  25%   ✓

mod 加成来源（2026-10-07 起）
----------------------------
**DOB 数据包**（``dob_loader.get_weapon_mod_attrs``，键已映射为面板显示名：
攻击 / 暴击率 / 暴击伤害 / 攻击速度 / 触发概率，值为百分比），
原 wiki ``effects`` 正则解析已废弃。
"""

from __future__ import annotations

from dataclasses import field, dataclass

from ..dna_mod import dob_loader
from ..utils.dna_api import dna_api
from ..utils.api.model import Mode, WeaponDetail
from ..utils.database.models import DNAUser
from ..utils.api.damage_model import WeaponCalculateRequest


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


async def _fetch_base_atk(dna_user: DNAUser, weapon_detail: WeaponDetail) -> float | None:
    """调 calculateWeapon（空 mods）取该武器当前等级的基础攻击

    返回 None 表示接口失败（调用方应回退）。
    """
    request = WeaponCalculateRequest(
        weaponId=weapon_detail.id,
        weaponModes=[],
        skillLevel=weapon_detail.skillLevel,
        weaponLevel=weapon_detail.level,
    )
    response = await dna_api.calculate_weapon(dna_user, request)
    if not response.is_success or response.data is None:
        return None
    return response.data.final_weapon_attribute.atk


@dataclass(slots=True)
class WeaponAttributeRows:
    """武器属性面板的 (显示名, 显示值) 列表"""

    rows: list[tuple[str, str]]


def _fmt_pct(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return f"{int(round(value))}%"
    return f"{value:.1f}%"


def _fmt_speed(value: float) -> str:
    if abs(value - round(value, 1)) < 1e-6:
        # 1.0 → "1"，1.5 → "1.5"
        return f"{value:g}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


async def compute_weapon_attribute(
    dna_user: DNAUser,
    weapon_detail: WeaponDetail,
) -> WeaponAttributeRows:
    """计算武器属性面板（武器类型 / 震荡攻击 / 暴击率 / 暴击伤害 / 攻击速度 / 触发概率）

    - 副属性：本地算
    - 震荡攻击：调 calculateWeapon 取基础攻击再乘 mod 加成；接口失败则回退基础值
    """
    base = weapon_detail.attribute
    bonus = collect_weapon_bonus(weapon_detail.modes)

    rows: list[tuple[str, str]] = []
    rows.append(("武器类型", weapon_detail.elementName))

    # 震荡攻击
    base_atk = await _fetch_base_atk(dna_user, weapon_detail)
    if base_atk is not None:
        final_atk = base_atk * (1 + bonus.atk / 100)
        rows.append(("震荡攻击", f"{final_atk:,.2f}"))
    else:
        # 接口失败 → 回退到详情里的基础攻击（口径偏低，但至少有值）
        rows.append(("震荡攻击", f"{base.atk:,.2f}"))

    # 副属性：基础值 × (1 + 加成%)
    # 注意字段口径：attribute.cri=暴击率(0.2)、crd=暴击伤害(2.0)、speed=攻速、trigger=触发率
    rows.append(("暴击率", _fmt_pct(base.cri * 100 * (1 + bonus.cri / 100))))
    rows.append(("暴击伤害", _fmt_pct(base.crd * 100 * (1 + bonus.crd / 100))))
    rows.append(("攻击速度", _fmt_speed(base.speed * (1 + bonus.speed / 100))))
    rows.append(("触发概率", _fmt_pct(base.trigger * 100 * (1 + bonus.trigger / 100))))

    return WeaponAttributeRows(rows=rows)


__all__ = [
    "WeaponBonus",
    "WeaponAttributeRows",
    "collect_weapon_bonus",
    "compute_weapon_attribute",
]
