"""Web API 单测：state / chat / config / reset / startup（仅标准库）。"""

import json
import os
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from e2e.web.server import Handler, reset_for_tests  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


def _serve():
    reset_for_tests()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(port, path, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_state_reports_plugin_and_routes():
    server, port = _serve()
    try:
        state = _get(port, "/api/state")
        assert isinstance(state["prefixes"], list) and state["prefixes"]
        assert state["handlers"] >= 3  # 演示指令
        assert state["report"]["plugin"]["name"] == "DNAUID"
    finally:
        server.shutdown()


def test_chat_roundtrip_with_tool_trace():
    server, port = _serve()
    try:
        result = _post(port, "/api/chat", {"text": "dnaping", "user_id": "10001"})
        assert result["replies"], result
        assert "pong" in result["replies"][0]["segments"][0]["text"]
        assert result["trace"][0]["kind"] == "tool"
        history = _get(port, "/api/history")
        assert any(h["role"] == "user" for h in history["history"])
    finally:
        server.shutdown()


def test_custom_prefix_via_api():
    server, port = _serve()
    try:
        cfg = _post(port, "/api/config", {"prefixes": ["#"]})
        assert cfg["prefixes"] == ["#"]
        ok = _post(port, "/api/chat", {"text": "#ping"})
        assert ok["replies"], ok
        missed = _post(port, "/api/chat", {"text": "dnaping"})
        assert missed["replies"] == []
    finally:
        server.shutdown()


def test_background_push_surfaces_via_history_poll():
    import asyncio  # noqa: PLC0415

    server, port = _serve()
    try:
        _post(port, "/api/chat", {"text": "dnaping"})
        base = _get(port, "/api/history")
        total = base["total"]
        # 模拟后台任务推送（登录完成、订阅推送等场景）
        from e2e.web.server import _get_state  # noqa: PLC0415

        state = _get_state()
        state.run(state.host.bot.send("后台推送测试"))
        inc = _get(port, f"/api/history?since={total}")
        assert inc["total"] > total
        assert all("_i" in h for h in inc["history"]), "历史条目应带绝对下标（前端去重用）"
        texts = [s.get("text", "") for h in inc["history"]
                 for s in h.get("segments", [])]
        assert any("后台推送测试" in t for t in texts)
    finally:
        server.shutdown()


def test_epoch_changes_on_restart():
    server, port = _serve()
    try:
        first = _get(port, "/api/history")
        assert "epoch" in first and first["epoch"]
        chat = _post(port, "/api/chat", {"text": "dnaping"})
        assert chat["epoch"] == first["epoch"]
    finally:
        server.shutdown()
    # 服务端“重启”：纪元必须变化，前端据此丢弃旧水位
    server2, port2 = _serve()
    try:
        second = _get(port2, "/api/history")
        assert second["epoch"] != first["epoch"]
        assert second["history"] == []
    finally:
        server2.shutdown()


def test_reset_clears_history():
    server, port = _serve()
    try:
        _post(port, "/api/chat", {"text": "dnaping"})
        _post(port, "/api/reset", {})
        history = _get(port, "/api/history")
        assert history["history"] == []
    finally:
        server.shutdown()


def test_commands_endpoint_lists_routes():
    server, port = _serve()
    try:
        data = _get(port, "/api/commands")
        assert data["count"] >= 3
        svs = [g["sv"] for g in data["groups"]]
        assert any("e2e" in s for s in svs)
        assert all("kind" in i and "triggers" in i for g in data["groups"] for i in g["items"])
    finally:
        server.shutdown()


def test_login_page_proxied():
    import re  # noqa: PLC0415

    server, port = _serve()
    try:
        result = _post(port, "/api/chat", {"text": "dna登录", "user_id": "90200"})
        text = result["replies"][0]["segments"][0]["text"]
        path = re.search(r"(/dna/i/\S+)", text).group(1)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as resp:
            html = resp.read().decode("utf-8")
        assert resp.status == 200 and ("login" in html.lower() or "登录" in html)
    finally:
        server.shutdown()


def test_index_page_served():
    server, port = _serve()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            html = resp.read().decode("utf-8")
        assert "e2e" in html and "/api/chat" in html
    finally:
        server.shutdown()
