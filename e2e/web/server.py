"""e2e 聊天 Web 服务（仅标准库，无第三方依赖）。

- ``GET /``                 即时聊天界面
- ``GET  /api/state``       宿主状态：前缀 / 插件 / 路由数 / 历史
- ``POST /api/chat``        发送消息 → mock 宿主分发 → 回复 + 工具调用 trace
- ``POST /api/config``      自定义消息前缀 ``{"prefixes": ["dna", "DNA"]}``
- ``POST /api/reset``       清空历史与 Bot 收件箱
- ``POST /api/startup``     运行插件 ``on_core_start`` 钩子（工具回显）
"""

from __future__ import annotations

import asyncio
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

STATIC_DIR = Path(__file__).parent / "static"

_state_lock = threading.Lock()
_host = None
_report: dict[str, Any] = {"loaded": [], "errors": []}


def _run_loop_forever(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


class _ServerState:
    def __init__(self, public_host: str = "127.0.0.1", public_port: int = 8765) -> None:
        import threading  # noqa: PLC0415
        import uuid as _uuid  # noqa: PLC0415

        # 服务端重启后历史下标归零：epoch 变化时前端必须丢弃旧水位
        self.epoch = _uuid.uuid4().hex[:8]
        import time as _time  # noqa: PLC0415

        self.started_at = _time.time()

        # loop 常驻独立线程：后台任务（登录轮询等）在请求之间也能推进
        self.loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=_run_loop_forever, args=(self.loop,), daemon=True)
        self._loop_thread.start()
        from e2e.mock_host import MockHost, load_plugin  # noqa: PLC0415
        from e2e.mock_host.loader import init_runtime  # noqa: PLC0415
        from e2e.mock_host.stubs import core_config  # noqa: PLC0415

        core_config.configure(public_host, public_port)
        self.report = load_plugin()
        self.db = self.run(init_runtime())
        self.report["db"] = self.db
        self.host = MockHost()
        global _report
        _report = self.report
        self.login_port = self._start_login_pages()

    def run(self, coro: Any, timeout: float = 120.0) -> Any:
        """在常驻 loop 上执行协程并等待结果（HTTP 线程调用）。"""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        try:
            for task in self.host.background:
                self.loop.call_soon_threadsafe(task.cancel)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:  # noqa: BLE001
            pass

    def _start_login_pages(self) -> int:
        """用 uvicorn 挂载插件注册在 gsuid_core.web_app 上的真实登录页."""
        import socket  # noqa: PLC0415
        import threading  # noqa: PLC0415

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        login_port = sock.getsockname()[1]
        sock.close()
        try:
            import uvicorn  # noqa: PLC0415
            from gsuid_core.web_app import app  # noqa: PLC0415

            thread = threading.Thread(
                target=uvicorn.run,
                kwargs={"app": app, "host": "127.0.0.1", "port": login_port,
                        "log_level": "warning"},
                daemon=True,
            )
            thread.start()
        except Exception as exc:  # noqa: BLE001
            print(f"[e2e] 登录页服务启动失败（仅影响 dna登录 网页链路）: {exc!r}")
            return 0
        return login_port


def _normalize_upload_image(data_url: str) -> str:
    """宿主侧归一化：浏览器 dataURL 统一转 PNG（上游只认 png/jpeg/base64）。"""
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return data_url
    if data_url.startswith(("data:image/png;base64,", "data:image/jpeg;base64,",
                             "base64://")):
        return data_url
    try:
        import base64  # noqa: PLC0415
        import io as _io  # noqa: PLC0415

        from PIL import Image  # noqa: PLC0415

        header, _, b64 = data_url.partition(",")
        img = Image.open(_io.BytesIO(base64.b64decode(b64))).convert("RGB")
        buf = _io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return data_url


def _get_state() -> _ServerState:
    global _host
    if _host is None:
        with _state_lock:
            if _host is None:
                _host = _ServerState(public_host=_PUBLIC_HOST, public_port=_PUBLIC_PORT)
    return _host


def reset_for_tests() -> None:
    """测试专用：重建宿主状态（含 mock 全局注册表与后台任务）。"""
    global _host
    from e2e.mock_host import reset_state  # noqa: PLC0415

    with _state_lock:
        old, _host = _host, None
    if old is not None:
        try:
            old.close()
        except Exception:  # noqa: BLE001
            pass
    reset_state()


class Handler(BaseHTTPRequestHandler):
    server_version = "MockHost/1.0"

    # -- 工具 ---------------------------------------------------------
    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ANN002,ANN003
        pass

    def _proxy_login_pages(self) -> bool:
        """把 /dna/* 反代到 uvicorn 上的真实插件登录页。"""
        import urllib.request  # noqa: PLC0415

        state = _get_state()
        if not state.login_port:
            self._json({"error": "login pages unavailable"}, status=503)
            return True
        target = f"http://127.0.0.1:{state.login_port}{self.path}"
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length > 0 else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length")}
        try:
            req = urllib.request.Request(target, data=body, headers=headers, method=self.command)
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                ctype = resp.headers.get("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except Exception as exc:  # noqa: BLE001
            self._json({"error": f"login proxy failed: {exc!r}"[:300]}, status=502)
        return True

    # -- 路由 ---------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/dna" or parsed.path.startswith("/dna/"):
            self._proxy_login_pages()
            return
        if parsed.path in ("/", "/index.html"):
            page = STATIC_DIR / "index.html"
            body = page.read_bytes() if page.exists() else b"<h1>static/index.html missing</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            # 单文件前端迭代快：禁止缓存，避免旧 JS 残留导致重复渲染
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/state":
            state = _get_state()
            from e2e.mock_host import HANDLERS, PLUGIN_INFO  # noqa: PLC0415
            from e2e.mock_host.stubs import get_active_prefixes  # noqa: PLC0415

            self._json({
                "epoch": state.epoch,
                "started_at": state.started_at,
                "prefixes": get_active_prefixes(),
                "plugin": dict(PLUGIN_INFO),
                "handlers": len(HANDLERS),
                "report": state.report,
                "history": state.host.history[-200:],
            })
            return
        if parsed.path == "/api/history":
            state = _get_state()
            state.host.sync_inbox()
            query = urllib.parse.parse_qs(parsed.query or "")
            try:
                since = max(0, int((query.get("since") or ["0"])[0]))
            except ValueError:
                since = 0
            items = []
            for index, entry in enumerate(state.host.history[since:]):
                item = dict(entry)
                item["_i"] = since + index
                items.append(item)
            self._json({"history": items, "total": len(state.host.history),
                        "epoch": state.epoch})
            return
        if parsed.path == "/api/commands":
            _get_state()  # 确保插件已加载（_serve 后首次请求可能是本接口）
            from e2e.mock_host import HANDLERS  # noqa: PLC0415

            groups: dict[str, list] = {}
            for h in HANDLERS:
                groups.setdefault(h["sv"], []).append({
                    "kind": h["kind"],
                    "triggers": [str(t) for t in h["triggers"]],
                    "block": bool(h.get("block")),
                })
            self._json({
                "groups": [{"sv": sv, "items": items} for sv, items in groups.items()],
                "count": sum(len(v) for v in groups.values()),
            })
            return
        self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/dna" or parsed.path.startswith("/dna/"):
            self._proxy_login_pages()
            return
        payload = self._read_json()
        state = _get_state()

        if parsed.path == "/api/chat":
            text = str(payload.get("text", ""))
            user_id = str(payload.get("user_id", "10001") or "10001")
            group_id = payload.get("group_id") or None
            images = [_normalize_upload_image(u) for u in (payload.get("images") or [])]
            coro = state.host.chat(text, user_id=user_id, group_id=group_id, images=images)
            result = state.run(coro)
            payload = result.to_dict()
            payload["total"] = len(state.host.history)
            payload["epoch"] = state.epoch
            self._json(payload)
            return
        if parsed.path == "/api/config":
            from e2e.mock_host import set_custom_prefixes  # noqa: PLC0415
            from e2e.mock_host.stubs import get_active_prefixes  # noqa: PLC0415

            prefixes = payload.get("prefixes")
            if not isinstance(prefixes, list) or not all(isinstance(p, str) for p in prefixes):
                self._json({"error": "prefixes must be string[]"}, status=400)
                return
            set_custom_prefixes([p for p in prefixes if p])
            self._json({"prefixes": get_active_prefixes()})
            return
        if parsed.path == "/api/reset":
            state.host.reset()
            self._json({"ok": True})
            return
        if parsed.path == "/api/startup":
            from e2e.mock_host import run_startup  # noqa: PLC0415

            trace: list[dict] = []
            state.run(run_startup(trace))
            state.host.history.append({"role": "tool", "kind": "startup", "items": trace})
            self._json({"trace": trace})
            return
        self._json({"error": "not found"}, status=404)


_PUBLIC_HOST = "127.0.0.1"
_PUBLIC_PORT = 8765


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    global _host, _PUBLIC_HOST, _PUBLIC_PORT
    _PUBLIC_HOST, _PUBLIC_PORT = host, port
    with _state_lock:
        _host = None
    _get_state()  # 预加载插件，失败信息直接打屏
    from e2e.mock_host.stubs import get_active_prefixes  # noqa: PLC0415

    print(f"[e2e] mock 宿主就绪：前缀={get_active_prefixes()} 处理器={len(__import__('e2e.mock_host', fromlist=['HANDLERS']).HANDLERS)}")
    print(f"[e2e] 聊天界面：http://{host}:{port}/")
    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DNAUID e2e mock 宿主聊天服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(args.host, args.port)
