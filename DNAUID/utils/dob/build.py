from __future__ import annotations

import re
from enum import StrEnum
from dataclasses import dataclass

from dna_builder_sdk.calc import Engine, build_state

from gsuid_core.logger import logger

from . import records
from .pack import get_tables
from ..api.model import Mode, RoleDetail, WeaponDetail


class WeaponSlot(StrEnum):
    MELEE = "近战"
    RANGED = "远程"
    SKILL = "同律"


class DobBuildError(RuntimeError):
    """装配失败（角色未收录等），调用方转用户提示。"""


@dataclass(frozen=True, slots=True, kw_only=True)
class DobBuild:
    """一次装配：结算引擎 + 用于展示的角色/武器详情。"""

    engine: Engine
    role: RoleDetail
    weapons: dict[WeaponSlot, WeaponDetail]


# 溯源描述里的技能等级加成，形如「[残光]等级+2」
_TRACE_BONUS_RE = re.compile(r"\[([^\]]+)]\s*等级\s*\+\s*(\d+)")
# 角色 modes：前 8 个是角色槽，其后是中枢
_CHAR_SLOTS = 8
_MAX_TRACES = 7


def skill_base_levels(role: RoleDetail) -> list[int]:
    """官方技能等级已含溯源加成，引擎要的是扣掉加成后的基础等级。"""
    bonus: dict[str, int] = {}
    for trace in role.traces[: role.gradeLevel]:
        for name, text in _TRACE_BONUS_RE.findall(trace.description):
            bonus[name] = bonus.get(name, 0) + int(text)
    return [max(1, skill.level - bonus.get(skill.skillName, 0)) for skill in role.skills]


def _mod_pairs(modes: list[Mode], missing: list[str]) -> list[list[int]]:
    pairs: list[list[int]] = []
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
        return {}
    if records.weapon_record(weapon.id) is None:
        # 新武器先于数据包上线：按空武器计算，面板显示「无法计算」
        missing.append(f"武器 {weapon.name}（id={weapon.id}）")
        return {prefix: 0}
    return {prefix: weapon.id, f"{prefix}Refine": weapon.skillLevel, f"{prefix}Level": weapon.level}


def build_engine(role: RoleDetail, weapons: dict[WeaponSlot, WeaponDetail]) -> DobBuild:
    """官方角色/武器详情 → 引擎；数据包未收录的魔之楔与武器跳过，不阻断出图。"""
    char = records.char_record(role.charId)
    if char is None:
        raise DobBuildError(f"角色 {role.charName}（id={role.charId}）未在数据包收录")

    missing: list[str] = []
    melee = weapons.get(WeaponSlot.MELEE)
    ranged = weapons.get(WeaponSlot.RANGED)
    skill = weapons.get(WeaponSlot.SKILL)
    settings: dict[str, int | list[list[int]]] = {
        "charLevel": role.level,
        "charMods": _mod_pairs(role.modes[:_CHAR_SLOTS], missing),
        "meleeMods": _mod_pairs(melee.modes if melee else [], missing),
        "rangedMods": _mod_pairs(ranged.modes if ranged else [], missing),
        "skillWeaponMods": _mod_pairs(skill.modes if skill else [], missing),
        **_weapon_settings("meleeWeapon", melee, missing),
        **_weapon_settings("rangedWeapon", ranged, missing),
    }
    aura = _mod_pairs(role.modes[_CHAR_SLOTS:], missing)
    if aura:
        settings["auraMod"] = aura[0][0]
    if missing:
        logger.warning(f"[DNA 面板] {role.charName} 有数据包未收录的条目，已跳过: {missing}")

    tables = get_tables()
    traces = min(max(role.gradeLevel, 0), _MAX_TRACES)
    try:
        state = build_state(char["id"], settings, tables, skill_levels=skill_base_levels(role)[:3], traces=traces)
    except KeyError as error:
        raise DobBuildError(f"装配失败：{error}") from error
    return DobBuild(engine=Engine(state, tables), role=role, weapons=weapons)
