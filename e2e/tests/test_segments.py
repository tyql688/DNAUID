"""消息段序列化单测（仅标准库）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from e2e.mock_host import MessageSegment, normalize_message, serialize_segment  # noqa: E402


def test_text_segment():
    seg = serialize_segment(MessageSegment.text("hello"))
    assert seg == {"kind": "text", "text": "hello"}


def test_image_bytes_sniff_png():
    raw = b"\x89PNG" + b"\x00" * 10
    seg = serialize_segment(MessageSegment.image(raw))
    assert seg["kind"] == "image"
    assert seg["url"].startswith("data:image/png;base64,")


def test_at_segment():
    seg = serialize_segment(MessageSegment.at("12345"))
    assert seg["kind"] == "at"
    assert seg["user_id"] == "12345"


def test_node_segment_flattens_children():
    seg = serialize_segment(MessageSegment.node([MessageSegment.text("a"), MessageSegment.at("1")]))
    assert seg["kind"] == "node"
    assert seg["count"] == 2
    assert seg["children"][0]["text"] == "a"


def test_normalize_mixed_list():
    parts = normalize_message(["hi", MessageSegment.at("9"), b"\x89PNGxx"])
    assert [p["kind"] for p in parts] == ["text", "at", "image"]


def test_normalize_plain_string():
    assert normalize_message("ok") == [{"kind": "text", "text": "ok"}]
