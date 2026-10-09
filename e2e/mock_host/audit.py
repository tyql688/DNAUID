"""mock 宿主依赖覆盖审计：静态扫描插件全部 gsuid_core 引用，逐个验证可解析。

用法：``uv run --group e2e e2e/mock_host/audit.py``（返回非 0 表示有缺口）
pytest：``e2e/tests/test_audit.py`` 调用同一入口。
"""

from __future__ import annotations

import ast
import sys
import importlib
from typing import Any
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN_DIR = ROOT / "DNAUID"


def _iter_plugin_files() -> list[Path]:
    files = sorted(PLUGIN_DIR.rglob("*.py"))
    real_dir = ROOT / "e2e" / "mock_host" / "_real"
    if real_dir.exists():
        files += sorted(real_dir.rglob("*.py"))
    return files


def collect_gsuid_imports() -> list[tuple[str, str, int]]:
    """收集 (模块, 导入原名, 行号)。别名不影响 import 成败，只核验原名。"""
    out: list[tuple[str, str, int]] = []
    for file in _iter_plugin_files():
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("gsuid_core"):
                for alias in node.names:
                    out.append((node.module, alias.name, node.lineno))
    return out


def collect_attr_usage() -> dict[str, set[str]]:
    """收集 logger./bot./ev./MessageSegment./gs_subscribe./scheduler. 的属性使用。"""
    targets = ("logger", "bot", "ev", "MessageSegment", "gs_subscribe", "scheduler", "site", "gss")
    found: dict[str, set[str]] = {t: set() for t in targets}
    for file in _iter_plugin_files():
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id in found:
                    found[node.value.id].add(node.attr)
    return out_sorted(found)


def out_sorted(found: dict[str, set[str]]) -> dict[str, set[str]]:
    return found


def check_imports() -> list[dict[str, Any]]:
    from e2e.mock_host import stubs  # noqa: PLC0415

    stubs.install()
    gaps: list[dict[str, Any]] = []
    for module, name, lineno in collect_gsuid_imports():
        try:
            mod = importlib.import_module(module)
            target = getattr(mod, name)
            if isinstance(target, stubs.Dummy):
                gaps.append(
                    {
                        "kind": "dummy",
                        "module": module,
                        "name": name,
                        "lineno": lineno,
                        "hint": "命中通用 Dummy，无真实行为",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            gaps.append(
                {"kind": "import-error", "module": module, "name": name, "lineno": lineno, "hint": repr(exc)[:200]}
            )
    return gaps


def check_attrs() -> list[dict[str, Any]]:
    from e2e.mock_host import MockBot, MessageSegment  # noqa: PLC0415
    from e2e.mock_host.event import MockEvent  # noqa: PLC0415
    from e2e.mock_host.stubs import Dummy, logger, gs_subscribe  # noqa: PLC0415

    gaps: list[dict[str, Any]] = []
    usage = collect_attr_usage()

    for attr in usage["logger"]:
        if isinstance(getattr(logger, attr, None), Dummy):
            gaps.append({"kind": "logger", "name": attr, "hint": "Dummy 方法"})
    for attr in usage["bot"]:
        if not callable(getattr(MockBot, attr, None)):
            gaps.append({"kind": "bot", "name": attr, "hint": "MockBot 缺方法"})
    fields = set(MockEvent.__dataclass_fields__)
    for attr in usage["ev"]:
        if attr not in fields:
            gaps.append({"kind": "event", "name": attr, "hint": "MockEvent 缺字段"})
    for attr in usage["MessageSegment"]:
        if not callable(getattr(MessageSegment, attr, None)):
            gaps.append({"kind": "segment", "name": attr, "hint": "MessageSegment 缺构造器"})
    for attr in usage["gs_subscribe"]:
        if not callable(getattr(gs_subscribe, attr, None)):
            gaps.append({"kind": "subscribe", "name": attr, "hint": "gs_subscribe 缺方法"})
    return gaps


def run_audit() -> dict[str, Any]:
    import_gaps = check_imports()
    attr_gaps = check_attrs()
    # Dummy 命中不全是问题：类型注解/未执行分支允许；但列出来让人 eyeball
    dummies = [g for g in import_gaps if g["kind"] == "dummy"]
    errors = [g for g in import_gaps if g["kind"] != "dummy"] + attr_gaps
    return {"errors": errors, "dummies": dummies, "summary": f"{len(errors)} errors, {len(dummies)} dummy-hits"}


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    report = run_audit()
    print("== ERRORS ==")
    for gap in report["errors"]:
        print(f"[{gap['kind']}] {gap.get('module', '')} {gap.get('name')} :: {gap.get('hint')}")
    print(f"== {report['summary']} ==")
    print(f"(dummy-hits: {len(report['dummies'])} 处，仅提示不计错)")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
