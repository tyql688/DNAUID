"""结算 parity e2e：官方详情 → dobsdk 引擎 → 面板/伤害，三合成案钉住期望输出。

数据源为仓内最小包（e2e/fixtures/settlement/datapack.min.zip，仅 30KB，
覆盖用例实际消费的记录），全离线、无网络。期望输出钉的是与 dna-builder
网页版逐项对账过的当前口径（共振+3/武器槽按类型入表/武器Buff池/数据包基值…），
改口径请同步更新 expected.json。
"""

from __future__ import annotations

import sys
import json
import math
import types
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIX = ROOT / "e2e" / "fixtures" / "settlement"

# ---- 仓根有创仓遗留的 __init__.py：pytest 按包收集时会把仓根本身认成
# ---- `DNAUID` 包（真正的代码包在 仓根/DNAUID/），这里把包搜索路径修过去 ----
import DNAUID as _root_pkg  # noqa: E402

_anchor = Path(getattr(_root_pkg, "__file__", "") or "")
if _anchor.parent != ROOT / "DNAUID":
    _root_pkg.__path__ = [str(ROOT / "DNAUID")]
if "gsuid_core" not in sys.modules:
    _gsuid = types.ModuleType("gsuid_core")
    _gsuid.__path__ = []
    sys.modules["gsuid_core"] = _gsuid
if "gsuid_core.logger" not in sys.modules:
    _mod = types.ModuleType("gsuid_core.logger")

    class _Log:
        def debug(self, *a, **k):
            pass

        def info(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

        def success(self, *a, **k):
            pass

    _mod.logger = _Log()
    sys.modules["gsuid_core.logger"] = _mod
if "gsuid_core.sv" not in sys.modules:
    _sv = types.ModuleType("gsuid_core.sv")

    class _Plugins:
        def __init__(self, *a, **k):
            pass

    _sv.Plugins = _Plugins
    sys.modules["gsuid_core.sv"] = _sv


def _stub_pkg(name: str, path: Path) -> None:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.__path__ = [str(path)]
        sys.modules[name] = mod


_stub_pkg("DNAUID.dna_detail", ROOT / "DNAUID" / "dna_detail")
_stub_pkg("DNAUID.utils.resource", ROOT / "DNAUID" / "utils" / "resource")
_res = types.ModuleType("DNAUID.utils.resource.RESOURCE_PATH")
_res.DOB_PATH = FIX
sys.modules["DNAUID.utils.resource.RESOURCE_PATH"] = _res

from DNAUID.dna_sdk import tables as T  # noqa: E402
from DNAUID.dna_detail import (  # noqa: E402
    local_damage as LD,  # noqa: E402
    local_attribute as LA,  # noqa: E402
    local_weapon_damage as LWD,  # noqa: E402
    local_weapon_attribute as LWA,  # noqa: E402
)
from DNAUID.dna_sdk.build import build_engine  # noqa: E402
from DNAUID.utils.api.model import Mode, RoleDetail, WeaponDetail  # noqa: E402

CHAR_ID = 1501
CHAR_MODS = [[51463, 10], [51326, 10], [51768, 10], [51768, 10], [56162, 10], [31203, 10], [51768, 10], [51768, 10]]
AURA = 51765
MELEE_MODS = [[52011, 10], [52007, 10], [42002, 10], [42003, 10], [52010, 10], [52008, 10], [42006, 10], [52203, 10]]
RANGED_MODS = [[53011, 10], [53111, 10], [53008, 10], [43006, 10], None, [33332, 10], [53801, 10], None]
SKILL_MODS = [[54003, 10], [54002, 10], [54004, 10], [54204, 10]]
NAMES = ["以坚忍之名", "我不忍啦！", "哼！！"]
T0 = "释放[以坚忍之名]时，自身获得攻击提高35%，持续15秒。"
T1 = "造成的伤害触发额外效果时，额外获得1点连击点数。"
T2 = "[以坚忍之名]等级+2，[哼！！]等级+1。"

EXPECTED = json.loads((FIX / "expected.json").read_text(encoding="utf-8"))


def _mode_of(pair):
    return None if not pair else Mode(id=int(pair[0]), level=int(pair[1]))


def _modes_of(slots):
    return [m for m in (_mode_of(e) for e in slots) if m]


def _base_role(**kw):
    args = dict(
        attribute=dict(
            atk=1500,
            maxHp=30000,
            maxES=0,
            **{"def": 500},
            maxSp=100,
            weaponTags=[],
            skillIntensity="350%",
            skillRange="100%",
            skillSustain="100%",
            skillEfficiency="100%",
            skillRecharge="100%",
            strongValue="0%",
            enmityValue="0%",
        ),
        skills=[],
        paint="p",
        charId=CHAR_ID,
        charName="莉兹贝尔",
        elementIcon="e",
        traces=[],
        currentVolume=9,
        sumVolume=9,
        level=80,
        icon="i",
        gradeLevel=0,
        elementName="光",
        modes=[],
        conWeaponEid=None,
        conWeaponId=None,
    )
    args.update(kw)
    return RoleDetail(**args)


def _skill(name, level, idx):
    return dict(skillId=1000 + idx, icon="s", level=level, skillName=name)


def _weapon(wid, refine, wlevel, modes, atk):
    return WeaponDetail(
        attribute=dict(atk=atk, crd=2.0, cri=0.2, speed=1.0, trigger=0.25),
        currentVolume=8,
        sumVolume=8,
        elementIcon=None,
        elementName=None,
        icon="w",
        id=wid,
        level=wlevel,
        modes=modes,
        name=f"W{wid}",
        skillLevel=refine,
    )


_MELEE = _weapon(10399, 5, 80, _modes_of(MELEE_MODS), atk=500)
_RANGED = _weapon(20510, 5, 80, _modes_of(RANGED_MODS), atk=400)
_MODES_A = _modes_of(CHAR_MODS) + [Mode(id=AURA, level=10)]

CASES = {
    "A_full12": (
        _base_role(skills=[_skill(n, 12, i) for i, n in enumerate(NAMES)], modes=_MODES_A),
        [_MELEE, _RANGED, None],
    ),
    "B_lowskill_trace3": (
        _base_role(
            skills=[_skill(n, lv, i) for i, (n, lv) in enumerate(zip(NAMES, [7, 9, 12]))],
            traces=[{"icon": "t", "description": t} for t in (T0, T1, T2)],
            gradeLevel=3,
            modes=_MODES_A,
        ),
        [_MELEE, _RANGED, None],
    ),
    "C_conweapon": (
        _base_role(
            skills=[_skill(n, 12, i) for i, n in enumerate(NAMES)], modes=_MODES_A, conWeaponEid="e", conWeaponId=150101
        ),
        [_MELEE, _RANGED, _weapon(150101, 5, 80, _modes_of(SKILL_MODS), atk=300)],
    ),
}


def _run_case(name):
    role, weapons = CASES[name]
    close, ranged, con = weapons
    tmp = Path(tempfile.mkdtemp(prefix="dob-e2e-"))
    try:
        staged = tmp / "1.6.208.6"
        staged.mkdir()
        shutil.copy(FIX / "datapack.min.zip", staged / "package.zip")
        T.use_cache_dir(tmp)
        build = build_engine(role, close, ranged, con, sdk_cache=tmp)
        ctx = LA.compute_attr_context(build)
        final = LA.compute_final_attribute(build, ctx)
        out = {"final_rows": final.rows, "final_hidden": final.hidden_rows, "weapons": {}, "skills": []}
        inherit_slot = None
        if con is not None:
            inherit_detail = LWA.resolve_inherit_source(con, role, close, ranged)
            if inherit_detail is close:
                inherit_slot = "close"
            elif inherit_detail is ranged:
                inherit_slot = "ranged"
        for label, slot, isl in (("close", "close", None), ("ranged", "ranged", None), ("con", "con", inherit_slot)):
            wd = {"close": close, "ranged": ranged, "con": con}[label]
            if wd is None:
                continue
            rows = LWA.compute_weapon_attribute(build, wd, slot, isl)
            dmg = LWD.compute_weapon_damage(build, slot, ctx, isl)
            out["weapons"][label] = {"rows": rows.rows, "final_atk": rows.final_atk, "damage": dmg}
        for p in LD.build_local_skill_panels(build, ctx):
            out["skills"].append({"名称": p.名称, "显示等级": p.显示等级, "rows": p.rows})
        return out
    finally:
        T.use_cache_dir(None)


def _rows(rows):
    return [list(r) for r in rows]


def _check_case(name):
    want = EXPECTED[name]
    got = _run_case(name)
    assert _rows(got["final_rows"]) == want["final_rows"], f"{name} 属性行漂移"
    assert _rows(got["final_hidden"]) == want["final_hidden"], f"{name} 隐藏属性漂移"
    assert set(got["weapons"]) == set(want["weapons"]), f"{name} 武器槽位漂移"
    for label, w in want["weapons"].items():
        g = got["weapons"][label]
        assert _rows(g["rows"]) == w["rows"], f"{name}/{label} 武器行漂移"
        assert math.isclose(g["final_atk"], w["final_atk"], rel_tol=1e-9), f"{name}/{label} 终伤攻击漂移"
        assert (g["damage"] is None) == (w["damage"] is None), f"{name}/{label} 伤害空值漂移"
        if w["damage"] is not None:
            assert math.isclose(g["damage"], w["damage"], rel_tol=1e-9), f"{name}/{label} 伤害漂移"
    assert [(s["名称"], s["显示等级"], _rows(s["rows"])) for s in got["skills"]] == [
        (s["名称"], s["显示等级"], s["rows"]) for s in want["skills"]
    ], f"{name} 技能面板漂移"


def test_settlement_full12():
    _check_case("A_full12")


def test_settlement_lowskill_trace3():
    _check_case("B_lowskill_trace3")


def test_settlement_conweapon():
    _check_case("C_conweapon")
