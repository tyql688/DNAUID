"""DOB 数据包的结构定义 —— 供 ``dob_pack``（生成）与 ``dob_loader``（查询）共用

键名直接沿用 dna-builder 数据包的原始键（含中文），因此这里的 TypedDict 字段名也是中文。
字段类型按 v1.6.208.6 实际数据核对（586 mod / 71 武器 / 7 同律武器）。

两层结构：

1. **原始包**（游戏 msgpack 解出）：``RawValue`` / ``RawRecord`` —— 只有那几种取值形态，
   消费方逐处 ``isinstance`` 收窄，不引入 ``Any``。
2. **转换产物**（``dob_data.json``）：``DobData`` 及其下的 TypedDict。键可能缺省，
   故一律 ``total=False``，缺失由消费方显式给默认值，不用 ``(record or {}).get(...)`` 掩盖。
"""

from __future__ import annotations

from typing import TypeAlias, TypedDict

# ── 原始数据包（游戏 msgpack）取值形态 ───────────────────────
# 递归联合：标量 / 数组 / 嵌套对象。pyright 对字符串形式的别名惰性求值。
RawValue: TypeAlias = "str | int | float | bool | None | list[RawValue] | dict[str, RawValue]"
RawRecord: TypeAlias = "dict[str, RawValue]"

# 属性值形态：标量（按等级线性缩放）或逐档数组（按等级下标取值）。
# 保留 int 成员：产物 JSON 里 1 与 1.0 是两种文本，收窄成 float 会改到产物。
AttrValue: TypeAlias = "int | float | list[int | float]"

# 条件生效块的一条条件：["D趋向", ">=", 4] / ["*id", "<=", 1] / ["单手剑", "*"]
ConditionValue: TypeAlias = "str | int | float"
Condition: TypeAlias = "list[ConditionValue]"


class MainAttrs(TypedDict):
    """四维基础值（``baseLv1`` 为 1 级白值，``base`` 为满级值）

    ``_convert_chars`` 恒定写全 5 项（缺失即视为数据包异常，转换阶段就拦下），
    故这里声明为必选，消费方不必逐层补默认值。
    """

    攻击: float
    生命: float
    护盾: float
    防御: float
    神智: float


class BonusZones(TypedDict):
    """数据包里 ``char.加成`` 的原始分区（值均为百分比）—— 四个分区恒定存在"""

    main: dict[str, float]
    rate: dict[str, float]
    elem_atk: dict[str, float]
    extra: dict[str, float]


class ParsedAttrs(TypedDict):
    """``parse_attrs`` 的输出 —— 六个键恒定存在，消费方直接下标取用"""

    main: dict[str, float]
    rate: dict[str, float]
    elem_atk: dict[str, float]
    flat: dict[str, float]
    extra: dict[str, float]
    raw: list[str]


class SkillField(TypedDict, total=False):
    """技能字段；``值`` / ``值2`` 可以是标量，也可以是按技能等级的数组"""

    名称: str
    影响: str | None
    值: AttrValue | None
    值2: AttrValue | None
    格式: str | None
    基础: str | None
    伤害类型: str | None


class ResolvedSkillField(TypedDict):
    """``resolve_skill_fields`` 的输出 —— 值已按等级与面板属性缩放"""

    名称: str
    值: float
    值2: float | None
    影响: str | None
    格式: str | None
    基础: str | None
    伤害类型: str | None


class SkillEntry(TypedDict, total=False):
    """角色技能（含逐级字段表）"""

    名称: str
    类型: str | None
    字段: list[SkillField]


class ModEffect(TypedDict, total=False):
    """条件生效块"""

    conditions: list[Condition]
    attrs: dict[str, AttrValue]


class ModRecord(TypedDict, total=False):
    """魔之楔记录（``attrs`` 为满级值，小数）"""

    id: int | None
    name: str | None
    series: str | None
    quality: int
    qualityName: str
    element: str | None
    modType: str | None
    polarity: str | None
    tolerance: float | None
    limited: int | str | None
    maxLevel: int
    attrs: dict[str, AttrValue]
    effect: ModEffect | None


class WeaponRecord(TypedDict, total=False):
    """武器记录 —— ``weapons.byId``（普通）与 ``char.conWeapons``（同律）共用

    普通武器写 ``name``，同律武器写 ``名称``；同律武器没有 ``加成`` / ``hasForge``，
    且 攻击 / 暴击 / 暴伤 / 触发 / 攻速 可能缺省（继承型同律武器靠 ``inherit``
    在被装备的那把武器上取值）。
    """

    id: int | None
    name: str | None
    名称: str | None
    类型: list[str]
    伤害类型: str | None
    攻击: float | None
    暴击: float | None
    暴伤: float | None
    触发: float | None
    攻速: float | None
    加成: dict[str, float]
    hasForge: bool
    inherit: str | None
    atk: str | None
    视为: str | None
    filter: str | None
    skill: list[int]


class PassiveEntry(TypedDict):
    """技能解锁被动的一条（``char.加成`` 的一项，按数据包写入顺序）

    数据包只给两档合计值；``skill`` / ``index`` 指明它挂在哪个技能下，
    查询侧据此按技能 4 级 / 8 级还原档位（见 ``local_attribute._passive_tier_ratio``）。
    """

    skill: str | None
    index: int
    zone: str
    key: str
    value: float


class CharEntry(TypedDict, total=False):
    """角色面板条目"""

    id: int | None
    name: str | None
    element: str | None
    精通: list[str]
    额外精通: list[str]
    baseLv1: MainAttrs
    base: MainAttrs
    bonus: BonusZones
    passives: list[PassiveEntry]
    conWeapons: list[WeaponRecord]
    skills: list[SkillEntry]


class ConvertedChars(TypedDict):
    """``_convert_chars`` 的输出"""

    byCharId: dict[str, CharEntry]
    byName: dict[str, str]


class ConvertedMods(TypedDict):
    """``_convert_mods`` 的输出"""

    byId: dict[str, ModRecord]


class ConvertedWeapons(TypedDict):
    """``_convert_weapons`` 的输出"""

    byId: dict[str, WeaponRecord]


class DobMeta(TypedDict, total=False):
    """数据包元信息"""

    source: str
    packVersion: str | None
    packBuiltAt: str | None
    chars: int
    mods: int
    weapons: int
    generated: str


class DobData(TypedDict, total=False):
    """``dob_data.json`` 顶层结构"""

    _meta: DobMeta
    byCharId: dict[str, CharEntry]
    byName: dict[str, str]
    mods: dict[str, dict[str, ModRecord]]
    weapons: dict[str, dict[str, WeaponRecord]]
    commonLevelUp: list[float]


__all__ = [
    "AttrValue",
    "BonusZones",
    "CharEntry",
    "Condition",
    "ConditionValue",
    "ConvertedChars",
    "ConvertedMods",
    "ConvertedWeapons",
    "DobData",
    "DobMeta",
    "MainAttrs",
    "ModEffect",
    "ModRecord",
    "ParsedAttrs",
    "PassiveEntry",
    "RawRecord",
    "RawValue",
    "ResolvedSkillField",
    "SkillEntry",
    "SkillField",
    "WeaponRecord",
]
