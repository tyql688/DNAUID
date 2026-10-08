"""真实插件回复测试：需要第三方依赖，缺失时自动 skip。

运行前：``uv sync --group e2e``
执行：``uv run --group e2e pytest e2e/tests/test_plugin_reply.py -v``
"""

import os
import sys
import asyncio

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from e2e.mock_host import MockHost, load_plugin, reset_state  # noqa: E402

MISSING: list[str] = []
for _mod in ("PIL", "sqlmodel", "httpx", "jinja2", "cachetools"):
    try:
        __import__(_mod)
    except ImportError:
        MISSING.append(_mod)

pytestmark = pytest.mark.skipif(bool(MISSING), reason=f"缺少第三方依赖：{MISSING}")


@pytest.fixture()
def host():
    from e2e.mock_host.loader import init_runtime  # noqa: PLC0415

    reset_state()
    report = load_plugin()
    asyncio.run(init_runtime())
    return MockHost(), report


def test_plugin_modules_loaded(host):
    _host, report = host
    assert report["plugin"].get("name") == "DNAUID"
    assert report["handlers"] > 10, report


def test_help_reply_contains_image(host):
    _host, report = host
    result = asyncio.run(_host.chat("dna帮助"))
    assert result.matched, result.trace
    assert result.replies, result.trace
    kinds = [s["kind"] for r in result.replies for s in r["segments"]]
    assert "image" in kinds


def test_help_uses_real_gsuid_renderer(host):
    """帮助图必须走上游真实 get_new_help（输出 JPEG），而非本地占位渲染。"""
    import io as _io
    import base64

    _host, _report = host
    result = asyncio.run(_host.chat("dna帮助"))
    segs = [s for r in result.replies for s in r["segments"] if s["kind"] == "image"]
    assert segs, result.trace
    url = segs[0]["url"]
    assert url.startswith("data:image/jpeg;base64,"), url[:40]
    from PIL import Image  # noqa: PLC0415

    img = Image.open(_io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert img.width >= 1500, img.size  # 真实版式宽度（fallback 为 1000）


def test_config_defaults_are_real(host):
    """插件配置走真实 StringConfig，默认值生效（登录 local 模式的前提）。"""
    from DNAUID.dna_config.dna_config import DNAConfig  # noqa: PLC0415

    assert DNAConfig.get_config("DNALoginTransport").data == "local"
    assert DNAConfig.get_config("DNAQRLogin").data is False
    assert DNAConfig.get_config("MaxBindNum").data == 2


def test_bind_and_view_roundtrip_real_db(host):
    """绑定→sqlite 落盘→查看读回，全真实链路。"""
    import random  # noqa: PLC0415

    from DNAUID.utils.database.models import DNABind  # noqa: PLC0415

    _host, _report = host
    game_uid = "900" + "".join(random.choices("0123456789", k=10))
    tester = "8" + "".join(random.choices("0123456789", k=7))
    result = asyncio.run(_host.chat(f"dna绑定{game_uid}", user_id=tester))
    assert result.matched, result.trace
    assert result.trace[0]["ok"] is True, result.trace
    rec = asyncio.run(DNABind.select_data(tester, "MockBot"))
    assert rec is not None and game_uid in (rec.uid or "")
    viewed = asyncio.run(_host.chat("dna查看UID", user_id=tester))
    assert viewed.replies, viewed.trace
    assert game_uid in viewed.replies[0]["segments"][0]["text"]


def test_login_returns_real_login_url(host):
    """dna登录 走真实 local 流程：返回可用登录地址，处理器转后台等待。"""
    _host, _report = host
    result = asyncio.run(_host.chat("dna登录", user_id="90100"))
    assert result.matched, result.trace
    text = result.replies[0]["segments"][0]["text"]
    assert "/dna/i/" in text, text
    tool = result.trace[0]
    assert tool["ok"] is True and tool.get("background") is True


def test_unknown_command_gives_no_match_hint(host):
    _host, _report = host
    result = asyncio.run(_host.chat("dna根本不存在的指令xyz"))
    assert result.replies == [] or result.matched == []
    assert any(t.get("kind") in ("system", "tool") for t in result.trace)
