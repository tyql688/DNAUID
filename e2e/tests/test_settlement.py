from __future__ import annotations

import sys
import json
import math
import types
import logging
from pathlib import Path
from collections.abc import Sequence

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "e2e" / "fixtures" / "settlement"
EXPECTED_PATH = FIX / "expected.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _stub_module(name: str, **attrs: object) -> None:
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module


# CI 只装插件依赖、没有宿主：补最小桩；mock 宿主已装时沿用宿主的
_stub_module("gsuid_core", __path__=[])
_stub_module("gsuid_core.logger", logger=logging.getLogger("dnauid-settlement"))
_stub_module("gsuid_core.sv", Plugins=lambda **_kwargs: None)
_stub_module("DNAUID.utils.resource.RESOURCE_PATH", DOB_PATH=FIX)

from dna_builder_sdk import DataPackStore  # noqa: E402

from DNAUID.utils.dob import pack  # noqa: E402
from DNAUID.utils.api.model import Mode, RoleSkill, RoleTrace, RoleDetail, WeaponDetail, RoleAttribute  # noqa: E402
from DNAUID.utils.dob.build import WeaponSlot, build_engine  # noqa: E402
from DNAUID.utils.dob.panel import compute_panel  # noqa: E402

CHAR_MODS = [[51463, 10], [51326, 10], [51768, 10], [51768, 10], [56162, 10], [31203, 10], [51768, 10], [51768, 10]]
AURA = [51765, 10]
MELEE_MODS = [[52011, 10], [52007, 10], [42002, 10], [42003, 10], [52010, 10], [52008, 10], [42006, 10], [52203, 10]]
RANGED_MODS = [[53011, 10], [53111, 10], [53008, 10], [43006, 10], None, [33332, 10], [53801, 10], None]
SKILL_MODS = [[54003, 10], [54002, 10], [54004, 10], [54204, 10]]
SKILL_NAMES = ["以坚忍之名", "我不忍啦！", "哼！！"]
TRACES = [
    "释放[以坚忍之名]时，自身获得攻击提高35%，持续15秒。",
    "造成的伤害触发额外效果时，额外获得1点连击点数。",
    "[以坚忍之名]等级+2，[哼！！]等级+1。",
]


def _modes(slots: Sequence[list[int] | None]) -> list[Mode]:
    return [Mode(id=slot[0], level=slot[1]) for slot in slots if slot]


def _role(skill_levels: list[int], grade_level: int = 0, con_weapon_id: int | None = None) -> RoleDetail:
    return RoleDetail(
        attribute=RoleAttribute.model_validate(
            {
                "atk": 1500,
                "maxHp": 30000,
                "maxES": 0,
                "def": 500,
                "maxSp": 100,
                "weaponTags": [],
                "skillIntensity": "350%",
                "skillRange": "100%",
                "skillSustain": "100%",
                "skillEfficiency": "100%",
                "skillRecharge": "100%",
                "strongValue": "0%",
                "enmityValue": "0%",
            }
        ),
        skills=[
            RoleSkill(skillId=1000 + i, icon="s", level=level, skillName=name)
            for i, (name, level) in enumerate(zip(SKILL_NAMES, skill_levels))
        ],
        paint="p",
        charId=1501,
        charName="莉兹贝尔",
        elementIcon="e",
        traces=[RoleTrace(icon="t", description=text) for text in TRACES[:grade_level]],
        currentVolume=9,
        sumVolume=9,
        level=80,
        icon="i",
        gradeLevel=grade_level,
        elementName="光",
        modes=_modes(CHAR_MODS + [AURA]),
        conWeaponEid="e" if con_weapon_id else None,
        conWeaponId=con_weapon_id,
    )


def _weapon(weapon_id: int, modes: Sequence[list[int] | None], atk: int) -> WeaponDetail:
    return WeaponDetail.model_validate(
        {
            "attribute": {"atk": atk, "crd": 2.0, "cri": 0.2, "speed": 1.0, "trigger": 0.25},
            "currentVolume": 8,
            "sumVolume": 8,
            "icon": "w",
            "id": weapon_id,
            "level": 80,
            "modes": [mode.model_dump() for mode in _modes(modes)],
            "name": f"W{weapon_id}",
            "skillLevel": 5,
        }
    )


_MELEE = _weapon(10399, MELEE_MODS, atk=500)
_RANGED = _weapon(20510, RANGED_MODS, atk=400)
CASES: dict[str, tuple[RoleDetail, dict[WeaponSlot, WeaponDetail]]] = {
    "A_full12": (_role([12, 12, 12]), {WeaponSlot.MELEE: _MELEE, WeaponSlot.RANGED: _RANGED}),
    "B_lowskill_trace3": (_role([7, 9, 12], grade_level=3), {WeaponSlot.MELEE: _MELEE, WeaponSlot.RANGED: _RANGED}),
    "C_conweapon": (
        _role([12, 12, 12], con_weapon_id=150101),
        {
            WeaponSlot.MELEE: _MELEE,
            WeaponSlot.RANGED: _RANGED,
            WeaponSlot.SKILL: _weapon(150101, SKILL_MODS, atk=300),
        },
    ),
}


def use_fixture_pack() -> None:
    pack._store = DataPackStore(cache_dir=str(FIX))
    pack._tables = None
    assert pack._load_local()


def run_case(name: str) -> dict:
    role, weapons = CASES[name]
    view = compute_panel(build_engine(role, weapons))
    result = {
        "attr_rows": view.attr_rows,
        "hidden_rows": view.hidden_rows,
        "compare_rows": view.compare_rows,
        "weapons": {slot.value: {"rows": w.rows, "damage": w.damage} for slot, w in view.weapons.items()},
        "skills": [{"name": s.name, "level": s.level, "rows": s.rows} for s in view.skills],
    }
    return json.loads(json.dumps(result, ensure_ascii=False))


@pytest.fixture(autouse=True)
def _fixture_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pack, "_store", DataPackStore(cache_dir=str(FIX)))
    monkeypatch.setattr(pack, "_tables", None)
    assert pack._load_local()


@pytest.mark.parametrize("name", sorted(CASES))
def test_settlement(name: str) -> None:
    want = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))[name]
    got = run_case(name)
    for slot, weapon in want["weapons"].items():
        damage = got["weapons"][slot].pop("damage")
        assert (damage is None) == (weapon["damage"] is None), f"{name}/{slot} 伤害空值漂移"
        if damage is not None:
            assert math.isclose(damage, weapon["damage"], rel_tol=1e-9), f"{name}/{slot} 伤害漂移"
        weapon.pop("damage")
    assert got == want


# 改结算口径后重新生成期望：python e2e/tests/test_settlement.py --update，再逐项核对 diff
if __name__ == "__main__" and "--update" in sys.argv:
    use_fixture_pack()
    EXPECTED_PATH.write_text(
        json.dumps({name: run_case(name) for name in sorted(CASES)}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
