"""分发器单测：前缀剥离 / 四种路由 / 自定义前缀 / 图片与工具回显（仅标准库）。"""

import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from e2e.mock_host import (  # noqa: E402
    MockHost,
    MessageSegment,
    install,
    reset_state,
    set_custom_prefixes,
)

install()


def _register_routes():
    from gsuid_core.sv import SV  # noqa: PLC0415

    sv = SV("单测", priority=0)

    @sv.on_fullmatch("帮助", block=True)
    async def _help(bot, ev):
        await bot.send("这是帮助")

    @sv.on_prefix(("开启", "关闭"), block=True)
    async def _switch(bot, ev):
        await bot.send(f"开关：{ev.text}")

    @sv.on_regex(r"^绑定(?P<uid>\d+)$", block=True)
    async def _bind(bot, ev):
        await bot.send(f"绑定 {ev.regex_dict['uid']}")

    @sv.on_command("公告", block=True)
    async def _ann(bot, ev):
        await bot.send(f"公告参数：{ev.text}")

    @sv.on_fullmatch("图文", block=True)
    async def _rich(bot, ev):
        await bot.send(
            [
                MessageSegment.text("看图："),
                MessageSegment.image(b"\x89PNG" + b"1" * 8),
                MessageSegment.at("10001"),
                MessageSegment.node([MessageSegment.text("转发一"), MessageSegment.text("转发二")]),
            ]
        )


def _fresh_host():
    reset_state()
    set_custom_prefixes(["dna", "DNA"])
    _register_routes()
    return MockHost()


def test_fullmatch_and_reply():
    host = _fresh_host()
    result = asyncio.run(host.chat("dna帮助"))
    assert len(result.matched) == 1
    assert result.replies[0]["segments"][0]["text"] == "这是帮助"
    assert result.trace[0]["ok"] is True


def test_prefix_trigger_splits_text():
    host = _fresh_host()
    result = asyncio.run(host.chat("dna开启自动签到"))
    assert result.replies[0]["segments"][0]["text"] == "开关：自动签到"


def test_regex_groups():
    host = _fresh_host()
    result = asyncio.run(host.chat("dna绑定123456"))
    assert "123456" in result.replies[0]["segments"][0]["text"]
    assert result.matched[0]["via"].startswith("regex:")


def test_command_with_args():
    host = _fresh_host()
    result = asyncio.run(host.chat("dna公告 1"))
    assert result.replies[0]["segments"][0]["text"] == "公告参数：1"


def test_no_prefix_is_ignored_with_hint():
    host = _fresh_host()
    result = asyncio.run(host.chat("帮助"))
    assert result.replies == []
    assert any("未命中前缀" in t.get("message", "") for t in result.trace)


def test_custom_prefix_override():
    host = _fresh_host()
    set_custom_prefixes(["#"])
    result = asyncio.run(host.chat("#帮助"))
    assert len(result.replies) == 1
    missed = asyncio.run(host.chat("dna帮助"))
    assert missed.replies == []


def test_rich_segments_and_tool_trace():
    host = _fresh_host()
    result = asyncio.run(host.chat("dna图文"))
    kinds = [s["kind"] for s in result.replies[0]["segments"]]
    assert kinds == ["text", "image", "at", "node"]
    assert result.replies[0]["segments"][1]["url"].startswith("data:image/png;base64,")
    tool = result.trace[0]
    assert tool["kind"] == "tool" and tool["sent"] == 1 and tool["ok"] is True


def test_user_images_reach_event():
    seen = {}

    def _run():
        reset_state()
        set_custom_prefixes(["dna"])
        from gsuid_core.sv import SV  # noqa: PLC0415

        sv = SV("图单测")

        @sv.on_fullmatch("传图", block=True)
        async def _img(bot, ev):
            seen["n"] = len(ev.image_list)
            await bot.send(f"收到 {len(ev.image_list)} 张图")

        host = MockHost()
        return asyncio.run(host.chat("dna传图", images=["data:image/png;base64,AAA"]))

    result = _run()
    assert seen["n"] == 1
    assert "1 张图" in result.replies[0]["segments"][0]["text"]


def test_handler_exception_becomes_error_reply():
    def _run():
        reset_state()
        set_custom_prefixes(["dna"])
        from gsuid_core.sv import SV  # noqa: PLC0415

        sv = SV("爆单测")

        @sv.on_fullmatch("炸", block=True)
        async def _boom(bot, ev):  # noqa: ARG001
            raise RuntimeError("boom")

        host = MockHost()
        return asyncio.run(host.chat("dna炸"))

    result = _run()
    assert result.trace[0]["ok"] is False
    assert "boom" in result.trace[0]["error"]
    assert "执行失败" in result.replies[0]["segments"][0]["text"]
