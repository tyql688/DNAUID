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
   getWeaponDetail.attribute 同口径）。

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

import asyncio
import io
import json
import os
import shutil
import time
import zipfile
from typing import Any
from pathlib import Path
from datetime import datetime

try:
    from gsuid_core.logger import logger
except ImportError:  # pragma: no cover - 允许脱离 gsuid_core 单测
    import logging

    logger = logging.getLogger("dna_dob_pack")

import msgpack

# 允许脱离 gsuid_core 环境复用（如本地脚本）：httpx 不可用时退回 urllib
try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

# 数据文件统一放 data/DNAUID/resource/dob/（路径定义在 utils/resource/RESOURCE_PATH.py，
# 下载、读取和状态查询共用）；脱离 gsuid_core 的独立环境回退到模块目录。
# 旧位置 dna_mod/data/dob_data.json 在读取时自动迁移。
try:
    from ..utils.resource.RESOURCE_PATH import DOB_DATA_PATH as DATA_PATH
except ImportError:  # pragma: no cover - 独立测试环境
    DATA_PATH = Path(__file__).parent / "data" / "dob_data.json"
_LEGACY_DATA_PATH = Path(__file__).parent / "data" / "dob_data.json"

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
    if key == "神智":  # 数据包键名 → 面板显示名
        return ("main", "最大神志")
    if key in ("技能威力", "技能范围", "技能耐久", "技能效益", "充盈威力", "昂扬", "背水"):
        return ("rate", key)
    if key == "属性攻击":
        return ("elem_atk", "")  # 显示名由魔之楔自身属性补（水/火/雷/风/光/暗）
    return None


def _round2(value: float) -> float:
    return round(value + 1e-9, 2)


def _numeric_field(value: Any) -> bool:
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


def _convert_chars(chars: list[dict[str, Any]]) -> dict[str, Any]:
    """角色列表 → {byCharId, byName}，基础值折算 80 级、加成聚合为面板条目"""
    by_char: dict[str, Any] = {}
    by_name: dict[str, Any] = {}
    for char in chars:
        char_id = str(char.get("id"))
        bonus_zones: dict[str, dict[str, float]] = {"main": {}, "rate": {}, "elem_atk": {}, "extra": {}}
        for key, value in (char.get("加成") or {}).items():
            if not isinstance(value, (int, float)):
                continue
            zone = _attr_zone(key)
            if zone is None:
                # 隐藏属性（增伤/减伤/技能伤害等）：键名原样透传
                bonus_zones["extra"][key] = bonus_zones["extra"].get(key, 0.0) + value * 100
                continue
            zone_name, display = zone
            if zone_name == "elem_atk":
                # 角色加成里的属性攻击键形如「水属性攻击」
                elem = key.replace("属性攻击", "")
                bonus_zones["elem_atk"][elem] = bonus_zones["elem_atk"].get(elem, 0.0) + value * 100
                continue
            bonus_zones[zone_name][display] = bonus_zones[zone_name].get(display, 0.0) + value * 100

        con_weapons = [
            {
                "id": w.get("id"),
                "名称": w.get("名称"),
                "攻击": w.get("攻击"),
                "暴击": w.get("暴击"),
                "暴伤": w.get("暴伤"),
                "触发": w.get("触发"),
                "攻速": w.get("攻速"),
            }
            for w in (char.get("同律武器") or [])
        ]

        entry = {
            "id": char.get("id"),
            "name": char.get("名称"),
            "element": char.get("属性"),
            # 1 级白值（查询侧按角色实际等级缩放）
            "baseLv1": {
                "攻击": char.get("基础攻击", 0),
                "生命": char.get("基础生命", 0),
                "护盾": char.get("基础护盾", 0),
                "防御": char.get("基础防御", 0),
                "最大神志": char.get("基础神智", 0),
            },
            # 80 级值（等级未知时的兜底，与 wiki 阶段表满级行一致）
            "base": {
                "攻击": _round2(char.get("基础攻击", 0) * MAX_LEVEL_MULTIPLIER),
                "生命": round(char.get("基础生命", 0) * MAX_LEVEL_MULTIPLIER),
                "护盾": round(char.get("基础护盾", 0) * MAX_LEVEL_MULTIPLIER),
                "防御": char.get("基础防御", 0),
                "最大神志": char.get("基础神智", 0),
            },
            "bonus": bonus_zones,
            "conWeapons": con_weapons,
            # 技能（紧凑）：字段保留 名称/影响/值(逐档)/值2/格式/伤害类型，
            # 供本地伤害计算按等级取值并按面板属性乘区缩放（替代官方 H5 接口）
            "skills": [
                {
                    "名称": skill.get("名称"),
                    "类型": skill.get("类型"),
                    "字段": [
                        {
                            "名称": f.get("名称"),
                            "影响": f.get("影响"),
                            "值": f.get("值"),
                            "值2": f.get("值2"),
                            "格式": f.get("格式"),
                            "基础": f.get("基础"),
                            "伤害类型": f.get("伤害类型"),
                        }
                        for f in (skill.get("字段") or [])
                        if f.get("名称") is not None and _numeric_field(f.get("值"))
                    ],
                }
                for skill in (char.get("技能") or [])
                if skill.get("名称")
            ],
        }
        by_char[char_id] = entry
        by_name[char.get("名称")] = char_id
    return {"byCharId": by_char, "byName": by_name}


def _convert_effect(effect: dict[str, Any] | None) -> dict[str, Any] | None:
    """生效块 → {"conditions": [...], "attrs": {...}}；无条件或无数值属性时返回 None

    数据包形态：``{"条件": [["D趋向", ">=", 4]], "背水": 0.22}``。
    条件原样保留（判定在查询侧做）；属性保留数值标量与**纯数值数组**——
    数组形态按 dna-builder applyCondition 的表达式规则在查询侧结算：
    ``最终值 = min(条件属性值 × v1, v2)``（如 锋芒系列 增伤 [0.06, 0.18]）。
    """
    if not effect:
        return None
    conditions = [list(c) for c in (effect.get("条件") or [])]
    attrs: dict[str, Any] = {}
    for key, value in effect.items():
        if key == "条件" or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            attrs[key] = value
        elif isinstance(value, list) and value and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            attrs[key] = list(value)
    if not conditions or not attrs:
        return None
    return {"conditions": conditions, "attrs": attrs}


def _convert_mods(mods: list[dict[str, Any]]) -> dict[str, Any]:
    """魔之楔列表 → {byId}，数值字段保留满级小数（数组型保留逐档取值），等级缩放放查询侧"""
    by_id: dict[str, Any] = {}
    for mod in mods:
        mod_id = mod.get("id")
        quality_cn = mod.get("品质") or "白"
        quality = QUALITY_TO_INT.get(quality_cn, 1)
        max_level = QUALITY_MAX_LEVEL.get(quality, 3)
        attrs: dict[str, Any] = {}
        for key, value in mod.items():
            if key in _MOD_SKIP_KEYS or isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                attrs[key] = value
            elif isinstance(value, list) and value and all(isinstance(v, (int, float)) for v in value):
                # 数组型属性：逐档取值（下标即等级），不随等级线性缩放，如 追袭 技能伤害 [-0.5]
                attrs[key] = list(value)
        by_id[str(mod_id)] = {
            "id": mod_id,
            "name": mod.get("名称"),
            "series": mod.get("系列"),
            "quality": quality,
            "qualityName": quality_cn,
            "element": mod.get("属性"),
            "modType": mod.get("类型"),
            "limited": mod.get("限定"),
            "polarity": mod.get("极性"),
            "tolerance": mod.get("耐受"),
            "maxLevel": max_level,
            "attrs": attrs,
            # 条件生效属性（如 羽蛇·背水：D趋向>=4 时 背水+22%），判定在查询侧
            "effect": _convert_effect(mod.get("生效")),
        }
    return {"byId": by_id}


def _convert_weapons(weapons: list[dict[str, Any]]) -> dict[str, Any]:
    """武器列表 → {byId}，保留 1 级白值口径"""
    by_id: dict[str, Any] = {}
    for weapon in weapons:
        by_id[str(weapon.get("id"))] = {
            "id": weapon.get("id"),
            "name": weapon.get("名称"),
            "types": weapon.get("类型") or [],
            "攻击": weapon.get("攻击"),
            "暴击": weapon.get("暴击"),
            "暴伤": weapon.get("暴伤"),
            "触发": weapon.get("触发"),
            "攻速": weapon.get("攻速"),
        }
    return {"byId": by_id}


def convert_pack(zip_bytes: bytes) -> dict[str, Any]:
    """数据包 zip → 插件面板用的紧凑 JSON 结构（内存内完成）"""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        manifest_text = zf.read("manifest.json").decode("utf-8")
        manifest = json.loads(manifest_text)
        char_data = msgpack.unpackb(zf.read("modules/char.data.msgpack"), raw=False)
        mod_data = msgpack.unpackb(zf.read("modules/mod.data.msgpack"), raw=False)
        weapon_data = msgpack.unpackb(zf.read("modules/weapon.data.msgpack"), raw=False)

    def exports(decoded: Any) -> list[dict[str, Any]]:
        """模块解码结果是 {导出名: 数据}，取第一个数组导出（即数据本体）"""
        if isinstance(decoded, list):
            return decoded
        for value in (decoded or {}).values():
            if isinstance(value, list):
                return value
        return []

    chars = _convert_chars(exports(char_data))
    mods = _convert_mods(exports(mod_data))
    weapons = _convert_weapons(exports(weapon_data))
    mod_count = len(mods["byId"])
    char_count = len(chars["byCharId"])
    weapon_count = len(weapons["byId"])

    return {
        "_meta": {
            "source": "dna-builder 数据包（DOB）",
            "packVersion": manifest.get("version"),
            "packBuiltAt": manifest.get("builtAt"),
            "chars": char_count,
            "mods": mod_count,
            "weapons": weapon_count,
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "commonLevelUp": list(COMMON_LEVEL_UP),
        **chars,
        "mods": mods,
        "weapons": weapons,
    }


def _urllib_get(url: str, timeout: int) -> bytes:
    """无 httpx 时的兜底下载（同步）"""
    from urllib.request import urlopen

    with urlopen(url, timeout=timeout) as response:  # noqa: S310 - 固定 CDN 地址
        return response.read()


def _fetch_json(url: str) -> Any:
    """同步拉取 JSON（在线程里跑）"""
    last_error: Exception | None = None
    for base in CDN_BASES:
        full = f"{base}/{url}"
        try:
            if httpx is not None:
                response = httpx.get(full, timeout=20)
                response.raise_for_status()
                return response.json()
            return json.loads(_urllib_get(full, 20).decode("utf-8"))
        except Exception as error:  # noqa: BLE001
            last_error = error
    raise last_error or RuntimeError("数据包版本列表拉取失败")


def _download_zip(package_file: str) -> bytes:
    """同步下载整包（先主源后备源）"""
    last_error: Exception | None = None
    for base in CDN_BASES:
        full = f"{base}/{package_file}"
        try:
            if httpx is not None:
                with httpx.Client(timeout=120) as client:
                    with client.stream("GET", full) as response:
                        response.raise_for_status()
                        return response.read()
            return _urllib_get(full, 120)
        except Exception as error:  # noqa: BLE001
            last_error = error
    raise last_error or RuntimeError("数据包下载失败")


def _migrate_legacy() -> None:
    """旧位置（dna_mod/data/）的 dob_data.json 迁移到 resource/dob/"""
    try:
        if (
            _LEGACY_DATA_PATH.resolve() == DATA_PATH.resolve()
            or not _LEGACY_DATA_PATH.exists()
            or DATA_PATH.exists()
        ):
            return
        DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(_LEGACY_DATA_PATH), str(DATA_PATH))
        logger.info(f"[DNA DOB] 旧数据文件已迁移到 {DATA_PATH}")
    except Exception as error:  # noqa: BLE001
        logger.warning(f"[DNA DOB] 旧数据文件迁移失败（不影响使用）: {error!r}")


def read_local_meta() -> dict[str, Any] | None:
    """读本地已转换数据的 _meta；文件缺失/损坏返回 None"""
    _migrate_legacy()
    try:
        raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return raw.get("_meta")
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def convert_from_file(zip_path: str | Path) -> dict[str, Any]:
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
    meta = data["_meta"]
    return (
        f"DOB 数据包转换完成：v{meta['packVersion']}"
        f"（角色 {meta['chars']} / 魔之楔 {meta['mods']} / 武器 {meta['weapons']}）"
    )


def sync(force: bool = False) -> tuple[bool, str]:
    """检查并同步最新数据包（同步阻塞，调用方应放线程里）

    Returns:
        (是否发生变化, 提示消息)
    """
    versions = _fetch_json("versions.json")
    if not versions:
        return False, "数据包版本列表为空"
    latest = versions[0]
    version = latest.get("version")
    package_file = latest.get("packageFile") or f"{version}.zip"

    local_meta = read_local_meta()
    if not force and local_meta and local_meta.get("packVersion") == version:
        return False, f"DOB 数据包已是最新（v{version}）"

    zip_bytes = _download_zip(package_file)
    data = convert_pack(zip_bytes)
    _write_atomic(json.dumps(data, ensure_ascii=False))
    meta = data["_meta"]
    logger.info(f"[DNA DOB] 数据包已更新: v{version}")
    return True, (
        f"DOB 数据包已更新到 v{version}（角色 {meta['chars']} / 魔之楔 {meta['mods']} / 武器 {meta['weapons']}）"
    )


# 手动与自动更新共用一把锁：检查、下载、替换和重载串行执行，
# 避免两次更新同时进入、争用临时文件或交错写盘。
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
        except Exception as error:  # noqa: BLE001
            logger.warning(f"[DNA DOB] 启动检查失败（不影响使用）: {error!r}")

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        logger.warning("[DNA DOB] 无运行中的事件循环，跳过启动检查")


def is_data_ready() -> bool:
    """本地是否已有可用的转换数据"""
    _migrate_legacy()
    try:
        meta = json.loads(DATA_PATH.read_text(encoding="utf-8")).get("_meta")
        return bool(meta and meta.get("packVersion"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


__all__ = [
    "CDN_BASES",
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
