from __future__ import annotations

import sys
import json
import math
import types
import asyncio
import logging
from pathlib import Path
from collections.abc import Sequence

import httpx
import pytest
from pydantic import JsonValue, TypeAdapter

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
if "gsuid_core.bot" not in sys.modules:
    _stub_module("DNAUID.utils.resource.RESOURCE_PATH", DOB_PATH=FIX)
    _stub_module("DNAUID.dna_dob", __path__=[str(ROOT / "DNAUID" / "dna_dob")])
    _stub_module("DNAUID.utils.name_convert", id2name_data={})

from dna_builder_sdk import DataPackStore  # noqa: E402

from DNAUID.dna_dob import service  # noqa: E402
from DNAUID.utils.dob import pack  # noqa: E402
from DNAUID.utils.api.model import Mode, RoleSkill, RoleTrace, RoleDetail, WeaponDetail, RoleAttribute  # noqa: E402
from DNAUID.utils.dob.build import WeaponSlot  # noqa: E402
from DNAUID.utils.dob.panel import settle_role  # noqa: E402
from DNAUID.utils.dob.engine import DobBuildError  # noqa: E402

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
    view = asyncio.run(settle_role(role, weapons))
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


def _serve_build(monkeypatch: pytest.MonkeyPatch, *settings: dict[str, JsonValue]) -> None:
    builds = [
        {
            "id": f"sdk040-{index}" if index else "sdk040",
            "title": "莉兹贝尔构筑",
            "charId": 1501,
            "charSettings": json.dumps(value),
            "updateAt": 0,
            "likes": 1,
            "views": 2,
            "user": {"name": "tester", "qq": ""},
        }
        for index, value in enumerate(settings)
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "build": builds[0],
                    "builds": builds,
                    "rankingLists": [{"name": "测试榜", "items": [{"build": build} for build in builds]}],
                }
            },
        )

    real_client = httpx.AsyncClient

    def client(*, timeout: float) -> httpx.AsyncClient:
        return real_client(timeout=timeout, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(service.httpx, "AsyncClient", client)


@pytest.mark.parametrize("variant", ["legacy", "selected", "unused_null", "selected_null", "null_fields"])
def test_dob_build_and_board(monkeypatch: pytest.MonkeyPatch, variant: str) -> None:
    settings = TypeAdapter(dict[str, JsonValue]).validate_python(
        {
            "charLevel": 80,
            "charSkillLevel": [12, 12, 12],
            "meleeWeapon": 10399,
            "rangedWeapon": 20510,
            "targetFunction": "角色::攻击!",
            "charMods": [] if variant in ("selected", "null_fields") else CHAR_MODS,
            "meleeMods": MELEE_MODS,
            "rangedMods": RANGED_MODS,
            "auraMod": AURA[0],
            "modVariantIndex": 1 if variant in ("selected", "null_fields") else 0,
            "modVariants": [{"角色": CHAR_MODS, "近战": MELEE_MODS, "远程": RANGED_MODS}],
        }
    )
    if variant in ("unused_null", "selected_null"):
        settings["modVariants"] = [None, None]
        settings["modVariantIndex"] = 1 if variant == "selected_null" else 0
    elif variant == "null_fields":
        settings["charLevel"] = None
        settings["meleeWeaponLevel"] = None
        settings["rangedWeaponRefine"] = None
        settings["modVariants"] = TypeAdapter(list[JsonValue]).validate_python(
            [{"角色": CHAR_MODS, "近战": MELEE_MODS, "远程": RANGED_MODS, "同律": None, "中枢": None}]
        )
    _serve_build(monkeypatch, settings)
    card = asyncio.run(service.synthesize_build("sdk040"))
    assert card is not None
    assert (card.role.charName, card.role.level) == ("莉兹贝尔", 80)
    assert [mode.id for mode in card.role.modes] == [
        51463,
        51768,
        51326,
        51768,
        31203,
        51768,
        56162,
        51768,
        51765,
    ]
    assert card.panel.weapons[WeaponSlot.MELEE].detail.id == 10399
    assert card.panel.weapons[WeaponSlot.RANGED].detail.id == 20510
    assert (card.target_fn, card.target_value) == ("角色::攻击!", "6158")
    view = card.panel
    want = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))["A_full12"]
    assert [list(row) for row in view.attr_rows] == want["attr_rows"]
    boards = asyncio.run(service.fetch_boards())
    assert len(boards) == 1
    assert [(row.bdid, row.score) for row in boards[0].rows] == [
        ("sdk040", service.BuildScore(target_fn="角色::攻击!", dps=6158))
    ]


def test_dob_invalid_weapon_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve_build(monkeypatch, {"meleeWeapon": 999999, "rangedWeapon": 0, "auraMod": 0})
    with pytest.raises(DobBuildError):
        asyncio.run(service.synthesize_build("sdk040"))


@pytest.mark.parametrize("slots", [{}, {"角色": None, "近战": None, "远程": None, "同律": None}])
def test_dob_empty_variant_keeps_empty_slots(monkeypatch: pytest.MonkeyPatch, slots: dict[str, JsonValue]) -> None:
    _serve_build(
        monkeypatch,
        TypeAdapter(dict[str, JsonValue]).validate_python(
            {
                "charMods": CHAR_MODS,
                "meleeWeapon": 10399,
                "rangedWeapon": 20510,
                "auraMod": 51765,
                "modVariants": [slots],
                "modVariantIndex": 1,
                "targetFunction": "角色::攻击!",
            }
        ),
    )
    card = asyncio.run(service.synthesize_build("sdk040"))
    assert card is not None
    assert [mode.id for mode in card.role.modes] == [-1] * 8 + [51765]
    assert card.target_value == "2575"
    assert ("光属性攻击", "2,575.7") in card.panel.attr_rows


def test_failed_calculation_has_no_dps_rank(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve_build(
        monkeypatch,
        {"meleeWeapon": 999999, "rangedWeapon": 0, "auraMod": 0},
        {"meleeWeapon": 0, "rangedWeapon": 0, "auraMod": 0, "targetFunction": "0"},
        {"meleeWeapon": 0, "rangedWeapon": 0, "auraMod": 0, "targetFunction": "10"},
        {"meleeWeapon": 0, "rangedWeapon": 0, "auraMod": 0, "targetFunction": "-1"},
    )
    rows = asyncio.run(service.fetch_boards())[0].rows
    assert [(row.bdid, row.rank) for row in rows] == [
        ("sdk040-2", 1),
        ("sdk040-1", 2),
        ("sdk040-3", 3),
        ("sdk040", None),
    ]
    assert rows[1].score == service.BuildScore(target_fn="0", dps=0)
    assert isinstance(rows[-1].score, service.BuildFailure)
    assert rows[-1].score.reason
    choices = asyncio.run(service.fetch_char_builds(1501))
    assert [(row.bdid, row.rank) for row in choices] == [
        ("sdk040", 1),
        ("sdk040-1", 2),
        ("sdk040-2", 3),
        ("sdk040-3", 4),
    ]


def test_role_without_equipment_has_no_default_mods() -> None:
    role = _role([12, 12, 12]).model_copy(update={"modes": []})
    view = asyncio.run(settle_role(role, {}))
    assert view.weapons == {}
    assert ("技能威力", "100%") in view.attr_rows


# 改结算口径后重新生成期望：python e2e/tests/test_settlement.py --update，再逐项核对 diff
if __name__ == "__main__" and "--update" in sys.argv:
    use_fixture_pack()
    EXPECTED_PATH.write_text(
        json.dumps({name: run_case(name) for name in sorted(CASES)}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
