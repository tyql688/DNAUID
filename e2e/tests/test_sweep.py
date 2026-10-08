"""全指令动态横扫（pytest 版）：每个触发器真实分发，ok=False 即缺口。

较慢（约 1 分钟），属 e2e 慢测试；CI 应运行。
"""

import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from e2e.mock_host.sweep import run_sweep  # noqa: E402


def test_sweep_no_failures():
    report = asyncio.run(run_sweep())
    failures = report["failures"]
    assert not failures, f"{len(report['cases'])} 例中 {len(failures)} 个失败:\n" + "\n".join(
        f"[{r['sv']}] {r['text']} :: {r['error']}" for r in failures[:20]
    )
    assert not [r for r in report["cases"] if not r["matched"]], "存在未命中路由的用例"
