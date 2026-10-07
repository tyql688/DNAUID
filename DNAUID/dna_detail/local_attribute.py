"""角色面板本地属性计算 —— 不依赖官方 /role/build/calculate 接口

用途
----
面板图右上角的「属性」表原本直接读官方 ``getCharDetail`` 返回的
``role_detail.attribute``（裸身基础值），并在「伤害计算」区块调用官方
``/role/build/calculate`` 拿最终属性。该官方计算接口对多数账号返回
``参数错误``（code 10000），导致面板里看不到算好的最终数值。

本模块改为**本地计算**，直接把最终值写进面板的属性表。

数据源（2026-10-07 起）：**DOB 数据包**（dna-builder 数据包，``dna_mod/dob_pack.py``
下载转换、``dna_mod/dob_loader.py`` 查询），原 dnabbs wiki 双源抓取已废弃。

公式（与官方 H5 对齐，见 PANEL_FORMULA_cur.md）
------------------------------------------------
``面板 = 基础值(角色实际等级) × (1 + Σ普通百分比加成) × Π(1 + 属性攻击加成)``

- 基础值按**角色实际等级**计算（数据包 1 级白值 × ``COMMON_LEVEL_UP`` 等级倍率，
  与 dna-builder LeveledChar 同口径；攻击保留两位小数、生命/护盾取整，
  80 级结果与 wiki 阶段表满级行逐位一致）。等级未知时回退 80 级口径。
- **普通加成走单一加法区**：攻击/生命/防御/神智/技能威力/技能效益… 的百分比
  全部相加，不连乘。
- **属性攻击（水/火/雷/风/光/暗）是独立乘区**，单独再乘一次。
- 率类（技能威力/范围/耐久/效益）基础 **100%**；昂扬/背水基础 **0%**。

加成来源
--------
1. **角色魔之楔**（``role_detail.modes``），数值取 ``dob_loader.get_mod_attrs``
   （满级小数按等级线性缩放后 ×100 转百分比）。
2. **角色加成**（数据包 ``char.加成``）—— 即 wiki 技能解锁被动（伤害/增益节点）
   的聚合总值（验证：芙罗拉 加成.昂扬 15% = wiki 两条被动 6% + 9%），默认全部计入。
3. **同律武器精炼被动** —— 数据包 ``char.同律武器`` 提供同律武器白值；
   精炼被动数值仍在补，暂不计入。
   ⚠️ 同律武器的**专属 mod** 只进「同律武器自己的面板」，**不进角色面板**，
   所以这里**不累加** ``con_weapon_detail.modes``。

数据文件
--------
``DNAUID/dna_mod/data/dob_data.json``（由 ``dna_mod/dob_pack.py`` 生成）
"""

from __future__ import annotations

from typing import Any
from dataclasses import field, dataclass

try:
    from gsuid_core.logger import logger
except ImportError:  # pragma: no cover
    import logging

    logger = logging.getLogger("dna_local_attribute")

from ..dna_mod import dob_loader
from ..utils.api.model import Mode, RoleDetail, WeaponDetail

# 面板 11 项属性的计算定义 ─────────────────────────────────────
# 四维：数值型，最终 = 基础 × (1 + 加成/100)
_MAIN_KEYS: dict[str, str] = {
    "攻击": "atk",
    "生命": "maxHp",
    "护盾": "maxES",
    "防御": "defense",
    "最大神志": "maxSp",
}

# 率类属性：基础 100%（充盈威力是 0 基准的隐藏属性，见 _HIDDEN_ORDER）
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

# 官方 attribute 字段名（主属性）—— 逐项回退用
_ATTR_FIELD = {
    "攻击": "atk",
    "生命": "maxHp",
    "防御": "defense",
    "最大神智": "maxSp",
}


def reload_role_panel() -> None:
    """清空 DOB 数据（兼容旧接口名），下次查询重新读盘

    供数据包更新（dna_mod/dob_pack.py）在重建 dob_data.json 后调用。
    """
    dob_loader.reload()


def get_role_panel_entry(role_detail: RoleDetail) -> dict[str, Any] | None:
    """按游戏 charId（优先）或角色名找到 DOB 数据条目"""
    entry = dob_loader.get_char(role_detail.charId)
    if entry:
        return entry
    nm = getattr(role_detail, "charName", None)
    return dob_loader.get_char_by_name(nm)


@dataclass(slots=True)
class AttributeBonus:
    """从魔之楔 + 角色加成汇总出的加成"""

    main: dict[str, float] = field(default_factory=dict)  # 四维百分比
    rate: dict[str, float] = field(default_factory=dict)  # 率类百分比
    elem_atk: dict[str, float] = field(default_factory=dict)  # 属性攻击（独立乘区）
    flat: dict[str, float] = field(default_factory=dict)  # 固定值加成
    extra: dict[str, float] = field(default_factory=dict)  # 隐藏属性百分比（增伤/技能伤害/充盈威力…）
    raw: list[str] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)  # 查不到数据的 thirdId
    reduce_sources: list[float] = field(default_factory=list)  # 减伤小数来源（乘法聚合用）

    def add(self, parsed: dict[str, Any]) -> None:
        for key in ("main", "rate", "elem_atk", "flat", "extra"):
            bucket: dict[str, float] = getattr(self, key)
            for k, v in (parsed.get(key) or {}).items():
                bucket[k] = bucket.get(k, 0.0) + float(v)
        self.raw.extend(parsed.get("raw") or [])


def _collect_modes(
    modes: list[Mode] | None,
    bonus: AttributeBonus,
    attrs_snapshot: dict[str, float] | None = None,
) -> None:
    """把一个装备位的 modes 加成累加进 bonus（含条件生效块，如 羽蛇·背水 D趋向>=4）

    先收集已匹配的魔之楔并统计极性 / id 计数，再逐条结算普通词条与条件生效词条。
    条件三类（与 dna-builder checkCondition 同规则）：
    - ``X趋向``：极性计数（含中心槽自身）；
    - ``*id``：同 id 最多重复数；
    - 属性门槛（技能威力/神智/昂扬…）：对照 ``attrs_snapshot``（面板属性快照），
      快照为 None（首轮）时视为不满足——由 ``collect_attribute_bonus`` 的不动点
      迭代在后续轮次补判。
    """
    if not modes:
        return
    polarity_count: dict[str, int] = {}
    id_count: dict[int, int] = {}
    matched: list[tuple[Mode, dict[str, Any]]] = []
    for mode in modes:
        if mode.id is None or mode.id <= 0:
            continue
        rec = dob_loader.get_by_third_id(mode.id)
        if not rec:
            bonus.missing.append(mode.id)
            continue
        matched.append((mode, rec))
        polarity = rec.get("polarity")
        if polarity:
            polarity_count[polarity] = polarity_count.get(polarity, 0) + 1
        id_count[mode.id] = id_count.get(mode.id, 0) + 1

    for mode, rec in matched:
        attrs = dob_loader.get_mod_attrs(mode.id, mode.level, mode.quality)
        bonus.add(dob_loader.parse_attrs(attrs, rec.get("element")))
        # 减伤走乘法聚合，单独记录小数来源（extra 里的是相加近似值）
        if attrs and isinstance(attrs.get("减伤"), (int, float)):
            bonus.reduce_sources.append(float(attrs["减伤"]))
        # 条件生效块：条件满足时按等级缩放计入（如 羽蛇·背水 金+10 → 背水+22%）
        if rec.get("effect") and dob_loader.is_effect_effective(
            rec["effect"].get("conditions"),
            polarity_count,
            id_count,
            attrs_snapshot,
        ):
            eff_attrs = dob_loader.get_effect_attrs(rec, mode.level)
            bonus.add(dob_loader.parse_attrs(eff_attrs, rec.get("element")))
            if isinstance(eff_attrs.get("减伤"), (int, float)):
                bonus.reduce_sources.append(float(eff_attrs["减伤"]))
    if bonus.missing:
        # 诊断：数据包未收录的魔之楔 id（新版游戏先于数据包更新时会出现）
        logger.warning(f"[DNA 面板] 数据包未收录的魔之楔 id: {bonus.missing}（其词条未计入面板）")


def _collect_char_bonus(
    role_detail: RoleDetail,
    bonus: AttributeBonus,
) -> None:
    """累加角色自身加成（DOB 数据包 char.加成）

    该字段是游戏内技能解锁被动（伤害/增益节点）的聚合总值，
    与 wiki 逐条被动合计一致，因此默认全部计入、无需条件判定。
    """
    entry = get_role_panel_entry(role_detail)
    if not entry:
        return
    char_bonus = dob_loader.get_char_bonus(entry)
    bonus.add(char_bonus)
    reduce = (char_bonus.get("extra") or {}).get("减伤")
    if reduce:
        bonus.reduce_sources.append(float(reduce) / 100)


def _condition_snapshot(base_main: dict[str, float], bonus: AttributeBonus) -> dict[str, float]:
    """从当前加成汇总出「属性门槛」条件用的面板属性快照

    口径与 dna-builder 的 attrs 一致：率类 = 1 + 加成（小数，如 3.5 = 350%），
    昂扬/背水/充盈威力 = 0 基准小数，神智 = 最终值。
    """
    return {
        "神智": float(base_main.get("最大神志", 0.0) or 0.0) * (1 + bonus.main.get("最大神志", 0.0) / 100),
        "技能威力": 1 + bonus.rate.get("技能威力", 0.0) / 100,
        "技能效益": 1 + bonus.rate.get("技能效益", 0.0) / 100,
        "技能耐久": 1 + bonus.rate.get("技能耐久", 0.0) / 100,
        "技能范围": 1 + bonus.rate.get("技能范围", 0.0) / 100,
        "昂扬": bonus.rate.get("昂扬", 0.0) / 100,
        "充盈威力": (bonus.rate.get("充盈威力", 0.0) + bonus.extra.get("充盈威力", 0.0)) / 100,
    }


def collect_attribute_bonus(
    role_detail: RoleDetail,
    con_weapon_detail: WeaponDetail | None = None,
    base_main: dict[str, float] | None = None,
) -> AttributeBonus:
    """汇总角色魔之楔 + 角色加成的面板加成（含条件生效，不动点迭代至收敛）

    与 dna-builder 的循环同构：先按静态条件（趋向/*id）算一轮 → 用当前属性
    快照判「属性门槛」类条件 → 有变化就带着新快照重算，最多 3 轮收敛
    （门槛条件均为 >= 型、加成只增不减，必然单调收敛）。

    ⚠️ 不收 ``con_weapon_detail.modes`` —— 同律武器的专属 mod 只进
    同律武器自己的面板，不进角色面板。
    """
    if base_main is None:
        base_main, _ = _base_main_values(role_detail)

    def _run(snapshot: dict[str, float] | None) -> AttributeBonus:
        bonus = AttributeBonus()
        _collect_modes(role_detail.modes, bonus, snapshot)
        _collect_char_bonus(role_detail, bonus)
        return bonus

    bonus = _run(None)
    snapshot = _condition_snapshot(base_main, bonus)
    for _ in range(3):
        next_bonus = _run(snapshot)
        next_snapshot = _condition_snapshot(base_main, next_bonus)
        if next_snapshot == snapshot:
            return next_bonus
        bonus, snapshot = next_bonus, next_snapshot
    return bonus


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
    # 隐藏属性行（增伤/技能伤害/减伤/有效生命/充盈威力 及其他非零隐藏属性），
    # 渲染在标准 12 行之后
    hidden_rows: list[tuple[str, str]] = field(default_factory=list)


def _official_main_values(role_detail: RoleDetail) -> dict[str, float]:
    """官方 ``attribute`` 里能取到的四维裸值（回退用，口径不统一）"""
    out: dict[str, float] = {}
    for name, field_name in _MAIN_KEYS.items():
        if name == "护盾":
            continue
        v = getattr(role_detail.attribute, field_name, None)
        if v is not None:
            out[name] = float(v)
    es = getattr(role_detail.attribute, "maxES", None)
    if es is not None:
        out["护盾"] = float(es)
    return out


def _base_main_values(role_detail: RoleDetail) -> tuple[dict[str, float], str]:
    """返回四维基础值 + 来源标记（DOB 数据包按角色实际等级缩放，逐项回退官方 attribute）

    DOB 条目的 baseLv1 是 1 级白值，查询侧乘 ``COMMON_LEVEL_UP[level-1]`` 得到
    实际等级的基础值（攻击两位小数、生命/护盾取整，与 dna-builder 一致）；
    等级未知回退 80 级。缺的项单独用官方值补，不整组否掉。
    """
    entry = get_role_panel_entry(role_detail)
    official = _official_main_values(role_detail)
    got: dict[str, float] = {}
    source = "attribute"

    if entry:
        base = dob_loader.scaled_base(entry, getattr(role_detail, "level", None))
        for name in _MAIN_KEYS:
            _v = base.get(name)
            if _v is not None:
                got[name] = float(_v)
        # DOB 提供了攻击即认可（四维里最关键、也是面板纠错的主要来源）
        if "攻击" in got:
            source = "dob"

    if source != "dob":
        # 整组回退：官方 attribute
        return dict(official), source

    # 逐项补齐 DOB 里缺的（如「护盾」）
    for name, val in official.items():
        if name not in got:
            got[name] = val
    return got, source


def _role_element_cn(role_detail: RoleDetail) -> str:
    """角色自身属性（中文单字：光/暗/水/火/雷/风），取自 DOB 数据"""
    entry = get_role_panel_entry(role_detail)
    elem = str((entry or {}).get("element") or "")
    return elem if elem in ("光", "暗", "水", "火", "雷", "风") else ""


def _elem_atk_multiplier(bonus: AttributeBonus, role_detail: RoleDetail) -> float:
    """属性攻击独立乘区的倍率

    ``bonus.elem_atk`` 的键是单个属性字（``{"光": 33.0}``）。只有与角色
    **自身属性一致**时才生效；mod 未限定属性时按角色属性生效
    （判定在 dob_loader.parse_attrs / is_elem_atk_effective 阶段已完成）。
    """
    if not bonus.elem_atk:
        return 1.0
    cn = _role_element_cn(role_detail)
    total = 0.0
    for key, val in bonus.elem_atk.items():
        k = str(key)
        if cn:
            if cn not in k:
                continue
        elif k:  # 角色属性未知：保守起见不计
            continue
        total += float(val)
    return 1.0 + total / 100.0


@dataclass(slots=True)
class AttrContext:
    """本地伤害/面板共用的属性上下文

    tt 是技能字段四大乘区（1 起始乘数，含 dna-builder 的上限截断：
    效益 175% / 范围 280% / 耐久 400%）。
    """

    base_main: dict[str, float]
    bonus: AttributeBonus
    final_main: dict[str, float]
    elem_mult: float
    reduce_frac: float
    source: str
    matched: bool
    tt: dict[str, float]


def compute_attr_context(
    role_detail: RoleDetail,
    con_weapon_detail: WeaponDetail | None = None,
) -> AttrContext:
    """计算面板与本地伤害共用的属性上下文（最终四维原始值 + 技能乘区）"""
    base_main, source = _base_main_values(role_detail)
    bonus = collect_attribute_bonus(role_detail, con_weapon_detail, base_main)
    elem_mult = _elem_atk_multiplier(bonus, role_detail)
    reduce_frac = dob_loader.get_damage_reduce(bonus.reduce_sources)

    final_main: dict[str, float] = {}
    for name in _MAIN_KEYS:
        base_value = base_main.get(name)
        if base_value is None:
            continue
        final_value = float(base_value) * (1 + bonus.main.get(name, 0.0) / 100)
        if name == "攻击":
            final_value *= elem_mult
        final_main[name] = final_value

    def _rate1(key: str) -> float:
        return 1 + bonus.rate.get(key, 0.0) / 100

    tt = {
        "技能威力": _rate1("技能威力"),
        "技能范围": min(_rate1("技能范围"), 2.8),
        "技能耐久": min(_rate1("技能耐久"), 4),
        "技能效益": min(_rate1("技能效益"), 1.75),
    }
    return AttrContext(
        base_main=base_main,
        bonus=bonus,
        final_main=final_main,
        elem_mult=elem_mult,
        reduce_frac=reduce_frac,
        source=source,
        matched=get_role_panel_entry(role_detail) is not None,
        tt=tt,
    )


def compute_final_attribute(
    role_detail: RoleDetail,
    con_weapon_detail: WeaponDetail | None = None,
) -> FinalAttribute:
    """本地计算角色最终属性，返回面板标准行 + 隐藏属性行"""
    ctx = compute_attr_context(role_detail, con_weapon_detail)
    bonus = ctx.bonus
    source = ctx.source
    matched = ctx.matched
    # 减伤：逐来源乘法聚合（小数），显示与有效生命共用
    reduce_frac = ctx.reduce_frac

    rows: list[tuple[str, str]] = []
    final_main = dict(ctx.final_main)

    # 四维：基础 × (1 + 加成/100)（已在 compute_attr_context 中算好原始值）
    for name in _MAIN_KEYS:
        if name not in final_main:
            continue
        rows.append((name, _fmt_value(final_main[name], percent=False)))

    # 率类：100 + 加成
    for key, display in _RATE_DISPLAY.items():
        pct = bonus.rate.get(key, 0.0)
        rows.append((display, _fmt_value(100 + pct, percent=True)))

    # 昂扬 / 背水：0 + 加成
    for key, display in _EXTRA_DISPLAY.items():
        pct = bonus.rate.get(key, 0.0)
        rows.append((display, _fmt_value(pct, percent=True)))

    # 充盈威力：显示口径与率类一致（白板 100% + 加成）；伤害结算公式仍为 (1 + 充盈威力增量)
    fullness = bonus.rate.get("充盈威力", 0.0) + bonus.extra.get("充盈威力", 0.0)
    rows.append(("充盈威力", _fmt_value(100 + fullness, percent=True)))

    # ── 隐藏属性行（0 基准，渲染在标准行之后）──────────────────
    hidden: list[tuple[str, str]] = [
        ("增伤", _fmt_value(bonus.extra.get("增伤", 0.0), percent=True)),
        ("技能伤害", _fmt_value(bonus.extra.get("技能伤害", 0.0), percent=True)),
        ("减伤", _fmt_value(reduce_frac * 100, percent=True)),
    ]

    # 有效生命 = (最终生命 ÷ (1 - 防御/(300+防御)) + 最终护盾) ÷ (1 - 减伤)
    # （防御系数 300 为引擎常量，见 dna-builder CharBuild）
    hp = final_main.get("生命")
    defense = final_main.get("防御")
    if hp is not None and defense is not None and hp > 0 and defense >= 0:
        shield = final_main.get("护盾", 0.0)
        ehp = (hp / (1 - defense / (300 + defense)) + shield) / (1 - reduce_frac)
        hidden.append(("有效生命", _fmt_value(ehp, percent=False)))

    # 其余非零隐藏属性（追加伤害/多重/歧视/攻击范围…）按名追加
    for key in sorted(bonus.extra):
        if key in ("增伤", "技能伤害", "减伤", "充盈威力"):
            continue
        if abs(bonus.extra[key]) > 1e-9:
            hidden.append((key, _fmt_value(bonus.extra[key], percent=True)))

    return FinalAttribute(rows=rows, base_source=source, matched=matched, hidden_rows=hidden)


__all__ = [
    "AttributeBonus",
    "FinalAttribute",
    "collect_attribute_bonus",
    "compute_final_attribute",
    "get_role_panel_entry",
    "reload_role_panel",
]
