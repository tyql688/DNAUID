from __future__ import annotations

from enum import StrEnum
from dataclasses import dataclass

from ..utils.api.model import WeaponInsForTool
from ..utils.name_convert import alias_to_weapon_name


class WeaponSlot(StrEnum):
    CLOSE = "近战"
    RANGED = "远程"


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectedWeapon:
    slot: WeaponSlot
    name: str
    weapon_id: int
    weapon_eid: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WeaponLoadout:
    close_weapon: SelectedWeapon | None = None
    ranged_weapon: SelectedWeapon | None = None


class WeaponSelectionError(ValueError):
    pass


class WeaponNotFoundError(WeaponSelectionError):
    weapon_name: str

    def __init__(self, weapon_name: str):
        self.weapon_name = weapon_name
        super().__init__(f"展柜武器【{weapon_name}】未找到")


class WeaponNotUnlockedError(WeaponSelectionError):
    weapon_name: str

    def __init__(self, weapon_name: str):
        self.weapon_name = weapon_name
        super().__init__(f"当前展柜武器【{weapon_name}】暂未拥有")


class WeaponSlotConflictError(WeaponSelectionError):
    slot: WeaponSlot

    def __init__(self, slot: WeaponSlot):
        self.slot = slot
        super().__init__(f"不能同时携带两把{slot.value}武器")


def _find_weapon(
    weapons: list[WeaponInsForTool],
    weapon_name: str,
) -> WeaponInsForTool | None:
    return next(
        (weapon for weapon in weapons if weapon.name == weapon_name),
        None,
    )


def _select_weapon(
    close_weapons: list[WeaponInsForTool],
    ranged_weapons: list[WeaponInsForTool],
    input_name: str,
) -> SelectedWeapon:
    weapon_name = alias_to_weapon_name(input_name)
    weapon = _find_weapon(close_weapons, weapon_name)
    slot = WeaponSlot.CLOSE
    if weapon is None:
        weapon = _find_weapon(ranged_weapons, weapon_name)
        slot = WeaponSlot.RANGED
    if weapon is None:
        raise WeaponNotFoundError(input_name)
    if not weapon.unLocked:
        raise WeaponNotUnlockedError(weapon.name)
    if weapon.weaponEid is None:
        raise RuntimeError(f"已解锁武器【{weapon.name}】缺少 weaponEid")
    return SelectedWeapon(
        slot=slot,
        name=weapon.name,
        weapon_id=weapon.weaponId,
        weapon_eid=weapon.weaponEid,
    )


def resolve_weapon_loadout(
    close_weapons: list[WeaponInsForTool],
    ranged_weapons: list[WeaponInsForTool],
    weapon_names: tuple[str, ...],
) -> WeaponLoadout:
    if len(weapon_names) > 2:
        raise ValueError("角色面板最多携带一把近战武器和一把远程武器")

    close_weapon: SelectedWeapon | None = None
    ranged_weapon: SelectedWeapon | None = None
    for weapon_name in weapon_names:
        selected = _select_weapon(
            close_weapons,
            ranged_weapons,
            weapon_name,
        )
        if selected.slot is WeaponSlot.CLOSE:
            if close_weapon is not None:
                raise WeaponSlotConflictError(WeaponSlot.CLOSE)
            close_weapon = selected
        else:
            if ranged_weapon is not None:
                raise WeaponSlotConflictError(WeaponSlot.RANGED)
            ranged_weapon = selected

    return WeaponLoadout(
        close_weapon=close_weapon,
        ranged_weapon=ranged_weapon,
    )
