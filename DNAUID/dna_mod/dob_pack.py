"""DOB（dna-builder）数据包的下载、解包与转换

数据来源
--------
dna-builder 的公开数据包（zip + msgpack，不加密）：

    <CDN>/data-pack/versions.json          版本列表（第一条为最新）
    <CDN>/data-pack/<version>.zip          整包

zip 内：
    manifest.json                       打包信息（version / builtAt）
    modules/char.data.msgpack           角色全量数据（数组，键为中文）
    modules/mod.data.msgpack            魔之楔全量数据
    modules/weapon.data.msgpack         武器全量数据

转换口径（输出 dna_mod/data/dob_data.json）
------------------------------------------
1. **角色基础值**：数据包里的 基础攻击/基础生命/基础护盾 是 **1 级白值**，按
   等级倍率表 ``COMMON_LEVEL_UP``（1~80 级，与 dna-builder CommonLevelUp.ts 同源）
   在**查询侧**缩放到角色实际等级（80 级 = ×12.5522）：
       攻击 = round(基础攻击 × 倍率, 2)
       生命/护盾 = round(基础生命 × 倍率)   （取整，与 dna-builder 一致）
   基础防御 / 基础神智 不随等级成长，原样保留。
   转换产物同时存 ``baseLv1``（1 级白值）与 ``base``（80 级，等级未知时的兜底口径，
   与官方 H5 / wiki 阶段表满级行一致）。
   （验证：芙罗拉 基础攻击 26 × 12.5522 = 326.36，与 wiki 满级行完全一致；
   莉兹贝尔 80 级 攻击 301.25 / 生命 1130，与真实游戏截图一致。）

2. **角色加成（char.加成）**：即 wiki 技能页「伤害/增益」解锁被动的**聚合总值**
   （验证：芙罗拉 加成.昂扬 0.15 = wiki 两条被动 6% + 9%）。转换成面板加成条目，
   数值 ×100 变百分比，无解锁条件（视为全部计入，与面板模块既有约定一致）。

3. **魔之楔属性**：数据包里每个 id 一条记录（品质/档位即 id 本身），
   数值字段（攻击/生命/昂扬/属性攻击/暴击…）是 **满级值（小数）**。
   逐级缩放公式（与 dna-builder LeveledMod 一致，转换时不缩放，查询时算）：
       当前值 = 满级值 / (maxLevel + 1) × (等级 + 1)
   品质 → 等级上限：金 10 / 紫 5 / 蓝 5 / 绿 3 / 白 3。
   （验证：金 全盛·昂扬 攻击 1.54 → +10 时 154%，与 wiki 文本一致。）

4. **武器**：保留 攻击/暴击/暴伤/触发/攻速 白值（1 级口径，与官方
   getWeaponDetail.attribute 同口径）、类型（精通判定用）与 伤害类型（切割/贯穿/震荡/灾厄）；
   角色保留 精通 / 额外精通 —— 武器攻击的「精通倍率」判定依据。

更新流程
--------
``sync(force)``：拉 versions.json → 与本地版本比对 → 下载整包 → 内存解包转换
→ 原子写 dob_data.json。手动与自动更新共用一个 ``asyncio.Lock`` 串行执行；
临时文件按进程与时间戳命名，避免两次更新争用同一 ``.tmp`` 导致替换失败。
旧 wiki 抓取器（dnabbs wiki / 官方 config 双源）已废弃，全部数据改由本模块提供。

数据文件位于 ``data/DNAUID/resource/dob/dob_data.json``（路径定义统一在
``utils/resource/RESOURCE_PATH.py``），旧位置（dna_mod/data/）的文件在读取时自动迁移。
"""

from __future__ import annotations

import io
import os
import json
import time
import shutil
import asyncio
import zipfile
from pathlib import Path
from datetime import datetime

import httpx
import msgpack

from gsuid_core.logger import logger

from .dob_types import (
    DobData,
    DobMeta,
    RawValue,
    AttrValue,
    CharEntry,
    Condition,
    ModEffect,
    ModRecord,
    RawRecord,
    BonusZones,
    SkillEntry,
    SkillField,
    WeaponRecord,
    ConvertedMods,
    ConvertedChars,
    ConvertedWeapons,
)

# 数据文件统一放 data/DNAUID/resource/dob/（路径定义在 utils/resource/RESOURCE_PATH.py，
# 下载、读取和状态查询共用）；旧位置 dna_mod/data/dob_data.json 在读取时自动迁移。
from ..utils.resource.RESOURCE_PATH import DOB_DATA_PATH as DATA_PATH

_LEGACY_DATA_PATH = Path(__file__).parent / "data" / "dob_data.json"


class DobPackError(RuntimeError):
    """数据包拉取 / 转换失败（网络、CDN、包格式、写盘）

    底层异常在 ``sync()`` 的边界处一次性收敛成这一种，上层只需 catch 它。
    """


# 数据包 CDN 双源（与 dna-builder 客户端一致：OSS 主源 + R2 备源）
CDN_BASES = (
    "https://cdn.dna-builder.cn/data-pack",
    "https://cdn.dobapp.cc/data-pack",
)

# 角色等级倍率表（1~80 级），与 dna-builder src/data/leveled/CommonLevelUp.ts 同源
COMMON_LEVEL_UP = [
    1,
    1.0422,
    1.086,
    1.1305,
    1.1774,
    1.3988,
    1.4474,
    1.5012,
    1.5589,
    1.6157,
    1.8331,
    1.8921,
    1.9527,
    2.0162,
    2.0813,
    2.3128,
    2.3809,
    2.4505,
    2.5186,
    2.5897,
    2.8339,
    2.9053,
    2.9795,
    3.0538,
    3.1288,
    3.3098,
    3.5538,
    3.6327,
    3.7117,
    3.7921,
    4.1028,
    4.1842,
    4.2765,
    4.3725,
    4.4705,
    4.8047,
    4.9053,
    5.0059,
    5.1021,
    5.1933,
    5.5294,
    5.621,
    5.7141,
    5.8079,
    5.9032,
    6.2508,
    6.348,
    6.4451,
    6.5437,
    6.6416,
    6.8191,
    7.1079,
    7.2107,
    7.3127,
    7.4155,
    7.7876,
    7.8938,
    7.9999,
    8.1061,
    8.5685,
    8.6863,
    8.803,
    8.9214,
    9.0424,
    9.7101,
    9.7488,
    9.8684,
    9.9916,
    10.1107,
    10.2122,
    11.236,
    11.3504,
    11.459,
    11.5667,
    11.9809,
    12.093,
    12.2051,
    12.3222,
    12.4372,
    12.5522,
]

# 满级（80 级）倍率
MAX_LEVEL_MULTIPLIER = COMMON_LEVEL_UP[-1]

# 品质中文 → 数值（与官方接口 quality 1~5 对齐）
QUALITY_TO_INT = {"白": 1, "绿": 2, "蓝": 3, "紫": 4, "金": 5}

# 品质 → 魔之楔等级上限（与 dna-builder LeveledMod.modQualityMaxLevel 一致）
QUALITY_MAX_LEVEL = {1: 3, 2: 3, 3: 5, 4: 5, 5: 10}

# 角色数据里不参与面板转换的字段（数值字段之外的全部排除）
_CHAR_SKIP_KEYS = frozenset(
    {
        "id",
        "icon",
        "名称",
        "版本",
        "别名",
        "阵营",
        "势力",
        "属性",
        "出生地",
        "生日",
        "中文CV",
        "日文CV",
        "英文CV",
        "韩文CV",
        "突破",
        "精通",
        "额外精通",
        "标签",
        "特质",
        "基础攻击",
        "基础生命",
        "基础护盾",
        "基础防御",
        "基础神智",
        "技能",
        "溯源",
        "碎片",
        "第七溯源消耗",
        "专武",
        "同律武器",
    }
)

# 魔之楔记录里的非属性键（其余数值键都视作属性，满级小数）
_MOD_SKIP_KEYS = frozenset(
    {
        "id",
        "icon",
        "名称",
        "版本",
        "系列",
        "品质",
        "极性",
        "属性",
        "耐受",
        "类型",
        "消耗",
        "限定",
        "效果",
        "生效",
        "技能替换",
    }
)


def _attr_zone(key: str) -> tuple[str, str] | None:
    """属性键 → (分区, 面板显示名)

    分区：main（四维百分比）/ rate（率类与昂扬背水）/ elem_atk（属性攻击，独立乘区）
    返回 None 表示不进面板（武器面板的暴击/攻速等由 weapon 模块自行映射）。
    """
    if key in ("攻击", "生命", "防御", "护盾"):
        return ("main", key)
    if key == "神智":
        return ("main", key)
    if key in ("技能威力", "技能范围", "技能耐久", "技能效益", "充盈威力", "昂扬", "背水"):
        return ("rate", key)
    if key == "属性攻击":
        return ("elem_atk", "")  # 显示名由魔之楔自身属性补（水/火/雷/风/光/暗）
    return None


def _round2(value: float) -> float:
    return round(value + 1e-9, 2)


def _numeric_field(value: RawValue) -> bool:
    """字段值是否为数值或纯数值数组（文本型字段不进本地伤害计算）"""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    )


# ── 原始包取值：逐处 isinstance 收窄，不用 Any ─────────────


def _id_str(record: RawRecord, key: str) -> str:
    """id 字段转字符串（与 ``str(record.get(key))`` 同口径）"""
    return str(record.get(key))


def _str(record: RawRecord, key: str) -> str | None:
    """字符串字段；缺失或类型不符返回 None"""
    value = record.get(key)
    return value if isinstance(value, str) else None


def _int(record: RawRecord, key: str) -> int | None:
    """整数字段（bool 不算）；缺失或类型不符返回 None"""
    value = record.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _num(record: RawRecord, key: str) -> int | float | None:
    """数值字段（bool 不算）；缺失或类型不符返回 None。保留 int 形态，避免产物出现 x.0"""
    value = record.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _num_or(record: RawRecord, key: str, default: float) -> float:
    """数值字段，缺失取 default"""
    value = _num(record, key)
    return default if value is None else value


def _scalar(record: RawRecord, key: str) -> int | str | None:
    """int / str 标量字段（如 限定）；其余返回 None"""
    value = record.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, str)) else None


def _list_str(record: RawRecord, key: str) -> list[str]:
    """字符串数组字段（如 类型 / 精通）"""
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _list_int(record: RawRecord, key: str) -> list[int]:
    """整数数组字段（如同律武器的 skill）"""
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]


def _record(record: RawRecord, key: str) -> RawRecord | None:
    """对象字段（如 生效）"""
    value = record.get(key)
    return value if isinstance(value, dict) else None


def _records(record: RawRecord, key: str) -> list[RawRecord]:
    """对象数组字段（如同律武器 / 技能 / 字段）"""
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _lists(record: RawRecord, key: str) -> list[list[RawValue]]:
    """数组的数组字段（如生效块的 条件）"""
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, list)]


def _nums(record: RawRecord, key: str) -> dict[str, float]:
    """{键: 数值} 字段（如武器 加成）；非数值项丢弃"""
    value = record.get(key)
    if not isinstance(value, dict):
        return {}
    return {name: item for name, item in value.items() if isinstance(item, (int, float)) and not isinstance(item, bool)}


def _attr_value(record: RawRecord, key: str) -> AttrValue | None:
    """标量或纯数值数组属性（如技能字段的 值 / 值2）；其余返回 None"""
    value = record.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list) and all(isinstance(v, (int, float)) for v in value):
        return [v for v in value if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return None


def _attr_values(record: RawRecord, skip: frozenset[str]) -> dict[str, AttrValue]:
    """扫描记录的数值属性（标量或纯数值数组），跳过 skip 里的键与 bool"""
    out: dict[str, AttrValue] = {}
    for key, value in record.items():
        if key in skip or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, list) and value and all(isinstance(v, (int, float)) for v in value):
            # 数组型属性：逐档取值（下标即等级），不随等级线性缩放，如 追袭 技能伤害 [-0.5]
            out[key] = [v for v in value if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return out


def _convert_chars(chars: list[RawRecord]) -> ConvertedChars:
    """角色列表 → {byCharId, byName}，基础值折算 80 级、加成聚合为面板条目"""
    by_char: dict[str, CharEntry] = {}
    by_name: dict[str, str] = {}
    for char in chars:
        char_id = _id_str(char, "id")
        zones: dict[str, dict[str, float]] = {"main": {}, "rate": {}, "elem_atk": {}, "extra": {}}
        for key, value in _nums(char, "加成").items():
            zone = _attr_zone(key)
            if zone is None:
                # 隐藏属性（增伤/减伤/技能伤害等）：键名原样透传
                zones["extra"][key] = zones["extra"].get(key, 0.0) + value * 100
                continue
            zone_name, display = zone
            if zone_name == "elem_atk":
                # 角色加成里的属性攻击键形如「水属性攻击」
                elem = key.replace("属性攻击", "")
                zones["elem_atk"][elem] = zones["elem_atk"].get(elem, 0.0) + value * 100
                continue
            zones[zone_name][display] = zones[zone_name].get(display, 0.0) + value * 100

        con_weapons: list[WeaponRecord] = [
            WeaponRecord(
                id=_int(weapon, "id"),
                名称=_str(weapon, "名称"),
                类型=_list_str(weapon, "类型"),
                伤害类型=_str(weapon, "伤害类型"),
                攻击=_num(weapon, "攻击"),
                暴击=_num(weapon, "暴击"),
                暴伤=_num(weapon, "暴伤"),
                触发=_num(weapon, "触发"),
                攻速=_num(weapon, "攻速"),
                # 继承型同律武器（inherit=melee/ranged）没有自己的伤害类型/攻击，
                # 靠这些字段在被装备武器上取值（dna-builder CharBuild.syncSkillWeaponDamageType）
                inherit=_str(weapon, "inherit"),
                atk=_str(weapon, "atk"),
                视为=_str(weapon, "视为"),
                filter=_str(weapon, "filter"),
                skill=_list_int(weapon, "skill"),
            )
            for weapon in _records(char, "同律武器")
        ]

        char_name = _str(char, "名称")
        entry = CharEntry(
            id=_int(char, "id"),
            name=char_name,
            element=_str(char, "属性"),
            # 武器精通（精通判定用；同律武器绑定角色，必然命中）
            精通=_list_str(char, "精通"),
            额外精通=_list_str(char, "额外精通"),
            # 1 级白值（查询侧按角色实际等级缩放）
            baseLv1={
                "攻击": _num_or(char, "基础攻击", 0),
                "生命": _num_or(char, "基础生命", 0),
                "护盾": _num_or(char, "基础护盾", 0),
                "防御": _num_or(char, "基础防御", 0),
                "神智": _num_or(char, "基础神智", 0),
            },
            # 80 级值（等级未知时的兜底，与 wiki 阶段表满级行一致）
            base={
                "攻击": _round2(_num_or(char, "基础攻击", 0) * MAX_LEVEL_MULTIPLIER),
                "生命": round(_num_or(char, "基础生命", 0) * MAX_LEVEL_MULTIPLIER),
                "护盾": round(_num_or(char, "基础护盾", 0) * MAX_LEVEL_MULTIPLIER),
                "防御": _num_or(char, "基础防御", 0),
                "神智": _num_or(char, "基础神智", 0),
            },
            bonus=BonusZones(
                main=zones["main"],
                rate=zones["rate"],
                elem_atk=zones["elem_atk"],
                extra=zones["extra"],
            ),
            conWeapons=con_weapons,
            # 技能（紧凑）：字段保留 名称/影响/值(逐档)/值2/格式/伤害类型，
            # 供本地伤害计算按等级取值并按面板属性乘区缩放（替代官方 H5 接口）
            skills=[
                SkillEntry(
                    名称=_str(skill, "名称") or "",
                    类型=_str(skill, "类型"),
                    字段=[
                        SkillField(
                            名称=_str(field, "名称") or "",
                            影响=_str(field, "影响"),
                            值=_attr_value(field, "值"),
                            值2=_attr_value(field, "值2"),
                            格式=_str(field, "格式"),
                            基础=_str(field, "基础"),
                            伤害类型=_str(field, "伤害类型"),
                        )
                        for field in _records(skill, "字段")
                        if field.get("名称") is not None and _numeric_field(field.get("值"))
                    ],
                )
                for skill in _records(char, "技能")
                if skill.get("名称")
            ],
        )
        by_char[char_id] = entry
        if char_name:
            by_name[char_name] = char_id
    return ConvertedChars(byCharId=by_char, byName=by_name)


def _convert_effect(effect: RawRecord | None) -> ModEffect | None:
    """生效块 → {"conditions": [...], "attrs": {...}}；无条件或无数值属性时返回 None

    数据包形态：``{"条件": [["D趋向", ">=", 4]], "背水": 0.22}``。
    条件原样保留（判定在查询侧做）；属性保留数值标量与**纯数值数组**——
    数组形态按 dna-builder applyCondition 的表达式规则在查询侧结算：
    ``最终值 = min(条件属性值 × v1, v2)``（如 锋芒系列 增伤 [0.06, 0.18]）。
    """
    if not effect:
        return None
    conditions: list[Condition] = [
        [item for item in condition if isinstance(item, (str, int, float)) and not isinstance(item, bool)]
        for condition in _lists(effect, "条件")
    ]
    attrs: dict[str, AttrValue] = {}
    for key, value in effect.items():
        if key == "条件" or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            attrs[key] = value
        elif (
            isinstance(value, list)
            and value
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
        ):
            attrs[key] = [v for v in value if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not conditions or not attrs:
        return None
    return ModEffect(conditions=conditions, attrs=attrs)


def _convert_mods(mods: list[RawRecord]) -> ConvertedMods:
    """魔之楔列表 → {byId}，数值字段保留满级小数（数组型保留逐档取值），等级缩放放查询侧"""
    by_id: dict[str, ModRecord] = {}
    for mod in mods:
        quality_cn = _str(mod, "品质") or "白"
        quality = QUALITY_TO_INT.get(quality_cn, 1)
        by_id[_id_str(mod, "id")] = ModRecord(
            id=_int(mod, "id"),
            name=_str(mod, "名称"),
            series=_str(mod, "系列"),
            quality=quality,
            qualityName=quality_cn,
            element=_str(mod, "属性"),
            modType=_str(mod, "类型"),
            limited=_scalar(mod, "限定"),
            polarity=_str(mod, "极性"),
            tolerance=_num(mod, "耐受"),
            maxLevel=QUALITY_MAX_LEVEL.get(quality, 3),
            attrs=_attr_values(mod, _MOD_SKIP_KEYS),
            # 条件生效属性（如 羽蛇·背水：D趋向>=4 时 背水+22%），判定在查询侧
            effect=_convert_effect(_record(mod, "生效")),
        )
    return ConvertedMods(byId=by_id)


def _convert_weapons(weapons: list[RawRecord]) -> ConvertedWeapons:
    """武器列表 → {byId}，保留 1 级白值口径"""
    by_id: dict[str, WeaponRecord] = {}
    for weapon in weapons:
        by_id[_id_str(weapon, "id")] = WeaponRecord(
            id=_int(weapon, "id"),
            name=_str(weapon, "名称"),
            类型=_list_str(weapon, "类型"),
            伤害类型=_str(weapon, "伤害类型"),
            攻击=_num(weapon, "攻击"),
            暴击=_num(weapon, "暴击"),
            暴伤=_num(weapon, "暴伤"),
            触发=_num(weapon, "触发"),
            攻速=_num(weapon, "攻速"),
            # 武器自身的精炼「加成」（如 囚鸟的刺羽 昂扬 0.15）：dna-builder 把近战/远程的
            # 加成计入角色属性（同律不计），精缩放在查询侧（dob_loader.weapon_forge_bonus）
            加成=_nums(weapon, "加成"),
            # 带熔炉的武器加成不按精炼缩放（dna-builder LeveledWeapon.updateProperties）
            hasForge=bool(weapon.get("熔炉")),
        )
    return ConvertedWeapons(byId=by_id)


def convert_pack(zip_bytes: bytes) -> DobData:
    """数据包 zip → 插件面板用的紧凑 JSON 结构（内存内完成）"""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest: RawRecord = json.loads(zf.read("manifest.json").decode("utf-8"))
        char_data: RawValue = msgpack.unpackb(zf.read("modules/char.data.msgpack"), raw=False)
        mod_data: RawValue = msgpack.unpackb(zf.read("modules/mod.data.msgpack"), raw=False)
        weapon_data: RawValue = msgpack.unpackb(zf.read("modules/weapon.data.msgpack"), raw=False)

    def exports(decoded: RawValue) -> list[RawRecord]:
        """模块解码结果是 {导出名: 数据}，取第一个数组导出（即数据本体）"""
        if isinstance(decoded, list):
            return [item for item in decoded if isinstance(item, dict)]
        if isinstance(decoded, dict):
            for value in decoded.values():
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    chars = _convert_chars(exports(char_data))
    mods = _convert_mods(exports(mod_data))
    weapons = _convert_weapons(exports(weapon_data))
    mod_count = len(mods["byId"])
    char_count = len(chars["byCharId"])
    weapon_count = len(weapons["byId"])

    return DobData(
        _meta=DobMeta(
            source="dna-builder 数据包（DOB）",
            packVersion=_str(manifest, "version"),
            packBuiltAt=_str(manifest, "builtAt"),
            chars=char_count,
            mods=mod_count,
            weapons=weapon_count,
            generated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
        commonLevelUp=list(COMMON_LEVEL_UP),
        byCharId=chars["byCharId"],
        byName=chars["byName"],
        mods={"byId": mods["byId"]},
        weapons={"byId": weapons["byId"]},
    )


def _fetch_json(url: str) -> list[RawRecord]:
    """同步拉取版本列表 JSON（在线程里跑）；非数组视为失败，空数组由调用方判空"""
    last_error: Exception | None = None
    for base in CDN_BASES:
        full = f"{base}/{url}"
        try:
            response = httpx.get(full, timeout=20)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise ValueError(f"版本列表不是数组: {type(payload).__name__}")
            return [item for item in payload if isinstance(item, dict)]
        except (httpx.HTTPError, ValueError) as error:
            last_error = error
    raise last_error or RuntimeError("数据包版本列表拉取失败")


def _download_zip(package_file: str) -> bytes:
    """同步下载整包（先主源后备源）"""
    last_error: Exception | None = None
    for base in CDN_BASES:
        full = f"{base}/{package_file}"
        try:
            with httpx.Client(timeout=120) as client:
                with client.stream("GET", full) as response:
                    response.raise_for_status()
                    return response.read()
        except httpx.HTTPError as error:
            last_error = error
    raise last_error or RuntimeError("数据包下载失败")


def _migrate_legacy() -> None:
    """旧位置（dna_mod/data/）的 dob_data.json 迁移到 resource/dob/"""
    try:
        if _LEGACY_DATA_PATH.resolve() == DATA_PATH.resolve() or not _LEGACY_DATA_PATH.exists() or DATA_PATH.exists():
            return
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(_LEGACY_DATA_PATH), str(DATA_PATH))
        logger.info(f"[DNA DOB] 旧数据文件已迁移到 {DATA_PATH}")
    except OSError as error:
        logger.warning(f"[DNA DOB] 旧数据文件迁移失败（不影响使用）: {error!r}")


def read_local_meta() -> DobMeta | None:
    """读本地已转换数据的 _meta；文件缺失/损坏返回 None"""
    _migrate_legacy()
    try:
        raw: DobData = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return raw.get("_meta")


def convert_from_file(zip_path: str | Path) -> DobData:
    """从本地 zip 文件转换（离线/调试用）"""
    return convert_pack(Path(zip_path).read_bytes())


def _write_atomic(payload: str) -> None:
    """原子写入：临时文件按进程 + 时间戳命名，避免并发更新争用同一 .tmp"""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = DATA_PATH.with_name(f"{DATA_PATH.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(DATA_PATH)


def sync_from_file(zip_path: str | Path) -> str:
    """离线转换入口：把本地数据包 zip 转成 dob_data.json（不联网）"""
    data = convert_from_file(zip_path)
    _write_atomic(json.dumps(data, ensure_ascii=False))
    meta = data.get("_meta", {})
    return (
        f"DOB 数据包转换完成：v{meta.get('packVersion')}"
        f"（角色 {meta.get('chars')} / 魔之楔 {meta.get('mods')} / 武器 {meta.get('weapons')}）"
    )


def sync(force: bool = False) -> tuple[bool, str]:
    """检查并同步最新数据包（同步阻塞，调用方应放线程里）

    网络 / 文件 / 包格式这几类底层异常在此边界处收敛成 ``DobPackError``，
    调用方（命令、定时任务、启动钩子）只需 catch 这一种。

    Returns:
        (是否发生变化, 提示消息)
    """
    try:
        return _sync_once(force)
    except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        raise DobPackError(str(error)) from error


def _sync_once(force: bool) -> tuple[bool, str]:
    """sync 的实际流程（异常由 sync 收敛）"""
    versions = _fetch_json("versions.json")
    if not versions:
        return False, "数据包版本列表为空"
    latest = versions[0]
    version = _str(latest, "version")
    package_file = _str(latest, "packageFile") or f"{version}.zip"

    local_meta = read_local_meta()
    if not force and local_meta and local_meta.get("packVersion") == version:
        return False, f"DOB 数据包已是最新（v{version}）"

    zip_bytes = _download_zip(package_file)
    data = convert_pack(zip_bytes)
    _write_atomic(json.dumps(data, ensure_ascii=False))
    meta = data.get("_meta", {})
    logger.info(f"[DNA DOB] 数据包已更新: v{version}")
    return True, (
        f"DOB 数据包已更新到 v{version}"
        f"（角色 {meta.get('chars')} / 魔之楔 {meta.get('mods')} / 武器 {meta.get('weapons')}）"
    )


# 手动与自动更新共用一把锁，检查/下载/替换/重载串行执行，避免争用临时文件或交错写盘。
# asyncio.Lock 在 3.10+ 不再绑定事件循环，模块导入时创建是安全的。
_update_lock = asyncio.Lock()


async def sync_async(force: bool = False) -> tuple[bool, str]:
    """同步数据包（异步入口）：检查 → 下载 → 校验替换 → 重载查询层，全程持锁串行"""
    async with _update_lock:
        changed, message = await asyncio.to_thread(sync, force)
        if changed:
            # 更新成功后必须重载查询层：loader 在 import 时读盘，
            # 那时 dob_data.json 可能还不存在（首次启动）或仍是旧版本
            from . import dob_loader

            await asyncio.to_thread(dob_loader.reload)
    return changed, message


async def init_if_needed() -> None:
    """首次没有数据时同步等待初始化；有数据时由调用方决定是否后台检查"""
    if not is_data_ready():
        await sync_async()


def startup_auto_sync() -> None:
    """启动时后台检查更新（周期复查由 gsuid_core 调度器按配置间隔承担）"""
    import asyncio

    async def _run() -> None:
        try:
            changed, message = await sync_async()
            if changed:
                logger.info(f"[DNA DOB] {message}（启动检查）")
        except DobPackError as error:
            logger.warning(f"[DNA DOB] 启动检查失败（不影响使用）: {error!r}")

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        logger.warning("[DNA DOB] 无运行中的事件循环，跳过启动检查")


def is_data_ready() -> bool:
    """本地是否已有可用的转换数据"""
    _migrate_legacy()
    try:
        data: DobData = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    meta = data.get("_meta")
    return bool(meta and meta.get("packVersion"))


__all__ = [
    "CDN_BASES",
    "DobPackError",
    "init_if_needed",
    "is_data_ready",
    "COMMON_LEVEL_UP",
    "DATA_PATH",
    "MAX_LEVEL_MULTIPLIER",
    "QUALITY_MAX_LEVEL",
    "convert_from_file",
    "convert_pack",
    "read_local_meta",
    "startup_auto_sync",
    "sync",
    "sync_async",
    "sync_from_file",
]
