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
"""

from __future__ import annotations

import json
from typing import Any

try:
    from gsuid_core.logger import logger
except ImportError:  # pragma: no cover - 允许脱离 gsuid_core 单测
    import logging

    logger = logging.getLogger("dna_dob_loader")


from .dob_pack import DATA_PATH

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

_data: dict[str, Any] = {}


def _load() -> None:
    global _data
    try:
        _data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        logger.warning(f"[DNA DOB] 数据包数据加载失败: {error}")
        _data = {}
        return
    meta = _data.get("_meta") or {}
    logger.info(
        f"[DNA DOB] 数据已加载: v{meta.get('packVersion')}"
        f"（角色 {meta.get('chars')} / 魔之楔 {meta.get('mods')} / 武器 {meta.get('weapons')}）"
    )


def reload() -> None:
    _load()


_load()


def is_loaded() -> bool:
    return bool(_data.get("mods", {}).get("byId"))


def version() -> str | None:
    return (_data.get("_meta") or {}).get("packVersion")


def built_at() -> str | None:
    return (_data.get("_meta") or {}).get("packBuiltAt")


def mod_count() -> int:
    return len((_data.get("mods") or {}).get("byId") or {})


def char_count() -> int:
    return len(_data.get("byCharId") or {})


def weapon_count() -> int:
    return len((_data.get("weapons") or {}).get("byId") or {})


# ── 角色查询 ─────────────────────────────────────────────────


def get_char(char_id: int | str | None) -> dict[str, Any] | None:
    """按游戏 charId 取角色面板数据条目"""
    if char_id is None:
        return None
    return (_data.get("byCharId") or {}).get(str(char_id))


def get_char_by_name(name: str | None) -> dict[str, Any] | None:
    """按角色名取数据条目（id 查不到时兜底）"""
    if not name:
        return None
    cid = (_data.get("byName") or {}).get(name)
    return get_char(cid) if cid else None


def level_multiplier(level: int | None) -> float | None:
    """角色等级 → 成长倍率（1~80）；等级无效返回 None"""
    if level is None:
        return None
    table = _data.get("commonLevelUp") or []
    if not table or level < 1 or level > len(table):
        return None
    return table[level - 1]


def scaled_base(char: dict[str, Any] | None, level: int | None) -> dict[str, float]:
    """角色基础值按实际等级缩放（与 dna-builder LeveledChar 同口径）

    - 攻击：round(1 级白值 × 倍率, 2)；生命/护盾：round(白值 × 倍率)（取整）；
    - 防御 / 最大神志不随等级成长，原样返回；
    - 等级缺失或超出 1~80 时回退 80 级值（``base`` 字段）。
    """
    if not char:
        return {}
    base80 = char.get("base") or {}
    multiplier = level_multiplier(level)
    lv1 = char.get("baseLv1")
    if multiplier is None or not lv1:
        return dict(base80)
    return {
        "攻击": round(lv1.get("攻击", 0) * multiplier + 1e-9, 2),
        "生命": round(lv1.get("生命", 0) * multiplier),
        "护盾": round(lv1.get("护盾", 0) * multiplier),
        "防御": lv1.get("防御", base80.get("防御", 0)),
        "最大神志": lv1.get("最大神志", base80.get("最大神志", 0)),
    }


# ── 魔之楔查询 ───────────────────────────────────────────────


def get_by_third_id(third_id: int | str | None) -> dict[str, Any] | None:
    """按官方接口 modes[].id（= 数据包 mod id）取记录"""
    if third_id is None:
        return None
    return (_data.get("mods") or {}).get("byId", {}).get(str(third_id))


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
    if not rec:
        return None
    max_level = rec.get("maxLevel") or 3
    lv = max(0, min(max_level, level if level is not None else max_level))
    stance = _is_stance(rec.get("id"))
    # 换生灵 / 海妖系列减伤为固定属性（dna-builder: 系列 special-case → lv = maxLevel）
    series = rec.get("series")
    fixed_series = series in ("换生灵", "海妖")
    out: dict[str, float] = {}
    for key, value in (rec.get("attrs") or {}).items():
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
_MAIN_KEYS = ("攻击", "生命", "防御", "护盾", "最大神志")

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
)


def parse_attrs(attrs: dict[str, float] | None, element: str | None = None) -> dict[str, Any]:
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
    out: dict[str, Any] = {"main": {}, "rate": {}, "elem_atk": {}, "flat": {}, "extra": {}, "raw": []}
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
        if key == "神智":
            display = "最大神志"
        else:
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
    return parse_attrs(get_mod_attrs(third_id, level, quality), (get_by_third_id(third_id) or {}).get("element"))["raw"]


# ── 角色加成（= wiki 技能解锁被动的聚合）─────────────────────


def get_char_bonus(char: dict[str, Any] | None) -> dict[str, Any]:
    """取角色加成的面板分区结构（转换时已聚合为百分比）"""
    zones = (char or {}).get("bonus") or {}
    return {
        "main": dict(zones.get("main") or {}),
        "rate": dict(zones.get("rate") or {}),
        "elem_atk": dict(zones.get("elem_atk") or {}),
        "extra": dict(zones.get("extra") or {}),
    }


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

_CMP_OPS = {
    "=": lambda a, b: a == b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "!=": lambda a, b: a != b,
}


def is_effect_effective(
    conditions: list[list],
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
    max_id_count = max(id_count.values()) if id_count else 0
    for cond in conditions:
        attr, op, value = cond[0], cond[1], cond[2]
        if attr == "*id":
            actual = max_id_count
        elif str(attr).endswith("趋向"):
            actual = polarity_count.get(str(attr)[:1], 0)
        else:
            if attrs_snapshot is None:
                return False
            actual = attrs_snapshot.get(attr, 0.0)
        if op == "*":
            continue
        cmp_fn = _CMP_OPS.get(op)
        if cmp_fn is None or not cmp_fn(actual, value):
            return False
    return True


def get_effect_attrs(
    rec: dict[str, Any],
    level: int | None,
    base_values: dict[str, float] | None = None,
) -> dict[str, float]:
    """取某魔之楔条件生效块在指定等级下的属性（小数）

    - 标量：按等级线性缩放 ``满级值 / (maxLevel + 1) × (等级 + 1)``；
    - **数组**：按 dna-builder applyCondition 的表达式规则结算——
      ``最终值 = min(条件属性值 × v1, v2)``，条件属性值取 ``条件[0][0]``
      在 ``base_values`` 中的取值（极性计数 / *id 重复数 / 属性快照，
      武器类别计数在角色面板无上下文，按 0 处理 → 结果为 0，即不生效）。
    """
    effect = rec.get("effect") or {}
    attrs = effect.get("attrs") or {}
    if not attrs:
        return {}
    max_level = rec.get("maxLevel") or 3
    lv = max(0, min(max_level, level if level is not None else max_level))
    scale = (lv + 1) / (max_level + 1)
    conditions = (effect.get("conditions") or [])
    cond_attr = str(conditions[0][0]) if conditions else ""
    base_values = base_values or {}
    out: dict[str, float] = {}
    for key, value in attrs.items():
        if isinstance(value, list):
            if len(value) >= 2:
                base = base_values.get(cond_attr, 0.0)
                v1, v2 = value[0], value[1]
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


def get_char_skills(char_id: int | str | None) -> list[dict[str, Any]]:
    """取角色技能（紧凑字段表，供本地伤害计算）"""
    entry = get_char(char_id)
    return list((entry or {}).get("skills") or [])


def get_weapon(weapon_id: int | str | None) -> dict[str, Any] | None:
    """按武器 id 取武器记录（普通武器，不含同律武器）"""
    if weapon_id is None:
        return None
    return (_data.get("weapons") or {}).get("byId", {}).get(str(weapon_id))


def get_con_weapon(char_id: int | str | None, weapon_id: int | str | None) -> dict[str, Any] | None:
    """按角色与同律武器 id 取同律武器记录"""
    entry = get_char(char_id)
    for weapon in (entry or {}).get("conWeapons") or []:
        if weapon.get("id") is not None and str(weapon.get("id")) == str(weapon_id):
            return weapon
    return None


def resolve_skill_fields(
    skill: dict[str, Any],
    level: int,
    attrs: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """按技能等级与面板属性缩放技能字段（移植 dna-builder LeveledSkill.getFieldsWithAttr）

    Args:
        skill: 数据包技能记录（含 字段）
        level: 技能等级（1~12，逐档数组按下标取值）
        attrs: 面板属性（键与 影响 一致：技能威力/技能范围/技能耐久/技能效益 为
               **1 起始乘数**（如 2.21 = +121%），技能倍率乘数/加数 为小数）

    Returns:
        [{名称, 影响, 值, 值2, 格式, 基础, 伤害类型}]（值已缩放）
    """
    attrs = attrs or {}
    # 四大乘区（1 起始），缺省 1；效益/范围/耐久上限与 dna-builder calculateAttributes 一致
    tt = {
        "技能威力": attrs.get("技能威力", 1),
        "技能范围": min(attrs.get("技能范围", 1), 2.8),
        "技能耐久": min(attrs.get("技能耐久", 1), 4),
        "技能效益": min(attrs.get("技能效益", 1), 1.75),
    }
    mult = attrs.get("技能倍率乘数", 0)
    add = attrs.get("技能倍率加数", 0)

    out: list[dict[str, Any]] = []
    for field in skill.get("字段") or []:
        raw = field.get("值")
        if isinstance(raw, list):
            value = raw[max(0, min(SKILL_MAX_LEVEL, level)) - 1]
        else:
            value = raw
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        value2 = field.get("值2")
        if isinstance(value2, list):
            value2 = value2[max(0, min(SKILL_MAX_LEVEL, level)) - 1]
        name = field.get("名称") or ""
        influence = field.get("影响")
        if influence:
            val = value
            val2 = value2 if isinstance(value2, (int, float)) else 0
            if "伤害" in name:
                val = val * (1 + mult) + add
            prop_set = set(str(influence).split(","))
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
                    val = value * max(0.25, (2 - tt["技能效益"]) / tt["技能耐久"])
                else:
                    val = value * (2 - tt["技能效益"])
            if "神智消耗" in name:
                import math

                val = math.ceil(val)
            value, value2 = val, val2
        out.append(
            {
                "名称": name,
                "影响": influence,
                "值": value,
                "值2": value2 if isinstance(value2, (int, float)) else None,
                "格式": field.get("格式"),
                "基础": field.get("基础"),
                "伤害类型": field.get("伤害类型"),
            }
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
]
