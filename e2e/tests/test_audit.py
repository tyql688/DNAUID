"""mock 依赖覆盖审计（pytest 版）：静态扫描插件全部 gsuid_core 引用。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from e2e.mock_host import install  # noqa: E402
from e2e.mock_host.audit import run_audit  # noqa: E402

install()


def test_audit_no_errors():
    report = run_audit()
    assert not report["errors"], "mock 宿主有未覆盖的依赖:\n" + "\n".join(
        f"[{g['kind']}] {g.get('module', '')} {g.get('name')} :: {g.get('hint')}" for g in report["errors"]
    )
