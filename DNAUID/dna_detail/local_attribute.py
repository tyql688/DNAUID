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
2. **角色加成**（数据包 ``char.加成``）—— 技能解锁被动的两档合计值
   （验证：芙罗拉 昂扬 15% = 6% + 9%、贝蕾妮卡 攻击 50% = 20% + 30%）。
   **按官方 ``get_skill_extend_level`` 还原档位**：第 1 档技能 4 级解锁、
   第 2 档 8 级解锁，两档比例固定 40%:60%。
3. **同律武器精炼被动** —— 数据包 ``char.同律武器`` 提供同律武器白值；
   精炼被动数值仍在补，暂不计入。
   ⚠️ 同律武器的**专属 mod** 只进「同律武器自己的面板」，**不进角色面板**，
   所以这里**不累加**同律武器的专属 mod。

数据文件
--------
``DNAUID/dna_mod/data/dob_data.json``（由 ``dna_mod/dob_pack.py`` 生成）
"""

from __future__ import annotations

import re
from dataclasses import field, dataclass

from gsuid_core.logger import logger

from ..dna_mod import dob_loader
from ..utils.api.model import Mode, RoleDetail, WeaponDetail
from ..dna_mod.dob_types import CharEntry, ModRecord, ParsedAttrs, WeaponRecord

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


def get_role_panel_entry(role_detail: RoleDetail) -> CharEntry | None:
    """按游戏 charId（优先）或角色名找到 DOB 数据条目"""
    entry = dob_loader.get_char(role_detail.charId)
    if entry:
        return entry
    return dob_loader.get_char_by_name(role_detail.charName)


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

    def add(self, parsed: ParsedAttrs) -> None:
        for bucket, zone in (
            (self.main, parsed["main"]),
            (self.rate, parsed["rate"]),
            (self.elem_atk, parsed["elem_atk"]),
            (self.flat, parsed["flat"]),
            (self.extra, parsed["extra"]),
        ):
            for key, value in zone.items():
                bucket[key] = bucket.get(key, 0.0) + float(value)
        self.raw.extend(parsed["raw"])


def _weapon_record_of(role_detail: RoleDetail, weapon_detail: WeaponDetail | None) -> WeaponRecord | None:
    """取武器记录（与武器面板/伤害共用同一查找：按**请求 id** 匹配）

    不能拿角色的同律武器顶替查不到的普通武器 —— 否则未收录的普通武器会被算进
    同律武器的类别计数（如「锋芒」增伤按两把单手剑算成 12%）。
    """
    if weapon_detail is None:
        return None
    from .local_weapon_attribute import resolve_weapon_record

    record, _is_skill = resolve_weapon_record(weapon_detail, role_detail)
    return record


def _is_inherit_skill_weapon(rec: WeaponRecord | None) -> bool:
    """是否继承型同律武器（圆舞/剑非剑/疑星落 —— 复用被继承的近战/远程面板）

    dna-builder 对这类武器一律不单独计数（类别计数、充盈威力汇总都排除），
    因为它与被继承的那把武器共用同一份面板。
    """
    return rec is not None and bool(rec.get("inherit"))


def collect_weapon_categories(
    role_detail: RoleDetail,
    weapon_details: list[WeaponDetail | None],
) -> dict[str, int]:
    """统计已装备武器的「类别」计数（条件词条按武器类别取值用，如 锋芒 增伤 [0.06, 0.18]）

    与 dna-builder ``CharBuild.getConditionValues`` 同口径：近战/远程各计 1，
    **继承型同律武器不额外计**（``if (this.skillWeapon && !this.skillWeapon.inherit)``），
    空武器槽位不参与计数。
    """
    counts: dict[str, int] = {}
    for wd in weapon_details:
        rec = _weapon_record_of(role_detail, wd)
        if _is_inherit_skill_weapon(rec):
            continue
        cat = dob_loader.weapon_category(rec)
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    return counts


def collect_weapon_forge_bonus(
    role_detail: RoleDetail,
    weapon_details: list[WeaponDetail | None],
) -> list[ParsedAttrs]:
    """近战/远程武器自身的精炼「加成」→ 解析后的面板分区（逐把一份）

    与 dna-builder 同口径：``getTotalBonus(attr, "角色")`` 会把 melee / ranged
    **武器实例的「加成」**计入角色属性（``isWeaponForgeEffective`` 为真时 ——
    即无熔炉，或角色精通该武器类别）；**同律武器不在 melee/ranged 来源表里，
    不计入角色面板**，所以这里跳过同律武器。
    """
    parsed_list: list[ParsedAttrs] = []
    for weapon_detail in weapon_details:
        if weapon_detail is None:
            continue
        record = _weapon_record_of(role_detail, weapon_detail)
        if record is None or dob_loader.is_skill_weapon(record):
            continue
        if record.get("hasForge") and not dob_loader.is_weapon_mastered(role_detail.charId, record):
            continue
        bonus = dob_loader.weapon_forge_bonus(record, weapon_detail.skillLevel)
        if not bonus:
            continue
        # 数据包的武器记录没有 element 字段，属性攻击键恒按角色自身属性结算
        parsed = dob_loader.parse_attrs(bonus, None)
        # 武器自身「加成」的武器作用域属性只进该武器面板（dna-builder 只进 table.melee/ranged），
        # 不能进 bonus.extra —— 否则会经「角色侧穿透」泄漏到另一把武器。
        for zone in (parsed["main"], parsed["rate"], parsed["extra"]):
            for key in dob_loader.WEAPON_SCOPE_KEYS:
                zone.pop(key, None)
        parsed_list.append(parsed)
    return parsed_list


def _collect_modes(
    modes: list[Mode] | None,
    bonus: AttributeBonus,
    attrs_snapshot: dict[str, float] | None = None,
    weapon_categories: dict[str, int] | None = None,
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
    matched: list[tuple[Mode, ModRecord]] = []
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
        effect = rec.get("effect")
        if effect and dob_loader.is_effect_effective(
            effect.get("conditions", []),
            polarity_count,
            id_count,
            attrs_snapshot,
        ):
            # 数组形态的条件属性（如 锋芒 增伤 [0.06, 0.18]）按
            # min(条件属性值 × v1, v2) 结算，条件属性值来自极性/id 计数与属性快照
            base_values: dict[str, float] = {"*id": float(max(id_count.values())) if id_count else 0.0}
            for pol, count in polarity_count.items():
                base_values[f"{pol}趋向"] = float(count)
            if attrs_snapshot is not None:
                base_values.update(attrs_snapshot)
            # 武器类别计数（如 锋芒 的 ["单手剑","*"] → min(单手剑数量 × v1, v2)）
            if weapon_categories is not None:
                base_values.update(weapon_categories)
            eff_attrs = dob_loader.get_effect_attrs(rec, mode.level, base_values)
            bonus.add(dob_loader.parse_attrs(eff_attrs, rec.get("element")))
            if isinstance(eff_attrs.get("减伤"), (int, float)):
                bonus.reduce_sources.append(float(eff_attrs["减伤"]))
    if bonus.missing:
        # 诊断：数据包未收录的魔之楔 id（新版游戏先于数据包更新时会出现）
        logger.warning(f"[DNA 面板] 数据包未收录的魔之楔 id: {bonus.missing}（其词条未计入面板）")


# 两档比例与解锁等级：官方 get_skill_extend_level 为 >=4 第 1 档、>=8 第 2 档；
# 比例 40%:60% 是 33 个角色的实测值（数据包只给两档合计）。
_PASSIVE_TIER_RATIO = (0.4, 0.6)
_PASSIVE_UNLOCK_LEVELS = (4, 8)

# 溯源文案里的技能等级加成，形如「[残光]等级+2」
_SKILL_LEVEL_BONUS_RE = re.compile(r"\[([^\]]+)]\s*等级\s*\+\s*(\d+)")


def _skill_base_levels(role_detail: RoleDetail) -> list[int]:
    """官方 ``skills`` 的**基础**等级（扣掉溯源加成），下标与 ``role_detail.skills`` 一致

    接口返回的 ``level`` 含溯源加成（如「[残光]等级+2」），解锁判定必须用基础等级，
    否则会提前计入档位（贝蕾妮卡 残光 接口 3 级、溯源 +2 → 基础 1 级）。
    溯源只算前 ``gradeLevel`` 条（与官方 H5 口径一致）。
    """
    bonus: dict[str, int] = {}
    for trace in role_detail.traces[: role_detail.gradeLevel]:
        for name, text in _SKILL_LEVEL_BONUS_RE.findall(trace.description):
            bonus[name] = bonus.get(name, 0) + int(text)
    return [max(1, skill.level - bonus.get(skill.skillName, 0)) for skill in role_detail.skills]


def _passive_tier_ratio(level: int | None) -> float:
    """按技能等级取该被动的计入比例（**估算**）

    ``>=8`` 全计、``>=4`` 只计第 1 档、其余不计。技能不在官方返回里
    （``level is None``）时按「默认已学会」全计 —— 端口没返回不代表没学。

    ⚠️ 这是估算，不是真值：真实门槛是「突破 5 阶 / 75 级 + **逐节点点亮**」
    （节点要消耗材料），而 App 不返回节点点亮状态。实测有角色技能 8 级却
    一个被动都没学（塔比瑟 攻击被动实际 0%，本估算会给 50%）。
    """
    if level is None:
        return 1.0
    if level >= _PASSIVE_UNLOCK_LEVELS[1]:
        return 1.0
    if level >= _PASSIVE_UNLOCK_LEVELS[0]:
        return _PASSIVE_TIER_RATIO[0]
    return 0.0


def _collect_char_bonus(
    role_detail: RoleDetail,
    bonus: AttributeBonus,
) -> None:
    """累加角色自身的技能解锁被动（数据包 ``char.加成``）

    数据包只给「两档合计」、没有解锁条件，这里按官方 ``get_skill_extend_level``
    的 4/8 级规则还原档位（两档比例 40%:60%），技能等级用**扣掉溯源**的基础等级。
    ⚠️ **属估算**：App 不返回技能节点是否点亮，只能按基础等级推断。
    每条被动挂在哪个技能下由转换阶段写入 ``passives[].skill`` / ``index``。
    """
    entry = get_role_panel_entry(role_detail)
    if not entry:
        return
    levels = _skill_base_levels(role_detail)
    by_name = {skill.skillName: levels[index] for index, skill in enumerate(role_detail.skills)}
    buckets = {
        "main": bonus.main,
        "rate": bonus.rate,
        "elem_atk": bonus.elem_atk,
        "extra": bonus.extra,
    }
    for passive in entry.get("passives", []):
        level = by_name.get(passive["skill"] or "")
        if level is None and passive["index"] < len(levels):
            # 名字对不上时按同一顺序回退（官方 skills 顺序与数据包一致）
            level = levels[passive["index"]]
        ratio = _passive_tier_ratio(level)
        if ratio <= 0:
            continue
        value = float(passive["value"]) * ratio
        key = passive["key"]
        bucket = buckets[passive["zone"]]
        bucket[key] = bucket.get(key, 0.0) + value
        if passive["zone"] == "extra" and key == "减伤":
            bonus.reduce_sources.append(value / 100)


def _condition_snapshot(base_main: dict[str, float], bonus: AttributeBonus) -> dict[str, float]:
    """从当前加成汇总出「属性门槛」条件用的面板属性快照

    口径与 dna-builder 的 attrs 一致：率类 = 1 + 加成（小数，如 3.5 = 350%），
    昂扬/背水/充盈威力 = 0 基准小数，神智 = 最终值；
    效益/范围/耐久与技能计算共用同一套上限截断（175%/280%/400%）。
    """
    return {
        "神智": float(base_main.get("神智", 0.0) or 0.0) * (1 + bonus.main.get("神智", 0.0) / 100),
        "技能威力": 1 + bonus.rate.get("技能威力", 0.0) / 100,
        "技能效益": min(1 + bonus.rate.get("技能效益", 0.0) / 100, 1.75),
        "技能耐久": min(1 + bonus.rate.get("技能耐久", 0.0) / 100, 4),
        "技能范围": min(1 + bonus.rate.get("技能范围", 0.0) / 100, 2.8),
        "昂扬": bonus.rate.get("昂扬", 0.0) / 100,
        "充盈威力": (bonus.rate.get("充盈威力", 0.0) + bonus.extra.get("充盈威力", 0.0)) / 100,
    }


def collect_attribute_bonus(
    role_detail: RoleDetail,
    base_main: dict[str, float] | None = None,
    weapon_categories: dict[str, int] | None = None,
    weapon_details: list[WeaponDetail | None] | None = None,
) -> AttributeBonus:
    """汇总角色魔之楔 + 角色加成 + 携带武器加成的面板加成（含条件生效，不动点迭代至收敛）

    与 dna-builder 的循环同构：先按静态条件（趋向/*id）算一轮 → 用当前属性
    快照判「属性门槛」类条件 → 有变化就带着新快照重算，最多 3 轮收敛
    （门槛条件均为 >= 型、加成只增不减，必然单调收敛）。

    ⚠️ 同律武器的专属 mod 只进同律武器自己的面板，**不进角色面板**。
    ✅ 收**近战/远程武器自身的「加成」**（``collect_weapon_forge_bonus``）
    —— dna-builder ``getTotalBonus(attr, "角色")`` 会把它计入角色属性。
    """
    if base_main is None:
        base_main, _ = _base_main_values(role_detail)
    details = weapon_details if weapon_details is not None else []
    forge_parsed = collect_weapon_forge_bonus(role_detail, details)

    def _run(snapshot: dict[str, float] | None) -> AttributeBonus:
        bonus = AttributeBonus()
        _collect_modes(role_detail.modes, bonus, snapshot, weapon_categories)
        _collect_char_bonus(role_detail, bonus)
        for parsed in forge_parsed:
            bonus.add(parsed)
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
    # 本次计算用的加成汇总（含条件生效块）；武器面板/伤害结算需要它取
    # 「可穿透到武器」的角色侧属性（暴击/暴伤/触发/攻速），避免重复计算
    bonus: AttributeBonus | None = None
    # 隐藏属性行（增伤/技能伤害/减伤/有效生命/充盈威力 及其他非零隐藏属性），
    # 渲染在标准 12 行之后
    hidden_rows: list[tuple[str, str]] = field(default_factory=list)


def _official_main_values(role_detail: RoleDetail) -> dict[str, float]:
    """官方 ``attribute`` 里能取到的四维裸值（回退用，口径不统一）"""
    attribute = role_detail.attribute
    return {
        "攻击": float(attribute.atk),
        "生命": float(attribute.maxHp),
        "防御": float(attribute.defense),
        "神智": float(attribute.maxSp),
        "护盾": float(attribute.maxES),
    }


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
        base = dob_loader.scaled_base(entry, role_detail.level)
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
    elem = entry.get("element", "") if entry else ""
    return elem if elem in _ELEMENT_NAMES_CN else ""


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


def collect_fullness_conversion(
    role_detail: RoleDetail,
    weapon_details: list[WeaponDetail | None] | None,
    bonus: AttributeBonus | None = None,
) -> float:
    """武器触发率溢出 100% 的部分按该武器「充盈转化」转为角色「充盈威力」

    与 dna-builder ``CharBuild.getWeaponFullness`` 同口径：

        触发率 = 武器面板触发率（基础触发 × (1 + 武器自身精炼加成 + 该武器槽 mod + 角色侧穿透)）
        转化率 = 1 + 该武器槽 mod 的充盈转化加成（基础 1）
        贡献   = max(0, 触发率 - 1) × 转化率

    触发率必须复用武器面板的完整口径 —— 只算该武器槽的 mod 会漏掉武器自身精炼加成
    （如 孤子的缚锁 精炼 5 的 触发 +150%）。返回百分比增量（如 18.0 表示 +18%）。
    """
    from .local_weapon_attribute import resolve_weapon_panel

    details = weapon_details if weapon_details is not None else []
    total = 0.0
    for weapon_detail in details:
        if weapon_detail is None:
            continue
        rec = _weapon_record_of(role_detail, weapon_detail)
        if _is_inherit_skill_weapon(rec):
            # 继承型同律武器复用被继承武器的面板，不单独计入
            # （dna-builder CharBuild.getAllFullnessWeapons 同样排除）
            continue
        conversion = 1.0  # 每把武器固定的基础转化 1
        for mode in weapon_detail.modes:
            attrs = dob_loader.get_mod_attrs(mode.id, mode.level, mode.quality)
            if not attrs:
                continue
            conversion += attrs.get("充盈转化", 0.0)
        panel = resolve_weapon_panel(weapon_detail, role_detail, bonus)
        trigger_rate = round(panel.trigger * 100) / 100
        total += max(0.0, trigger_rate - 1.0) * conversion * 100
    return total


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
    # 武器触发率溢出 100% 的部分按「充盈转化」转成的「充盈威力」增量（百分比）
    fullness_weapon: float = 0.0


def compute_attr_context(
    role_detail: RoleDetail,
    weapon_categories: dict[str, int] | None = None,
    weapon_details: list[WeaponDetail | None] | None = None,
) -> AttrContext:
    """计算面板与本地伤害共用的属性上下文（最终四维原始值 + 技能乘区）

    同一张卡片只调一次，结果交给 ``compute_final_attribute`` 与
    ``draw_local_damage_section`` 共用，避免重复跑不动点迭代。
    """
    base_main, source = _base_main_values(role_detail)
    bonus = collect_attribute_bonus(
        role_detail,
        base_main,
        weapon_categories,
        weapon_details,
    )
    elem_mult = _elem_atk_multiplier(bonus, role_detail)
    reduce_frac = dob_loader.get_damage_reduce(bonus.reduce_sources)
    fullness_weapon = collect_fullness_conversion(role_detail, weapon_details, bonus)

    final_main: dict[str, float] = {}
    for name in _MAIN_KEYS:
        base_value = base_main.get(name)
        if base_value is None:
            continue
        final_value = float(base_value) * (1 + bonus.main.get(name, 0.0) / 100)
        if name == "攻击":
            # 攻击吃「属性攻击」独立乘区，保留两位小数（dna-builder calculateAttributes）
            final_value = round(final_value * elem_mult * 100) / 100
        else:
            # 生命/护盾/防御/神智最终取整（dna-builder Math.round）
            final_value = round(final_value)
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
        fullness_weapon=fullness_weapon,
    )


def compute_final_attribute(
    role_detail: RoleDetail,
    weapon_categories: dict[str, int] | None = None,
    weapon_details: list[WeaponDetail | None] | None = None,
    ctx: AttrContext | None = None,
) -> FinalAttribute:
    """本地计算角色最终属性，返回面板标准行 + 隐藏属性行

    ``ctx`` 传已算好的 ``AttrContext`` 时直接复用（与伤害区块共用同一份）。
    """
    if ctx is None:
        ctx = compute_attr_context(role_detail, weapon_categories, weapon_details)
    bonus = ctx.bonus
    source = ctx.source
    matched = ctx.matched
    # 减伤：逐来源乘法聚合（小数），显示与有效生命共用
    reduce_frac = ctx.reduce_frac

    rows: list[tuple[str, str]] = []
    final_main = dict(ctx.final_main)

    # 四维：基础 × (1 + 加成/100)（已在 compute_attr_context 中算好原始值）
    # 「攻击」按角色自身属性显示为「X属性攻击」（与游戏面板一致）
    elem_cn = _role_element_cn(role_detail)
    for name in _MAIN_KEYS:
        if name not in final_main:
            continue
        display = f"{elem_cn}属性攻击" if (name == "攻击" and elem_cn) else _PANEL_DISPLAY_NAME.get(name, name)
        rows.append((display, _fmt_value(final_main[name], percent=False)))

    # 率类：100 + 加成；效益/范围/耐久与技能计算共用上限截断（ctx.tt）
    for key, display in _RATE_DISPLAY.items():
        if key in ctx.tt:
            rows.append((display, _fmt_value(ctx.tt[key] * 100, percent=True)))
        else:
            rows.append((display, _fmt_value(100 + bonus.rate.get(key, 0.0), percent=True)))

    # 昂扬 / 背水：0 + 加成
    for key, display in _EXTRA_DISPLAY.items():
        pct = bonus.rate.get(key, 0.0)
        rows.append((display, _fmt_value(pct, percent=True)))

    # 充盈威力：显示口径与率类一致（白板 100% + 加成）；伤害结算公式仍为 (1 + 充盈威力增量)
    # 加成 = 角色 mod 的充盈威力 + Σ 武器触发率溢出 × 该武器充盈转化（dna-builder calculateWeaponAttributes）
    fullness = bonus.rate.get("充盈威力", 0.0) + bonus.extra.get("充盈威力", 0.0) + ctx.fullness_weapon
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
        # 增伤/技能伤害/减伤/充盈威力/充盈转化 已有专门行；暴击/暴伤/触发/攻速 是武器作用域
        # 属性（attrAllowCharToWeapon 白名单），只在武器面板显示，故不列进隐藏行。
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
        base_source=source,
        matched=matched,
        hidden_rows=hidden,
        bonus=bonus,
    )


__all__ = [
    "AttrContext",
    "AttributeBonus",
    "FinalAttribute",
    "collect_attribute_bonus",
    "collect_weapon_categories",
    "collect_fullness_conversion",
    "compute_attr_context",
    "compute_final_attribute",
    "get_role_panel_entry",
]
