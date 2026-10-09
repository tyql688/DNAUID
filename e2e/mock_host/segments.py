"""Mock 宿主的消息段模型.

模拟 ``gsuid_core.segment.MessageSegment`` / ``gsuid_core.models.Message``，
并提供面向 Web 聊天界面的 JSON 序列化（含图片 / at / 合并转发等回显，
以及“工具调用”形态的结构化展示）。
"""

from __future__ import annotations

import io
import base64
from os import PathLike
from typing import Any
from dataclasses import field, dataclass


def _image_to_data_url(data: Any) -> tuple[str, str]:
    """把各种形态的图片载荷统一为 ``(data_url, alt)``。"""
    # PIL 图片
    try:
        from PIL import Image  # type: ignore

        if isinstance(data, Image.Image):
            buf = io.BytesIO()
            data.save(buf, format="PNG")
            raw = buf.getvalue()
            b64 = base64.b64encode(raw).decode("ascii")
            return f"data:image/png;base64,{b64}", f"PIL-{data.size[0]}x{data.size[1]}"
    except ImportError:
        pass
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
        # 常见图片魔数嗅探
        if raw.startswith(b"\x89PNG"):
            mime = "image/png"
        elif raw.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif raw.startswith(b"GIF8"):
            mime = "image/gif"
        elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            mime = "image/png"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}", f"{len(raw)}B"
    if isinstance(data, str):
        if data.startswith("base64://"):
            raw = data[len("base64://") :]
            return f"data:image/jpeg;base64,{raw}", "base64"
        if data.startswith("data:"):
            return data, "base64"
        if data.startswith(("http://", "https://")):
            return data, "url"
        # 本地路径：读文件转 dataURL，否则前端无法渲染（真实宿主会托管图片）
        try:
            from pathlib import Path as _Path  # noqa: PLC0415

            path = _Path(data)
            if path.exists() and path.is_file() and path.stat().st_size < 8 * 1024 * 1024:
                return _image_to_data_url(path.read_bytes())
        except (OSError, ValueError):
            pass
        return data, "path"
    if isinstance(data, PathLike):
        try:
            from pathlib import Path as _Path2  # noqa: PLC0415

            path = _Path2(data)
            if path.exists() and path.is_file():
                return _image_to_data_url(path.read_bytes())
        except (OSError, ValueError):
            pass
        return "", repr(data)[:120]
    return "", repr(data)[:120]


class MessageSegment:
    """极简消息段：text / image / at / node / reply。"""

    def __init__(self, type: str, data: Any = None) -> None:
        self.type = type
        self.data = data

    @classmethod
    def text(cls, text: str) -> MessageSegment:
        return cls("text", {"text": str(text)})

    @classmethod
    def image(cls, data: Any) -> MessageSegment:
        return cls("image", data)

    @classmethod
    def at(cls, user_id: str | int) -> MessageSegment:
        return cls("at", {"user_id": str(user_id)})

    @classmethod
    def node(cls, items: Any) -> MessageSegment:
        if not isinstance(items, list):
            items = [items]
        return cls("node", items)

    @classmethod
    def reply(cls, message_id: str | int) -> MessageSegment:
        return cls("reply", {"message_id": str(message_id)})

    def __repr__(self) -> str:  # pragma: no cover
        return f"MessageSegment(type={self.type!r}, data={self.data!r})"


@dataclass
class Message:
    """兼容 ``gsuid_core.models.Message(type=..., data=...)`` 的构造形态。"""

    type: str = "text"
    data: Any = None


def serialize_segment(seg: Any) -> dict[str, Any]:
    """把单个消息段序列化为前端可渲染的 dict。"""
    if isinstance(seg, MessageSegment):
        kind = seg.type
        payload = seg.data
    elif isinstance(seg, Message):
        kind = seg.type
        payload = seg.data
    elif isinstance(seg, str):
        return {"kind": "text", "text": seg}
    elif isinstance(seg, dict) and "kind" in seg:
        return seg
    else:
        return {"kind": "text", "text": str(seg)}

    if kind == "text":
        text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
        return {"kind": "text", "text": text}
    if kind == "image":
        url, alt = _image_to_data_url(payload)
        return {"kind": "image", "url": url, "alt": alt}
    if kind == "at":
        uid = payload.get("user_id", "") if isinstance(payload, dict) else str(payload)
        return {"kind": "at", "user_id": uid, "text": f"@{uid}"}
    if kind == "node":
        items = payload if isinstance(payload, list) else [payload]
        children: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, (list, tuple)):
                children.extend(serialize_segment(i) for i in item)
            else:
                children.append(serialize_segment(item))
        return {"kind": "node", "children": children, "count": len(children)}
    if kind == "reply":
        mid = payload.get("message_id", "") if isinstance(payload, dict) else str(payload)
        return {"kind": "reply", "message_id": mid}
    # 未知类型按工具调用回显处理
    return {"kind": "tool", "name": str(kind), "data": repr(payload)[:500]}


def normalize_message(msg: Any) -> list[dict[str, Any]]:
    """把 ``bot.send`` 收到的任意载荷归一化为段列表。"""
    if msg is None:
        return []
    if isinstance(msg, (list, tuple)):
        out: list[dict[str, Any]] = []
        for item in msg:
            out.extend(normalize_message(item))
        return out
    if isinstance(msg, (MessageSegment, Message)):
        return [serialize_segment(msg)]
    if isinstance(msg, dict) and "kind" in msg:
        return [msg]
    if isinstance(msg, (bytes, bytearray)):
        return [serialize_segment(MessageSegment.image(bytes(msg)))]
    if isinstance(msg, str):
        return [serialize_segment(msg)]
    # PIL 图片等其它对象：尝试按图片处理，否则转文本
    try:
        from PIL import Image  # type: ignore

        if isinstance(msg, Image.Image):
            return [serialize_segment(MessageSegment.image(msg))]
    except ImportError:
        pass
    return [serialize_segment(str(msg))]


@dataclass
class SentMessage:
    """MockBot 捕获到的一条发送记录。"""

    segments: list[dict[str, Any]] = field(default_factory=list)
    at_sender: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    msg_id: int = 0  # 全局唯一，历史去重用

    @property
    def text(self) -> str:
        return "".join(s.get("text", "") for s in self.segments if s.get("kind") == "text")

    @property
    def has_image(self) -> bool:
        return any(s.get("kind") == "image" for s in self.segments)

    def to_dict(self) -> dict[str, Any]:
        return {"segments": self.segments, "at_sender": self.at_sender, "extra": self.extra, "msg_id": self.msg_id}
