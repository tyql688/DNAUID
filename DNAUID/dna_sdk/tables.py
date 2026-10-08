"""dobsdk 数据层：DataPackStore 生命周期 + GameDataTables 缓存 + 查询小件。

替代 ``dna_mod/dob_pack.py``（下载/转换）与 ``dna_mod/dob_loader.py``（查询）——
不再维护自有 ``dob_data.json`` 转换格式，直接消费 dna-builder 数据包，
结算口径由 ``dna_builder_sdk``（dobsdk，下同）保证。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from dna_builder_sdk import DataPackStore
from dna_builder_sdk.calc.curves import COMMON_LEVEL_UP
from dna_builder_sdk.calc.entities import level_mod
from dna_builder_sdk.errors import DobApiError

try:
    from ..utils.resource.RESOURCE_PATH import DOB_PATH
except Exception:  # 无 gsuid 环境时打桩（harness/单测）
    DOB_PATH = None

__all__ = [
    "SdkPackError",
    "QUALITY_TO_INT",
    "WEAPON_ATTR_MAP",
    "WEAPON_SCOPE_KEYS",
    "SKILL_MAX_LEVEL",
    "CHAR_ID_ALIASES",
    "MASTERY_RATIO_HIT",
    "cache_dir",
    "use_cache_dir",
    "datapack_store",
    "get_tables",
    "reload_tables",
    "is_ready",
    "version",
    "built_at",
    "counts",
    "char_record",
    "mod_record",
    "mod_name",
    "mod_quality_int",
    "weapon_record",
    "con_weapon_record",
    "weapon_types",
    "char_mastery",
    "weapon_category",
    "is_skill_weapon",
    "is_weapon_mastered",
    "weapon_mastery_ratio",
    "weapon_forge_bonus",
    "level_multiplier",
    "leveled_mod_attrs",
    "weapon_mod_attrs",
    "damage_reduce",
]

CACHE_ENV_HINT = "DNA_BUILDER_CACHE"


class SdkPackError(RuntimeError):
    """数据包外部错误（网络 / 落盘 / 包格式），调用方只需 catch 这一种。"""


# —— 沿用旧口径的小常量（渲染/判定共用，键名与数据包一致）——
QUALITY_TO_INT = {"白": 1, "蓝": 2, "紫": 3, "金": 4, "彩": 5}
WEAPON_ATTR_MAP = {
    "攻击": "攻击",
    "物理": "物理",
    "暴击": "暴击率",
    "暴伤": "暴击伤害",
    "攻速": "攻击速度",
    "触发": "触发概率",
}
# 可从角色侧穿透到武器面板的属性（dna-builder CharBuild.attrAllowCharToWeapon）
WEAPON_SCOPE_KEYS = ("暴击", "暴伤", "触发", "攻速")
SKILL_MAX_LEVEL = 12
# 男主 charId → 数据包条目 id（官方接口用 6 位 id，数据包只有 4 位条目）
CHAR_ID_ALIASES = {"120101": "1201", "160101": "1601", "220101": "2201"}
# 精通命中倍率：游戏实测同律也是 ×1.2（dna-builder 写 1.4，按实测来）
MASTERY_RATIO_HIT = 1.2
_WEAPON_REFINE_BASE = 5


def cache_dir() -> Path:
    """数据包缓存目录（沿用旧 dob 目录，与 dob_data.json 共存，文件名不冲突）。"""
    if _cache_override is not None:
        return _cache_override
    if DOB_PATH is not None:
        return Path(DOB_PATH)
    from dna_builder_sdk.data_pack import _default_cache_dir

    return Path(_default_cache_dir())


_lock = threading.RLock()
_store: DataPackStore | None = None
_tables: Any | None = None
_cache_override: Path | None = None


def use_cache_dir(path: str | Path | None) -> None:
    """切换数据包缓存目录（e2e 注入最小包用；None 切回默认）。切换后清空表缓存。"""
    global _store, _tables, _cache_override
    with _lock:
        _cache_override = Path(path) if path is not None else None
        _store = None
        _tables = None


def _store_of() -> DataPackStore:
    global _store
    with _lock:
        if _store is None:
            _store = DataPackStore(cache_dir=str(cache_dir()))
        return _store


def datapack_store() -> DataPackStore:
    """底层的 DataPackStore（同步逻辑用；表缓存仍走 get_tables）。"""
    return _store_of()


def get_tables():
    """取缓存的 GameDataTables（未加载时 ensure + 转换；线程安全）。"""
    global _tables
    with _lock:
        if _tables is not None:
            return _tables
        store = _store_of()
        try:
            _tables = store.load_tables()
        except DobApiError as error:
            raise SdkPackError(f"DOB 数据表加载失败：{error}") from error
        return _tables


def reload_tables():
    """清空重载（运行时热重载入口；外部更新 zip 后调用，无需重启）。"""
    global _tables
    with _lock:
        store = _store_of()
        try:
            store.reload()
        except DobApiError as error:
            raise SdkPackError(f"DOB 数据包重载失败：{error}") from error
        _tables = None
        try:
            _tables = store.load_tables()
        except DobApiError as error:
            raise SdkPackError(f"DOB 数据表加载失败：{error}") from error
        return _tables


def is_ready() -> bool:
    """本地是否有可用数据包（不联网，只看安装目录）。"""
    try:
        return bool(_store_of().installed_versions())
    except DobApiError:
        return False


def version() -> str | None:
    """当前激活版本（未激活时按最新已安装版本读 manifest，不联网）。"""
    store = _store_of()
    manifest = store.manifest
    if manifest is None:
        installed = store.installed_versions()
        if not installed:
            return None
        try:
            manifest = store.activate(installed[-1])
        except DobApiError:
            return None
    return manifest.get("version")


def built_at() -> str | None:
    store = _store_of()
    manifest = store.manifest
    if manifest is None:
        if version() is None:
            return None
        manifest = store.manifest
    return manifest.get("builtAt") if manifest else None


def counts() -> dict[str, int]:
    tables = get_tables()
    return {
        "chars": len(tables.chars),
        "mods": len(tables.mods),
        "weapons": len(tables.weapons),
    }


# —— 记录查询（键口径与旧 dob_loader 一致：官方 id 直查数据包 id）——


def _by_id(mapping: dict, value) -> dict | None:
    """id 双向查（数据包 id 可能是 int，官方来的是 int/str）。"""
    if value is None:
        return None
    record = mapping.get(value)
    if record is not None:
        return record
    try:
        record = mapping.get(str(value))
    except Exception:
        record = None
    if record is not None:
        return record
    try:
        return mapping.get(int(value))
    except (TypeError, ValueError):
        return None


def char_record(char_id: int | str | None) -> dict | None:
    """按游戏 charId 取角色条目（男主 id 归一化）。"""
    tables = get_tables()
    record = _by_id(tables.char_by_id, char_id)
    if record is not None:
        return record
    alias = CHAR_ID_ALIASES.get(str(char_id)) if char_id is not None else None
    if alias is None:
        return None
    return _by_id(tables.char_by_id, alias)


def mod_record(mod_id: int | str | None) -> dict | None:
    """按官方 modes[].id（= 数据包 mod id）取记录（含名称/品质回退）。"""
    return _by_id(get_tables().mod_by_id, mod_id)


def weapon_record(weapon_id: int | str | None) -> dict | None:
    """按武器 id 取普通武器记录（不含同律武器）。"""
    return _by_id(get_tables().weapon_by_id, weapon_id)


def con_weapon_record(char_id: int | str | None, weapon_id: int | str | None) -> dict | None:
    """按角色与同律武器 id 取同律武器条目。"""
    entry = char_record(char_id)
    if entry is None or weapon_id is None:
        return None
    for weapon in entry.get("同律武器") or []:
        if weapon.get("id") is not None and str(weapon.get("id")) == str(weapon_id):
            return weapon
    return None


def weapon_types(weapon: dict | None) -> list:
    if not weapon:
        return []
    return list(weapon.get("类型") or [])


def weapon_category(weapon: dict | None) -> str | None:
    """武器类别（精通判定/条件计数的口径：同律取 类型[2]，普通取 类型[1]）。"""
    types = weapon_types(weapon)
    if not types:
        return None
    index = 2 if types[0] == "同律" else 1
    if index < len(types):
        return types[index]
    return types[-1]


def is_skill_weapon(weapon: dict | None) -> bool:
    """是否同律武器（绑定角色，必然命中精通）。"""
    types = weapon_types(weapon)
    return bool(types) and types[0] == "同律"


def char_mastery(char_id: int | str | None) -> tuple[list, list]:
    entry = char_record(char_id)
    if entry is None:
        return [], []
    return list(entry.get("精通") or []), list(entry.get("额外精通") or [])


def is_weapon_mastered(char_id: int | str | None, weapon: dict | None) -> bool:
    if weapon is None:
        return False
    category = weapon_category(weapon)
    if not category:
        return False
    mastered, _ = char_mastery(char_id)
    return category in mastered or "全部能力类型" in mastered or "全部类型" in mastered


def weapon_mastery_ratio(char_id: int | str | None, weapon: dict | None) -> float:
    """武器攻击精通倍率：命中 1.2 / 未命中 1.0（同律必然命中）。"""
    if weapon is None:
        return 1.0
    if is_skill_weapon(weapon):
        return MASTERY_RATIO_HIT
    category = weapon_category(weapon)
    if not category:
        return 1.0
    mastered, _ = char_mastery(char_id)
    hit = category in mastered or "全部类型" in mastered
    return MASTERY_RATIO_HIT if hit else 1.0


def weapon_forge_bonus(weapon: dict | None, skill_level: int | None) -> dict:
    """武器自身「加成」按精炼缩放后的小数字典（dna-builder LeveledWeapon 口径）。

    加成值 / 5 × (精炼 + 5)；带熔炉取原值；精炼缺省按满精炼 5。
    """
    if not weapon:
        return {}
    bonus = weapon.get("加成") or {}
    if not bonus:
        return {}
    if weapon.get("hasForge"):
        return dict(bonus)
    level = _WEAPON_REFINE_BASE if skill_level is None else max(0, min(_WEAPON_REFINE_BASE, int(skill_level)))
    scale = (level + _WEAPON_REFINE_BASE) / _WEAPON_REFINE_BASE
    return {key: value * scale for key, value in bonus.items()}


def level_multiplier(level: int | None) -> float | None:
    """等级 → 成长倍率（1~80）；无效返回 None。"""
    if level is None:
        return None
    if level < 1 or level > len(COMMON_LEVEL_UP):
        return None
    return COMMON_LEVEL_UP[level - 1]


def _num(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def leveled_mod_attrs(mod_id: int | str | None, level: int | None) -> dict | None:
    """某魔之楔在指定强化等级下的 leveled 实例属性（小数；条件生效已由引擎结算）。

    对应旧 ``get_mod_attrs``，但返回的是引擎结算后的完整 props（含已满足的
    条件生效块贡献 —— 与 dna-builder/BD 口径一致；旧 DNAUID 口径只取基础值）。
    查不到记录返回 None（调用方跳过，与旧 missing 口径一致）。
    """
    tables = get_tables()
    raw = mod_record(mod_id)
    if raw is None:
        return None
    inst = level_mod(raw, level, None, tables.mod_effect_by_id.get(raw.get("id")))
    out: dict[str, float] = {}
    for key, value in inst.items():
        if key.startswith("_") or key in ("id", "maxLevel", "耐受"):
            continue
        number = _num(value)
        if number is None:
            continue
        out[key] = number
    return out


def weapon_mod_attrs(mod_id: int | str | None, level: int | None) -> dict | None:
    """武器魔之楔加成（百分比，键为武器面板显示名），供武器面板/伤害用。"""
    attrs = leveled_mod_attrs(mod_id, level)
    if attrs is None:
        return None
    out: dict[str, float] = {}
    for key, fraction in attrs.items():
        display = WEAPON_ATTR_MAP.get(key)
        if display:
            out[display] = out.get(display, 0.0) + fraction * 100
    return out


def mod_quality_int(mod_id: int | str | None) -> int | None:
    """mod 品质数值（渲染底图用；官方缺品质时回退数据包）。"""
    record = mod_record(mod_id)
    if not record:
        return None
    quality = QUALITY_TO_INT.get(record.get("品质"))
    return quality if quality else None


def mod_name(mod_id: int | str | None) -> str | None:
    """mod 名称（官方缺名时回退数据包）。"""
    record = mod_record(mod_id)
    if not record:
        return None
    return record.get("名称")


def damage_reduce(values: list[float]) -> float:
    """减伤乘法聚合（dna-builder getTotalBonusReduce 口径）。"""
    bonus = 0.0
    for value in values:
        if value > 0:
            bonus = 1 - (1 - bonus) * (1 - value)
    return bonus
