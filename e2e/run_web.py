"""e2e 启动入口：``uv run --group e2e e2e/run_web.py [--host] [--port] [--watch]``。"""

from __future__ import annotations

import os
import sys
import signal
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CHILD_ENV = "DNAUID_E2E_WATCH_CHILD"
_WATCH_DIRS = ("DNAUID", "e2e")


def _spawn(root: str, host: str, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env[_CHILD_ENV] = "1"
    return subprocess.Popen(
        [sys.executable, os.path.join(root, "e2e", "run_web.py"), "--host", host, "--port", str(port)],
        cwd=root,
        env=env,
    )


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _supervise(host: str, port: int) -> int:
    """父进程：原生文件事件监听，改动即重启子进程（服务跑在子进程）。"""
    from watchfiles import PythonFilter, watch

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print("[watch] 原生监听 DNAUID/ e2e/（*.py），改动自动重启", flush=True)
    proc = _spawn(root, host, port)

    def _shutdown(*_args: object) -> None:
        _stop(proc)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    try:
        for changes in watch(
            os.path.join(root, "DNAUID"), os.path.join(root, "e2e"), watch_filter=PythonFilter(), debounce=500
        ):
            files = sorted(os.path.relpath(p, root) for _, p in changes)
            print(f"[watch] {len(files)} 个文件改动，重启服务…", flush=True)
            for path in files[:5]:
                print(f"[watch]   {path}", flush=True)
            _stop(proc)
            proc = _spawn(root, host, port)
    except KeyboardInterrupt:
        print("[watch] 退出", flush=True)
    finally:
        _stop(proc)
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DNAUID e2e mock 宿主聊天服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--watch", action="store_true", help="原生监听 DNAUID/ 与 e2e/ 的 *.py，改动自动重启（开发用）")
    args = parser.parse_args()
    if args.watch and os.environ.get(_CHILD_ENV) != "1":
        raise SystemExit(_supervise(args.host, args.port))

    from e2e.web.server import run

    run(args.host, args.port)
