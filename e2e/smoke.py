"""无 pytest 环境下的冒烟 runner（仅标准库）。

用法：``python e2e/smoke.py``
汇总执行 tests/ 下各用例函数的断言。
"""

from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import e2e.tests.test_dispatcher as t_dispatch  # noqa: E402
import e2e.tests.test_segments as t_segments  # noqa: E402
import e2e.tests.test_web_api as t_web  # noqa: E402


def main() -> int:
    cases = [
        (name, fn)
        for mod in (t_segments, t_dispatch, t_web)
        for name, fn in sorted(vars(mod).items())
        if name.startswith("test_") and callable(fn)
    ]
    passed, failed = 0, []
    for name, fn in cases:
        try:
            fn()
            passed += 1
            print(f"PASS {name}")
        except Exception:  # noqa: BLE001
            failed.append(name)
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{passed} passed, {len(failed)} failed (共 {len(cases)} 个)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
