from __future__ import annotations

from enum import StrEnum

from pydantic import JsonValue

from gsuid_core.logger import logger

from . import records
from .engine import DobBuildError
from ..api.model import Mode, RoleDetail, WeaponDetail


class WeaponSlot(StrEnum):
    MELEE = "近战"
    RANGED = "远程"
    SKILL = "同律"


# 角色 modes：前 8 个是角色槽，其后是中枢
_CHAR_SLOTS = 8


def _mod_pairs(modes: list[Mode], missing: list[str]) -> list[JsonValue]:
    pairs: list[JsonValue] = []
    for mode in modes:
        if mode.id <= 0:
            continue
        if records.mod_record(mode.id) is None:
            missing.append(f"魔之楔 {mode.name}（id={mode.id}）")
            continue
        pairs.append([mode.id, mode.level or 0])
    return pairs


def _weapon_settings(prefix: str, weapon: WeaponDetail | None, missing: list[str]) -> dict[str, int]:
    if weapon is None:
        return {prefix: 0}
    if records.weapon_record(weapon.id) is None:
        # 新武器先于数据包上线：按空武器计算，面板显示「无法计算」
        missing.append(f"武器 {weapon.name}（id={weapon.id}）")
        return {prefix: 0}
    return {prefix: weapon.id, f"{prefix}Refine": weapon.skillLevel, f"{prefix}Level": weapon.level}


def role_settings(role: RoleDetail, weapons: dict[WeaponSlot, WeaponDetail]) -> dict[str, JsonValue]:
    """官方角色/武器详情 → 结算设置；未收录的魔之楔与武器跳过并记录日志。"""
    char = records.char_record(role.charId)
    if char is None:
        raise DobBuildError(f"角色 {role.charName}（id={role.charId}）未在数据包收录")

    missing: list[str] = []
    melee = weapons.get(WeaponSlot.MELEE)
    ranged = weapons.get(WeaponSlot.RANGED)
    skill = weapons.get(WeaponSlot.SKILL)
    settings: dict[str, JsonValue] = {
        "charLevel": role.level,
        # 官方技能等级已包含溯源加成。
        "charSkillLevel": [skill.level for skill in role.skills[:3]],
        "auraMod": 0,
        "charMods": _mod_pairs(role.modes[:_CHAR_SLOTS], missing),
        "meleeMods": _mod_pairs(melee.modes if melee else [], missing),
        "rangedMods": _mod_pairs(ranged.modes if ranged else [], missing),
        "skillWeaponMods": _mod_pairs(skill.modes if skill else [], missing),
        **_weapon_settings("meleeWeapon", melee, missing),
        **_weapon_settings("rangedWeapon", ranged, missing),
    }
    aura = next((mode for mode in role.modes[_CHAR_SLOTS:] if records.mod_record(mode.id) is not None), None)
    if aura is not None:
        settings["auraMod"] = aura.id
    if missing:
        logger.warning(f"[DNA 面板] {role.charName} 有数据包未收录的条目，已跳过: {missing}")

    return settings
