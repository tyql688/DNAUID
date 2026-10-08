"""角色属性面板 —— dobsdk 引擎结算 + DNAUID 面板行组装。

口径以 dna-builder TS 为准（引擎逐项与 bun 真机一致）：
- 四维/率类/隐藏属性全部取引擎 ``calculate_attributes``；
- 四维基础值缺失时逐项回退官方 attribute（数据缺失兜底，非口径）；
- 充盈溢出按三把真武器（近战/远程/非继承同律）重算后替换引擎值
  （引擎按自推导同律武器算，官方 loadout 以真武器为准；公式同 TS）。
"""
from __future__ import annotations

from dataclasses import field, dataclass
from typing import TYPE_CHECKING

from gsuid_core.logger import logger

from ..dna_sdk import tables
from ..dna_sdk.build import SdkBuild

if TYPE_CHECKING:
    from ..dna_sdk.build import SdkBuild as _SdkBuild
    from ..utils.api.model import RoleDetail, WeaponDetail

# 面板 11 项属性的计算定义 ─────────────────────────────────────
# 四维：数值型，最终 = 基础 × (1 + 加成/100)
_MAIN_KEYS: dict[str, str] = {
    "攻击": "atk",
    "生命": "maxHp",
    "护盾": "maxES",
    "防御": "defense",
    "神智": "maxSp",
}

# 面板显示名覆盖：内部键名与数据包保持一致（「神智」），显示时用游戏叫法
_PANEL_DISPLAY_NAME: dict[str, str] = {"神智": "最大神智"}

# 角色自身属性（DOB ``char.element`` 口径）
_ELEMENT_NAMES_CN = ("光", "暗", "水", "火", "雷", "风")

# 率类属性：基础 100%
_RATE_DISPLAY: dict[str, str] = {
    "技能威力": "技能威力",
    "技能范围": "技能范围",
    "技能耐久": "技能耐久",
    "技能效益": "技能效益",
}

# 额外百分比属性：基础 0
_EXTRA_DISPLAY: dict[str, str] = {
    "昂扬": "昂扬",
    "背水": "背水",
}

# 引擎小数键 → 视图百分比区的映射（率类/隐藏属性；四维是绝对值，另行处理）
# 技能威力/范围/耐久/效益是 1 起始乘数（转百分比时先减 1），其余 0 基准。
_RATE_KEYS_0 = ("充盈威力", "昂扬", "背水")
_RATE_KEYS_1 = ("技能威力", "技能范围", "技能耐久", "技能效益")
_EXTRA_KEYS = (
    "增伤", "元素增伤", "物理增伤", "武器伤害", "技能伤害", "独立增伤",
    "属性穿透", "无视防御", "技能无视防御", "追加伤害", "多重", "歧视",
    "物理", "触发倍率", "充盈转化", "攻击范围", "技能倍率乘数", "技能倍率加数",
    "暴击", "暴伤", "触发", "攻速",
)


def get_role_panel_entry(role_detail: RoleDetail) -> dict | None:
    """按游戏 charId（优先）或角色名找到数据包条目。"""
    entry = tables.char_record(role_detail.charId)
    if entry:
        return entry
    for char in tables.get_tables().chars:
        if char.get("名称") == role_detail.charName:
            return char
    return None


@dataclass(slots=True)
class AttributeBonus:
    """面板加成视图（百分比单位）：从引擎属性换算，供武器面板/伤害结算取数。"""

    main: dict[str, float] = field(default_factory=dict)  # 四维百分比（仅兜底链路用）
    rate: dict[str, float] = field(default_factory=dict)  # 率类百分比
    elem_atk: dict[str, float] = field(default_factory=dict)  # 属性攻击（引擎已折入攻击绝对值，恒空）
    flat: dict[str, float] = field(default_factory=dict)  # 固定值加成（恒空）
    extra: dict[str, float] = field(default_factory=dict)  # 隐藏属性百分比
    raw: list[str] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)  # 查不到数据的 thirdId


def _pct(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) * 100
    return 0.0


def bonus_view(attrs: dict[str, float], missing: list[int] | None = None) -> AttributeBonus:
    """引擎属性（小数）→ 百分比视图。"""
    bonus = AttributeBonus(missing=list(missing or []))
    for key in _RATE_KEYS_0:
        bonus.rate[key] = _pct(attrs.get(key))
    for key in _RATE_KEYS_1:
        value = attrs.get(key)
        if isinstance(value, bool):
            bonus.rate[key] = 0.0
        elif isinstance(value, (int, float)):
            bonus.rate[key] = (float(value) - 1) * 100
        else:
            bonus.rate[key] = 0.0
    for key in _EXTRA_KEYS:
        value = attrs.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) > 1e-12:
            bonus.extra[key] = float(value) * 100
    return bonus


def _official_main_values(role_detail: RoleDetail) -> dict[str, float]:
    """官方 ``attribute`` 四维裸值（数据缺失时的逐项回退）。"""
    attribute = role_detail.attribute
    return {
        "攻击": float(attribute.atk),
        "生命": float(attribute.maxHp),
        "防御": float(attribute.defense),
        "神智": float(attribute.maxSp),
        "护盾": float(attribute.maxES),
    }


def _role_element_cn(role_detail: RoleDetail) -> str:
    name = role_detail.elementName or ""
    for cn in _ELEMENT_NAMES_CN:
        if cn in name:
            return cn
    return ""


@dataclass(slots=True)
class AttrContext:
    """本地伤害/面板共用的属性上下文（tt 为技能字段四大乘区，1 起始）。"""

    base_main: dict[str, float]
    bonus: AttributeBonus
    final_main: dict[str, float]
    elem_mult: float
    reduce_frac: float
    source: str
    matched: bool
    tt: dict[str, float]
    fullness_weapon: float = 0.0


def _auto_skill_overflow(engine) -> float:
    """引擎自推导同律武器的溢出贡献（DNAUID 以真同律武器替代，需扣掉）。"""
    try:
        skill_weapon = engine.s.get("skillWeapon")
        if not skill_weapon or skill_weapon.get("inherit"):
            return 0.0
        rate, conv = engine.weapon_fullness(skill_weapon)
        return max(0.0, rate - 1) * conv
    except Exception:
        return 0.0


def _con_overflow(build: SdkBuild) -> float:
    """真同律武器（非继承）的溢出贡献。"""
    from .local_weapon_attribute import con_weapon_panel, resolve_inherit_source

    con = build.weapons.get("con")
    if con is None:
        return 0.0
    role = build.role
    inherit = resolve_inherit_source(con, role, build.weapons.get("close"), build.weapons.get("ranged"))
    if inherit is not None:
        return 0.0
    panel = con_weapon_panel(build, con)
    if panel is None:
        return 0.0
    return max(0.0, panel.trigger - 1.0) * (1.0 + _con_conversion(con))


def _con_conversion(con) -> float:
    """同律槽充盈转化加成（小数）：槽 mod 基础值之和。"""
    from .local_weapon_attribute import _con_mod_bonus_fractions

    return _con_mod_bonus_fractions(con).get("充盈转化", 0.0)


def compute_attr_context(build: SdkBuild) -> AttrContext:
    """同一张卡片只算一次，属性表与伤害区块共用。"""
    from dna_builder_sdk.calc.entities import level_char

    role = build.role
    engine = build.engine
    # TS 界面口径：角色面板取 calculateWeaponAttributes（含充盈溢出）
    attrs = dict(engine.char_panel())
    # 溢出武器集合修正：引擎按 {近战, 远程, 自推导同律}，实按 {近战, 远程, 真同律}
    attrs["充盈威力"] = (attrs.get("充盈威力") or 0) - _auto_skill_overflow(engine) + _con_overflow(build)

    # 四维基础（DOB 按实际等级缩放，逐项回退官方）
    entry = get_role_panel_entry(role)
    official = _official_main_values(role)
    base_main: dict[str, float] = {}
    source = "attribute"
    if entry is not None:
        inst = level_char(entry, role.level or 80)
        base_map = {
            "攻击": inst.get("基础攻击"),
            "生命": inst.get("基础生命"),
            "护盾": inst.get("基础护盾"),
            "防御": inst.get("基础防御"),
            "神智": inst.get("基础神智"),
        }
        for name in _MAIN_KEYS:
            value = base_map.get(name)
            if isinstance(value, (int, float)):
                base_main[name] = float(value)
        if "攻击" in base_main:
            source = "dob"
    if source != "dob":
        base_main = dict(official)
    else:
        for name, val in official.items():
            if name not in base_main:
                base_main[name] = val
    matched = entry is not None

    bonus = bonus_view(attrs, build.missing_mods)
    if build.missing_mods:
        logger.warning(f"[DNA 面板] 数据包未收录的魔之楔 id: {build.missing_mods}（其词条未计入面板）")

    final_main: dict[str, float] = {}
    for name in _MAIN_KEYS:
        value = attrs.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            final_main[name] = float(value)

    def _rate1(key: str) -> float:
        return 1 + bonus.rate.get(key, 0.0) / 100

    tt = {
        "技能威力": _rate1("技能威力"),
        "技能范围": min(_rate1("技能范围"), 2.8),
        "技能耐久": min(_rate1("技能耐久"), 4),
        "技能效益": min(_rate1("技能效益"), 1.75),
    }
    reduce_value = attrs.get("减伤")
    reduce_frac = float(reduce_value) if isinstance(reduce_value, (int, float)) else 0.0
    return AttrContext(
        base_main=base_main,
        bonus=bonus,
        final_main=final_main,
        elem_mult=1.0,
        reduce_frac=reduce_frac,
        source=source,
        matched=matched,
        tt=tt,
    )


def _fmt_value(value: float, *, percent: bool) -> str:
    if percent:
        if abs(value - round(value)) < 1e-6:
            return f"{int(round(value))}%"
        return f"{value:.1f}%"
    if abs(value - round(value)) < 1e-6:
        return f"{int(round(value)):,}"
    return f"{value:,.1f}"


@dataclass(slots=True)
class FinalAttribute:
    """面板属性表的最终值（显示用）"""

    rows: list[tuple[str, str]]  # 标准行 [(显示名, 显示值)]
    base_source: str = "attribute"  # "dob" / "attribute"（调试用）
    matched: bool = False
    bonus: AttributeBonus | None = None
    hidden_rows: list[tuple[str, str]] = field(default_factory=list)


def compute_final_attribute(build: SdkBuild, ctx: AttrContext | None = None) -> FinalAttribute:
    """本地计算角色最终属性，返回面板标准行 + 隐藏属性行。"""
    if ctx is None:
        ctx = compute_attr_context(build)
    role = build.role
    bonus = ctx.bonus
    reduce_frac = ctx.reduce_frac

    rows: list[tuple[str, str]] = []
    final_main = dict(ctx.final_main)
    elem_cn = _role_element_cn(role)
    for name in _MAIN_KEYS:
        if name not in final_main:
            continue
        display = f"{elem_cn}属性攻击" if (name == "攻击" and elem_cn) else _PANEL_DISPLAY_NAME.get(name, name)
        rows.append((display, _fmt_value(final_main[name], percent=False)))

    for key, display in _RATE_DISPLAY.items():
        if key in ctx.tt:
            rows.append((display, _fmt_value(ctx.tt[key] * 100, percent=True)))
        else:
            rows.append((display, _fmt_value(100 + bonus.rate.get(key, 0.0), percent=True)))

    for key, display in _EXTRA_DISPLAY.items():
        pct = bonus.rate.get(key, 0.0)
        rows.append((display, _fmt_value(pct, percent=True)))

    # 充盈威力 0 起始（TS：totalFullness 从 0 累加，显示 val*100；+1 只在充盈伤害乘区现用）
    fullness = bonus.rate.get("充盈威力", 0.0) + bonus.extra.get("充盈威力", 0.0)
    rows.append(("充盈威力", _fmt_value(fullness, percent=True)))

    hidden: list[tuple[str, str]] = [
        ("增伤", _fmt_value(bonus.extra.get("增伤", 0.0), percent=True)),
        ("技能伤害", _fmt_value(bonus.extra.get("技能伤害", 0.0), percent=True)),
        ("减伤", _fmt_value(reduce_frac * 100, percent=True)),
    ]

    hp = final_main.get("生命")
    defense = final_main.get("防御")
    if hp is not None and defense is not None and hp > 0 and defense >= 0:
        shield = final_main.get("护盾", 0.0)
        ehp = (hp / (1 - defense / (300 + defense)) + shield) / (1 - reduce_frac)
        hidden.append(("有效生命", _fmt_value(ehp, percent=False)))

    for key in sorted(bonus.extra):
        if key in (
            "增伤",
            "技能伤害",
            "减伤",
            "充盈威力",
            "充盈转化",
            "暴击",
            "暴伤",
            "触发",
            "攻速",
        ):
            continue
        if abs(bonus.extra[key]) > 1e-9:
            hidden.append((key, _fmt_value(bonus.extra[key], percent=True)))

    return FinalAttribute(
        rows=rows,
        base_source=ctx.source,
        matched=ctx.matched,
        hidden_rows=hidden,
        bonus=bonus,
    )


__all__ = [
    "AttrContext",
    "AttributeBonus",
    "FinalAttribute",
    "bonus_view",
    "compute_attr_context",
    "compute_final_attribute",
    "get_role_panel_entry",
]
