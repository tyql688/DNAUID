"""装配层：官方 RoleDetail/WeaponDetail → dobsdk settings → Engine。

输入输出口径以 dna-builder TS（CharBuild）为准：
- 角色槽 8 + 中枢（aura，常驻满级，TS 默认 31524）；
- 近战/远程武器槽 mod 与武器（id/精炼/等级）；
- 技能 trio 取官方 skills 表顺序的基础等级（扣掉溯源加成），溯源等级取 gradeLevel；
- 同律武器不进装配（只影响自己的面板/伤害，TS 同理：skillWeapon 不进角色表）；
- 未收录 id 直接跳过并记录（新版游戏先于数据包更新时不阻断整张卡片）。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from pathlib import Path

from dna_builder_sdk import DataPackStore  # noqa: F401 （重导出，供调用方取数）
from dna_builder_sdk.calc import Engine, build_state

from . import tables as _tables_mod

if TYPE_CHECKING:
    from ..utils.api.model import RoleDetail, WeaponDetail

__all__ = [
    "SdkBuildError",
    "SdkBuild",
    "build_engine",
    "skill_base_levels",
    "TRACE_BONUS_RE",
]


class SdkBuildError(RuntimeError):
    """装配失败（角色/武器未收录时抛；调用方转用户提示）。"""


# 溯源文案里的技能等级加成，形如「[残光]等级+2」
TRACE_BONUS_RE = re.compile(r"\[([^\]]+)]\s*等级\s*\+\s*(\d+)")


def skill_base_levels(role: RoleDetail) -> list[int]:
    """官方 skills 的基础等级（扣掉前 gradeLevel 条溯源的加成），下标与 role.skills 一致。"""
    bonus: dict[str, int] = {}
    for trace in role.traces[: role.gradeLevel]:
        for name, text in TRACE_BONUS_RE.findall(trace.description):
            bonus[name] = bonus.get(name, 0) + int(text)
    return [max(1, skill.level - bonus.get(skill.skillName, 0)) for skill in role.skills]


def _mode_pairs(modes, tbl) -> list:
    out = []
    for mode in modes or []:
        if mode is None or mode.id is None or mode.id <= 0:
            continue
        if tbl.mod_record(mode.id) is None:
            continue
        out.append([int(mode.id), int(mode.level or 0)])
    return out


def _unknown_mod_ids(*groups, tbl) -> list[int]:
    out = []
    for modes in groups:
        for mode in modes or []:
            if mode is None or mode.id is None or mode.id <= 0:
                continue
            if tbl.mod_record(mode.id) is None:
                out.append(int(mode.id))
    return out


class SdkBuild:
    """一次装配：Engine + 官方输入回放（武器详情按槽位）。"""

    def __init__(
        self,
        engine: Engine,
        role: RoleDetail,
        weapons: dict[str, Any],
        missing_mods: list[int],
    ) -> None:
        self.engine = engine
        self.role = role
        self.weapons = weapons
        self.missing_mods = missing_mods

    @property
    def attrs(self) -> dict:
        """角色属性（引擎全量结算；充盈溢出的武器集合修正见 local_attribute）。"""
        return self.engine.calculate_attributes()


def build_engine(
    role: RoleDetail,
    close_weapon: WeaponDetail | None = None,
    ranged_weapon: WeaponDetail | None = None,
    con_weapon: WeaponDetail | None = None,
    sdk_cache: str | Path | None = None,
) -> SdkBuild:
    """官方详情 → Engine。sdk_cache 指定数据包缓存目录（e2e 注入最小包；缺省走全局）。"""
    tbl = _tables_mod
    if sdk_cache is not None:
        _tables_mod.use_cache_dir(sdk_cache)
    tbl.get_tables()
    entry = tbl.char_record(role.charId)
    if entry is None:
        raise SdkBuildError(f"角色 {role.charName}（id={role.charId}）未在数据包收录")
    try:
        char_id = int(entry.get("id"))
    except (TypeError, ValueError):
        raise SdkBuildError(f"角色 {role.charName} 的数据包 id 非法")

    role_modes = list(role.modes or [])
    center = role_modes[-1] if len(role_modes) > 8 else None
    if center is not None and (center.id is None or center.id <= 0):
        center = None
    char_slots = role_modes[:8]
    missing = _unknown_mod_ids(
        role_modes,
        close_weapon.modes if close_weapon else [],
        ranged_weapon.modes if ranged_weapon else [],
        con_weapon.modes if con_weapon else [],
        tbl=tbl,
    )
    missing_weapons: list[str] = []

    def weapon_setting(weapon: WeaponDetail | None, prefix: str) -> dict:
        if weapon is None:
            return {}
        if tbl.weapon_record(weapon.id) is None and tbl.con_weapon_record(role.charId, weapon.id) is None:
            # 未收录武器：槽位按空武器占位（面板/伤害显示“无法计算”），卡片不阻断
            missing_weapons.append(f"{weapon.name}（id={weapon.id}）")
            return {prefix: 0}
        return {
            prefix: int(weapon.id),
            f"{prefix}Refine": weapon.skillLevel,
            f"{prefix}Level": weapon.level,
        }

    settings: dict[str, Any] = {
        "charLevel": role.level or 80,
        "charMods": _mode_pairs(char_slots, tbl),
        "meleeMods": _mode_pairs(close_weapon.modes if close_weapon else [], tbl),
        "rangedMods": _mode_pairs(ranged_weapon.modes if ranged_weapon else [], tbl),
    }
    if center is not None and center.id:
        if tbl.mod_record(center.id) is None:
            missing.append(int(center.id))
            center = None
        else:
            settings["auraMod"] = int(center.id)
    settings.update(weapon_setting(close_weapon, "meleeWeapon"))
    settings.update(weapon_setting(ranged_weapon, "rangedWeapon"))

    base_levels = skill_base_levels(role)[:3]
    traces = max(0, min(7, int(role.gradeLevel or 0)))
    try:
        state = build_state(char_id, settings, tbl.get_tables(), skill_levels=base_levels, traces=traces)
    except KeyError as error:
        raise SdkBuildError(f"装配失败：{error}") from error
    engine = Engine(state, tbl.get_tables())
    if missing_weapons:
        missing.extend([w for w in missing_weapons if w not in missing])
    return SdkBuild(
        engine,
        role,
        {"close": close_weapon, "ranged": ranged_weapon, "con": con_weapon},
        missing,
    )
