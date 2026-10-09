from __future__ import annotations

from .pack import get_tables

# 数据包品质文字 → mod 底图框色编号（mod_*_{n}.png）
QUALITY_TO_INT = {"白": 1, "绿": 2, "蓝": 3, "紫": 4, "金": 5}
# 男主官方 charId 是 6 位，数据包条目只有 4 位
_CHAR_ID_ALIASES = {120101: 1201, 160101: 1601, 220101: 2201}


def char_record(char_id: int) -> dict | None:
    return get_tables().char_by_id.get(_CHAR_ID_ALIASES.get(char_id, char_id))


def mod_record(mod_id: int) -> dict | None:
    return get_tables().mod_by_id.get(mod_id)


def weapon_record(weapon_id: int) -> dict | None:
    return get_tables().weapon_by_id.get(weapon_id)


def con_weapon_record(char_id: int) -> dict | None:
    """角色绑定的同律武器（数据包里每个角色至多一把）。"""
    char = char_record(char_id)
    if char is None or not char.get("同律武器"):
        return None
    return char["同律武器"][0]


def weapon_category(record: dict) -> str:
    """武器类别（单手剑/重剑…）：同律武器的「类型」多一级「同律」前缀。"""
    types = record["类型"]
    return types[2] if types[0] == "同律" else types[1]


def mod_name(mod_id: int) -> str | None:
    record = mod_record(mod_id)
    return record["名称"] if record else None


def mod_quality(mod_id: int) -> int:
    """mod 底框品质，数据包未收录的按最低品质。"""
    record = mod_record(mod_id)
    return QUALITY_TO_INT[record["品质"]] if record else 1
