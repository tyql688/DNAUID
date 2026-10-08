"""DOB（dna-builder）数据包数据的加载与查询 —— 替代旧 wiki_loader / loader

数据文件由 ``dob_pack.py`` 从数据包转换生成（``dna_mod/data/dob_data.json``）：
    {
      "_meta": {...},
      "byCharId": {"1501": {...base/bonus/conWeapons...}}, "byName": {...},
      "mods": {"byId": {"51421": {...attrs 满级小数...}}},
      "weapons": {"byId": {...}}
    }

口径要点：
- **魔之楔等级缩放在查询侧完成**：记录里是满级值（小数），
  当前值 = 满级值 / (maxLevel + 1) × (等级 + 1)（与 dna-builder LeveledMod 一致）；
  架势类 mod（id 在 100000~150000 / 200000~250000 区间）数值不随等级缩放。
- **属性值统一输出为百分比**（小数 ×100），main/rate/elem_atk 三个分区与面板公式对齐。
- 官方接口 ``modes[].id`` 与数据包 mod id 同源，直接按 id 查，无需映射表。
- **武器攻击的精通倍率**：命中精通 ×1.2、未命中 ×1.0；同律武器绑定角色必然命中
  （``weapon_mastery_ratio``）。
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable

from gsuid_core.logger import logger

from .dob_pack import DATA_PATH
from .dob_types import (
    DobData,
    CharEntry,
    Condition,
    ModRecord,
    SkillEntry,
    ParsedAttrs,
    WeaponRecord,
    ResolvedSkillField,
)

DATA_FILE = DATA_PATH

# 品质数值 → 中文名（官方接口 quality 1~5）
QUALITY_TO_KEY: dict[int, str] = {1: "白", 2: "绿", 3: "蓝", 4: "紫", 5: "金"}

# 元素数值 → 中文（官方接口 element 口径）
ELEMENT_NAMES: dict[int, str] = {
    0: "无",
    1: "暗",
    2: "光",
    3: "水",
    4: "火",
    5: "雷",
    6: "风",
}

# 架势类 mod：数值不随等级缩放
_STANCE_RANGES = ((100000, 150000), (200000, 250000))

_data: DobData = {}


def _load() -> None:
    global _data
    if not DATA_FILE.exists():
        logger.warning(f"[DNA DOB] 数据包数据缺失: {DATA_FILE}")
        _data = {}
        return
    # 数据包来自网络下载，属不可信外部输入，解析失败只告警不中断（AGENTS §1.1 例外）
    try:
        _data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        logger.warning(f"[DNA DOB] 数据包解析失败: {error}")
        _data = {}
        return
    meta = _data.get("_meta", {})
    logger.info(
        f"[DNA DOB] 数据已加载: v{meta.get('packVersion')}"
        f"（角色 {meta.get('chars')} / 魔之楔 {meta.get('mods')} / 武器 {meta.get('weapons')}）"
    )


def reload() -> None:
    _load()


_load()


def is_loaded() -> bool:
    mods = _data.get("mods")
    return bool(mods and mods.get("byId"))


def version() -> str | None:
    meta = _data.get("_meta")
    return meta.get("packVersion") if meta else None


def built_at() -> str | None:
    meta = _data.get("_meta")
    return meta.get("packBuiltAt") if meta else None


def mod_count() -> int:
    mods = _data.get("mods")
    by_id = mods.get("byId") if mods else None
    return len(by_id) if by_id else 0


def char_count() -> int:
    return len(_data.get("byCharId", {}))


def weapon_count() -> int:
    weapons = _data.get("weapons")
    by_id = weapons.get("byId") if weapons else None
    return len(by_id) if by_id else 0


# ── 角色查询 ─────────────────────────────────────────────────


def get_char(char_id: int | str | None) -> CharEntry | None:
    """按游戏 charId 取角色面板数据条目"""
    if char_id is None:
        return None
    return _data.get("byCharId", {}).get(str(char_id))


def get_char_by_name(name: str | None) -> CharEntry | None:
    """按角色名取数据条目（id 查不到时兜底）"""
    if not name:
        return None
    cid = _data.get("byName", {}).get(name)
    return get_char(cid) if cid else None


def level_multiplier(level: int | None) -> float | None:
    """角色等级 → 成长倍率（1~80）；等级无效返回 None"""
    if level is None:
        return None
    table = _data.get("commonLevelUp", [])
    if level < 1 or level > len(table):
        return None
    return table[level - 1]


def scaled_base(char: CharEntry | None, level: int | None) -> dict[str, float]:
    """角色基础值按实际等级缩放（与 dna-builder LeveledChar 同口径）

    - 攻击：round(1 级白值 × 倍率, 2)；
    - **生命 / 护盾保留原始小数，不在中间步骤取整** —— 游戏与官方接口都不取整
      （法露茜 200 × 12.5522 = 2510.44，再乘 7 倍加成 = 17573.08 → 17573；
      dna-builder 的 `Math.round` 中间取整会得到 2510 × 7 = 17570，差 3）。
      最终取整统一由 ``local_attribute.compute_attr_context`` 负责；
    - 防御 / 神智不随等级成长，原样返回；
    - 等级缺失或超出 1~80 时回退 80 级值（``base`` 字段）。
    """
    if not char:
        return {}
    base80 = char.get("base", {})
    multiplier = level_multiplier(level)
    lv1 = char.get("baseLv1")
    if multiplier is None or not lv1:
        return {
            "攻击": base80.get("攻击", 0.0),
            "生命": base80.get("生命", 0.0),
            "护盾": base80.get("护盾", 0.0),
            "防御": base80.get("防御", 0.0),
            "神智": base80.get("神智", 0.0),
        }
    return {
        "攻击": round(lv1.get("攻击", 0.0) * multiplier + 1e-9, 2),
        "生命": lv1.get("生命", 0.0) * multiplier,
        "护盾": lv1.get("护盾", 0.0) * multiplier,
        "防御": lv1.get("防御", base80.get("防御", 0.0)),
        "神智": lv1.get("神智", base80.get("神智", 0.0)),
    }


# ── 魔之楔查询 ───────────────────────────────────────────────


def get_by_third_id(third_id: int | str | None) -> ModRecord | None:
    """按官方接口 modes[].id（= 数据包 mod id）取记录"""
    if third_id is None:
        return None
    mods = _data.get("mods")
    by_id = mods.get("byId") if mods else None
    return by_id.get(str(third_id)) if by_id else None


def _is_stance(mod_id: int | None) -> bool:
    if mod_id is None:
        return False
    return any(low < mod_id < high for low, high in _STANCE_RANGES)


def get_mod_attrs(
    third_id: int | str | None,
    level: int | None,
    quality: int | None = None,
) -> dict[str, float] | None:
    """取某魔之楔在指定强化等级下的属性（小数，如 攻击 0.56 = +56%）

    Args:
        third_id: 官方接口 modes[].id
        level: 强化等级（+N，0 ~ maxLevel）
        quality: 品质数值（1~5），仅用于校验，实际品质由 id 对应记录决定

    Returns:
        {属性键: 当前等级小数值}；查不到记录返回 None

    口径（与 dna-builder LeveledMod.updateProperties 一致）：
    - 数值属性按 ``满级值 / (maxLevel + 1) × (等级 + 1)`` 线性缩放；
    - **数组型属性**（如 追袭 ``技能伤害 [-0.5]``）逐档取值不缩放，
      下标 = min(等级 + 1, 长度) - 1；
    - **固定属性**：架势类 mod（id 在 100000~150000 / 200000~250000 区间）
      全部属性不缩放；**换生灵 / 海妖系列的减伤**不缩放（固定为满级值）。
    """
    rec = get_by_third_id(third_id)
    if rec is None:
        return None
    max_level = rec.get("maxLevel") or 3
    lv = max(0, min(max_level, level if level is not None else max_level))
    stance = _is_stance(rec.get("id"))
    # 换生灵 / 海妖系列减伤为固定属性（dna-builder: 系列 special-case → lv = maxLevel）
    fixed_series = rec.get("series") in ("换生灵", "海妖")
    out: dict[str, float] = {}
    for key, value in rec.get("attrs", {}).items():
        prop_lv = max_level if (stance or (fixed_series and key == "减伤")) else lv
        if isinstance(value, list):
            idx = min(prop_lv + 1, len(value)) - 1
            out[key] = value[idx]
        elif prop_lv >= max_level:
            out[key] = value
        else:
            out[key] = value * (prop_lv + 1) / (max_level + 1)
    return out


# 面板率类键
_RATE_KEYS = ("技能威力", "技能范围", "技能耐久", "技能效益", "充盈威力", "昂扬", "背水")

# 面板四维键
_MAIN_KEYS = ("攻击", "生命", "防御", "护盾", "神智")

# 隐藏属性键（不进面板 11 项，但参与伤害/生存结算的属性，原样透传）
_HIDDEN_KEYS = (
    "增伤",
    "元素增伤",
    "物理增伤",
    "武器伤害",
    "技能伤害",
    "独立增伤",
    "属性穿透",
    "无视防御",
    "技能无视防御",
    "减伤",
    "追加伤害",
    "多重",
    "歧视",
    "物理",
    "触发倍率",
    "充盈转化",
    "攻击范围",
    "技能倍率乘数",
    "技能倍率加数",
    "技能倍率赋值",
    # 武器作用域属性：角色侧（角色加成 + 角色槽 MOD）会穿透到武器面板（见
    # local_weapon_attribute.collect_char_weapon_scope_bonus），角色面板的隐藏行已过滤。
    "暴击",
    "暴伤",
    "触发",
    "攻速",
)

# 武器作用域属性（dna-builder attrAllowCharToWeapon 白名单）：角色侧穿透到所有武器面板，
# 武器自身「加成」里的同类属性只作用于该武器自己的面板（不穿透）。
WEAPON_SCOPE_KEYS = ("暴击", "暴伤", "触发", "攻速")


def parse_attrs(attrs: dict[str, float] | None, element: str | None = None) -> ParsedAttrs:
    """把属性小数字典解析成面板分区结构（值全部转为百分比）

    Returns:
        {
          "main": {"攻击": 154.0, ...},        # 四维百分比
          "rate": {"昂扬": 33.0, ...},          # 率类/昂扬/背水百分比
          "elem_atk": {"水": 18.0, ...},        # 属性攻击（独立乘区）
          "flat": {},                           # 固定值（DOB 数据暂无此形态，保留兼容）
          "extra": {"技能伤害": -50.0, ...},    # 隐藏属性（增伤/减伤/技能伤害等）
          "raw": ["攻击+154%", ...],            # 原始展示文本
        }
    """
    out = ParsedAttrs(main={}, rate={}, elem_atk={}, flat={}, extra={}, raw=[])
    if not attrs:
        return out

    def _fmt(display: str, percent: float) -> str:
        sign = "+" if percent >= 0 else "-"
        return f"{display}{sign}{abs(percent):g}%"

    for key, fraction in attrs.items():
        if key == "属性攻击":
            elem = element or ""
            out["elem_atk"][elem] = out["elem_atk"].get(elem, 0.0) + fraction * 100
            out["raw"].append(_fmt(f"{elem}属性攻击", fraction * 100))
            continue
        display = key
        percent = fraction * 100
        if display in _MAIN_KEYS:
            out["main"][display] = out["main"].get(display, 0.0) + percent
            out["raw"].append(_fmt(display, percent))
        elif display in _RATE_KEYS:
            out["rate"][display] = out["rate"].get(display, 0.0) + percent
            out["raw"].append(_fmt(display, percent))
        elif display in _HIDDEN_KEYS:
            # 透传的隐藏属性：多来源相加（注意减伤的特殊聚合口径见 get_damage_reduce）
            out["extra"][display] = out["extra"].get(display, 0.0) + percent
            out["raw"].append(_fmt(display, percent))
    return out


def get_effects(
    third_id: int | str | None,
    level: int | None,
    quality: int | None = None,
) -> list[str]:
    """兼容旧 wiki_loader 接口：返回某 mod 某等级的效果文本列表"""
    rec = get_by_third_id(third_id)
    attrs = get_mod_attrs(third_id, level, quality)
    return parse_attrs(attrs, rec.get("element") if rec else None)["raw"]


# ── 角色加成（= wiki 技能解锁被动的聚合）─────────────────────


def get_char_bonus(char: CharEntry | None) -> ParsedAttrs:
    """取角色加成的面板分区结构（转换时已聚合为百分比）"""
    zones = char.get("bonus", {}) if char else {}
    return ParsedAttrs(
        main=dict(zones.get("main", {})),
        rate=dict(zones.get("rate", {})),
        elem_atk=dict(zones.get("elem_atk", {})),
        extra=dict(zones.get("extra", {})),
        flat={},
        raw=[],
    )


def get_damage_reduce(values: list[float]) -> float:
    """减伤的正确聚合口径：逐来源乘法合并（与 dna-builder getTotalBonusReduce 一致）

    ``[0.3, 0.5] → 1 - 0.7 × 0.5 = 0.65``；入参为小数（0.5 = 50%）。
    注意：``parse_attrs`` 的 extra 里减伤是**相加**的近似值，精确计算请用本函数。
    """
    bonus = 0.0
    for value in values:
        if value > 0:
            bonus = 1 - (1 - bonus) * (1 - value)
    return bonus


# ── 武器魔之楔 ───────────────────────────────────────────────

# 数据包属性键 → 武器面板显示名
_WEAPON_ATTR_MAP = {
    "攻击": "攻击",
    "物理": "物理",
    "暴击": "暴击率",
    "暴伤": "暴击伤害",
    "攻速": "攻击速度",
    "触发": "触发概率",
}


def get_weapon_mod_attrs(
    third_id: int | str | None,
    level: int | None,
    quality: int | None = None,
) -> dict[str, float] | None:
    """取武器魔之楔在指定等级的加成（百分比，键为武器面板显示名）

    例：{"攻击": 150.0, "暴击率": 100.0}
    """
    attrs = get_mod_attrs(third_id, level, quality)
    if attrs is None:
        return None
    out: dict[str, float] = {}
    for key, fraction in attrs.items():
        display = _WEAPON_ATTR_MAP.get(key)
        if display:
            out[display] = out.get(display, 0.0) + fraction * 100
    return out


# ── 条件生效（生效块，如 羽蛇·背水：D趋向>=4 时 背水+22%）──────

_CMP_OPS: dict[str, Callable[[float, float], bool]] = {
    "=": lambda a, b: a == b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "!=": lambda a, b: a != b,
}


def is_effect_effective(
    conditions: list[Condition],
    polarity_count: dict[str, int],
    id_count: dict[int, int],
    attrs_snapshot: dict[str, float] | None = None,
) -> bool:
    """判定条件生效块的条件是否满足（与 dna-builder LeveledMod.checkCondition 同规则）

    Args:
        conditions: 条件列表。三种形态：
                    ``["D趋向", ">=", 4]``   极性计数（取首字符查 polarity_count）；
                    ``["*id", "<=", 1]``     同 id 最多重复数比对 id_count；
                    ``["技能威力", ">=", 3.5]`` 属性门槛（对照面板属性快照，
                    需传入 attrs_snapshot，否则视为不满足）。
        polarity_count: 已装备魔之楔的极性计数
        id_count: 已装备魔之楔的 id 计数
        attrs_snapshot: 面板属性快照（键与条件属性名一致，如 技能威力=3.5 表示 350%）

    Returns:
        全部条件满足返回 True；无条件列表返回 False
    """
    if not conditions:
        return False
    max_id_count = float(max(id_count.values())) if id_count else 0.0
    for cond in conditions:
        # 条件有两种形态：三元素 ["D趋向", ">=", 4] 与两元素通配 ["单手剑", "*"]
        attr = str(cond[0])
        op = str(cond[1]) if len(cond) > 1 else "*"
        if op == "*":
            # 通配条件恒满足（dna-builder checkCondition: if (op === "*") return true）
            continue
        expected = cond[2] if len(cond) > 2 else 0.0
        if not isinstance(expected, (int, float)) or isinstance(expected, bool):
            return False
        if attr == "*id":
            actual = max_id_count
        elif attr.endswith("趋向"):
            actual = float(polarity_count.get(attr[:1], 0))
        else:
            if attrs_snapshot is None:
                return False
            actual = attrs_snapshot.get(attr, 0.0)
        cmp_fn = _CMP_OPS.get(op)
        if cmp_fn is None or not cmp_fn(actual, float(expected)):
            return False
    return True


def get_effect_attrs(
    rec: ModRecord,
    level: int | None,
    base_values: dict[str, float] | None = None,
) -> dict[str, float]:
    """取某魔之楔条件生效块在指定等级下的属性（小数）

    - 标量：按等级线性缩放 ``满级值 / (maxLevel + 1) × (等级 + 1)``；
    - **数组**：按 dna-builder applyCondition 的表达式规则结算——
      ``最终值 = min(条件属性值 × v1, v2)``，条件属性值取 ``条件[0][0]``
      在 ``base_values`` 中的取值。调用方须把四类来源都塞进 ``base_values``：
      极性计数（``X趋向``）、``*id`` 重复数、面板属性快照（``_condition_snapshot``）、
      武器类别计数（``collect_weapon_categories``，如 锋芒 ``[["单手剑","*"]]``）。
      数组长度不足 2 时无法套用表达式，跳过（当前数据包无此形态）。
    """
    effect = rec.get("effect")
    attrs = effect.get("attrs", {}) if effect else {}
    if not attrs:
        return {}
    max_level = rec.get("maxLevel") or 3
    lv = max(0, min(max_level, level if level is not None else max_level))
    scale = (lv + 1) / (max_level + 1)
    conditions = effect.get("conditions", []) if effect else []
    cond_attr = str(conditions[0][0]) if conditions else ""
    values = base_values if base_values is not None else {}
    out: dict[str, float] = {}
    for key, value in attrs.items():
        if isinstance(value, list):
            # 两个系数都要先按等级缩放（dna-builder LeveledMod.updateProperties），再套 min 表达式
            if len(value) >= 2:
                base = values.get(cond_attr, 0.0)
                v1, v2 = value[0] * scale, value[1] * scale
                out[key] = min(base * v1, v2)
            # 长度不足 2 的数组无法套用表达式，跳过
            continue
        out[key] = value * scale
    return out


def is_elem_atk_effective(mod_element: str | None, char_element: str | None) -> bool:
    """判断该 mod 的属性攻击对某属性角色是否生效

    规则：mod 未限定属性（element 为空/无）→ 按角色自身属性生效；
          限定属性时仅相同属性生效。
    """
    if not mod_element or mod_element == "无":
        return True
    if char_element is None:
        return False
    return mod_element == char_element


# ── 技能与本地伤害计算 ───────────────────────────────────────

# 技能等级上限（与 dna-builder LeveledSkill.等级 一致）
SKILL_MAX_LEVEL = 12


def get_char_skills(char_id: int | str | None) -> list[SkillEntry]:
    """取角色技能（紧凑字段表，供本地伤害计算）"""
    entry = get_char(char_id)
    return list(entry.get("skills", [])) if entry else []


def get_weapon(weapon_id: int | str | None) -> WeaponRecord | None:
    """按武器 id 取武器记录（普通武器，不含同律武器）"""
    if weapon_id is None:
        return None
    weapons = _data.get("weapons")
    by_id = weapons.get("byId") if weapons else None
    return by_id.get(str(weapon_id)) if by_id else None


def get_con_weapon(char_id: int | str | None, weapon_id: int | str | None) -> WeaponRecord | None:
    """按角色与同律武器 id 取同律武器记录"""
    entry = get_char(char_id)
    if entry is None:
        return None
    for weapon in entry.get("conWeapons", []):
        if weapon.get("id") is not None and str(weapon.get("id")) == str(weapon_id):
            return weapon
    return None


# ── 武器精通倍率 ─────────────────────────────────────────────

# 命中武器精通时的攻击倍率。dna-builder 区分「同律 1.4 / 普通 1.2」，但游戏实测两把同律
# 都是 ×1.2（萨麦尔 225.94 = 188.28×1.2、伊卡洛斯 75.31 = 62.76×1.2），故统一取 1.2。
MASTERY_RATIO_HIT = 1.2


def get_char_mastery(char_id: int | str | None) -> tuple[list[str], list[str]]:
    """取角色的（精通, 额外精通）武器类别列表"""
    entry = get_char(char_id)
    if entry is None:
        return [], []
    return list(entry.get("精通", [])), list(entry.get("额外精通", []))


# 武器加成的精炼缩放基数（dna-builder LeveledWeapon：值 / 5 × (精炼等级 + 5)）
_WEAPON_REFINE_BASE = 5


def weapon_forge_bonus(
    weapon: WeaponRecord | None,
    skill_level: int | None,
) -> dict[str, float]:
    """取武器自身「加成」按精炼等级缩放后的小数字典

    与 dna-builder ``LeveledWeapon.updateProperties`` 同口径：
    ``加成值 / 5 × (精炼等级 + 5)``（精炼 0 → 原值，精炼 5 → 2×原值）；
    带熔炉的武器取原值（不缩放）。精炼等级缺省按满精炼 5。

    ⚠️ 数据包里**没有**单独的「精炼分档」字段，但 ``熔炼`` 文案的占位符数组
    就是真实分档，例如 囚鸟的刺羽::

        ["昂扬+#1。…", ["15.0%", "18.0%", "21.0%", "24.0%", "27.0%", "30.0%"], …]

    2026-10-08 逐把核对 52 条：**48 条与公式逐档完全一致**，另 4 条是
    「攻击范围 / 子弹爆炸范围」这类非百分比属性的单位差异（比例关系仍成立）。
    所以公式口径可用，无需解析文案。
    """
    if weapon is None:
        return {}
    bonus = weapon.get("加成", {})
    if not bonus:
        return {}
    if weapon.get("hasForge"):
        return dict(bonus)
    level = _WEAPON_REFINE_BASE if skill_level is None else max(0, min(_WEAPON_REFINE_BASE, int(skill_level)))
    scale = (level + _WEAPON_REFINE_BASE) / _WEAPON_REFINE_BASE
    return {key: value * scale for key, value in bonus.items()}


def weapon_types(weapon: WeaponRecord | None) -> list[str]:
    """取武器类型数组（如 ``["同律", "远程", "突击枪"]``）"""
    if weapon is None:
        return []
    return list(weapon.get("类型", []))


def weapon_category(weapon: WeaponRecord | None) -> str | None:
    """武器类别（精通判定 / 条件词条的按类别计数用）

    与 dna-builder 同口径 —— 按位置取，不取末位：
    同律 ``["同律", "远程", "突击枪"]`` → ``类型[2]`` = 突击枪；
    普通 ``["近战", "单手剑"]`` → ``类型[1]`` = 单手剑。

    ⚠️ 弓类普通武器是 3 元素 ``["远程", "弓", "弓（长弓）"]``，角色「精通」列表
    与条件词条（如 锋芒弓 ``[["弓", "*"]]``）用的都是大类 ``弓``（即 ``类型[1]``）。
    取末位会得到 ``弓（长弓）`` → 精通判定为未命中（攻击少 ×1.2）、条件计数恒为 0。
    """
    types = weapon_types(weapon)
    if not types:
        return None
    # dna-builder：LeveledSkillWeapon 类别在 类型[2]；LeveledWeapon 在 类型[1]
    index = 2 if types[0] == "同律" else 1
    if index < len(types):
        return types[index]
    return types[-1]


def is_skill_weapon(weapon: WeaponRecord | None) -> bool:
    """是否同律武器（绑定角色，必然命中精通）"""
    types = weapon_types(weapon)
    return bool(types) and types[0] == "同律"


def is_weapon_mastered(char_id: int | str | None, weapon: WeaponRecord | None) -> bool:
    """角色是否精通该武器类别（dna-builder ``CharBuild.isWeaponCategoryMastered``）

    同律武器绑定角色，类别取 ``类型[2]``；普通武器取 ``类型[1]``（见 ``weapon_category``）。
    「全部能力类型 / 全部类型」视为精通一切。
    """
    if weapon is None:
        return False
    category = weapon_category(weapon)
    if not category:
        return False
    mastered, _ = get_char_mastery(char_id)
    return category in mastered or "全部能力类型" in mastered or "全部类型" in mastered


def weapon_mastery_ratio(
    char_id: int | str | None,
    weapon: WeaponRecord | None,
    extra_mastery: str | None = None,
) -> float:
    """武器攻击的精通倍率：命中精通 1.2 / 未命中 1.0

    同律武器绑定角色，必然命中；普通武器按角色「精通」列表判定
    （与 dna-builder CharBuild.isWeaponCategoryMastered 同规则）。
    """
    if weapon is None:
        return 1.0
    if is_skill_weapon(weapon):
        return MASTERY_RATIO_HIT
    category = weapon_category(weapon)
    if not category:
        return 1.0
    mastery, _ = get_char_mastery(char_id)
    hit = category in mastery or "全部类型" in mastery or (bool(extra_mastery) and category == extra_mastery)
    return MASTERY_RATIO_HIT if hit else 1.0


def resolve_skill_fields(
    skill: SkillEntry,
    level: int,
    attrs: dict[str, float] | None = None,
) -> list[ResolvedSkillField]:
    """按技能等级与面板属性缩放技能字段（移植 dna-builder LeveledSkill.getFieldsWithAttr）

    Args:
        skill: 数据包技能记录（含 字段）
        level: 技能等级（1~12，逐档数组按下标取值）
        attrs: 面板属性（键与 影响 一致：技能威力/技能范围/技能耐久/技能效益 为
               **1 起始乘数**（如 2.21 = +121%），技能倍率乘数/加数 为小数）

    Returns:
        [{名称, 影响, 值, 值2, 格式, 基础, 伤害类型}]（值已缩放）
    """
    source = attrs if attrs is not None else {}
    # 四大乘区（1 起始），缺省 1；效益/范围/耐久上限与 dna-builder calculateAttributes 一致
    tt = {
        "技能威力": source.get("技能威力", 1.0),
        "技能范围": min(source.get("技能范围", 1.0), 2.8),
        "技能耐久": min(source.get("技能耐久", 1.0), 4.0),
        "技能效益": min(source.get("技能效益", 1.0), 1.75),
    }
    mult = source.get("技能倍率乘数", 0.0)
    add = source.get("技能倍率加数", 0.0)
    index = max(0, min(SKILL_MAX_LEVEL, level)) - 1

    out: list[ResolvedSkillField] = []
    for field in skill.get("字段", []):
        raw = field.get("值")
        value = raw[index] if isinstance(raw, list) else raw
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        raw2 = field.get("值2")
        value2 = raw2[index] if isinstance(raw2, list) else raw2
        name = field.get("名称", "")
        influence = field.get("影响")
        if influence:
            val = float(value)
            val2 = float(value2) if isinstance(value2, (int, float)) and not isinstance(value2, bool) else 0.0
            if "伤害" in name:
                val = val * (1 + mult) + add
            prop_set = set(influence.split(","))
            if "技能范围" in prop_set:
                val *= tt["技能范围"]
            if "技能威力" in prop_set:
                val *= tt["技能威力"]
                val2 *= tt["技能威力"]
            if "技能耐久" in prop_set:
                # 持续型消耗随耐久提升反而降低（持续时间变长），其余按耐久放大
                if "每秒神智消耗" in name:
                    val /= tt["技能耐久"]
                else:
                    val *= tt["技能耐久"]
            if "技能效益" in prop_set:
                if "技能耐久" in prop_set:
                    # 耐久和效益共同影响下仍有 25% 下限（对应 175% 效益上限的换算）
                    val = float(value) * max(0.25, (2 - tt["技能效益"]) / tt["技能耐久"])
                else:
                    val = float(value) * (2 - tt["技能效益"])
            if "神智消耗" in name:
                val = math.ceil(val)
            value, value2 = val, val2
        out.append(
            ResolvedSkillField(
                名称=name,
                值=float(value),
                值2=float(value2) if isinstance(value2, (int, float)) and not isinstance(value2, bool) else None,
                影响=influence,
                格式=field.get("格式"),
                基础=field.get("基础"),
                伤害类型=field.get("伤害类型"),
            )
        )
    return out


__all__ = [
    "DATA_FILE",
    "ELEMENT_NAMES",
    "QUALITY_TO_KEY",
    "built_at",
    "char_count",
    "get_by_third_id",
    "get_char",
    "get_char_by_name",
    "get_char_bonus",
    "get_char_skills",
    "get_con_weapon",
    "get_damage_reduce",
    "get_effects",
    "get_effect_attrs",
    "get_mod_attrs",
    "get_weapon_mod_attrs",
    "get_weapon",
    "is_effect_effective",
    "is_elem_atk_effective",
    "is_loaded",
    "level_multiplier",
    "mod_count",
    "parse_attrs",
    "reload",
    "resolve_skill_fields",
    "scaled_base",
    "version",
    "weapon_count",
    "MASTERY_RATIO_HIT",
    "get_char_mastery",
    "is_skill_weapon",
    "is_weapon_mastered",
    "weapon_category",
    "weapon_mastery_ratio",
    "weapon_types",
]
