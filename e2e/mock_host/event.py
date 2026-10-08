"""Mock 事件模型：模拟 ``gsuid_core.models.Event``。"""

from __future__ import annotations

from typing import Any
from dataclasses import field, dataclass


@dataclass
class MockMessage:
    type: str = "text"
    data: Any = None


@dataclass
class MockEvent:
    """插件处理器实际消费的事件字段全集。"""

    bot_id: str = "MockBot"
    real_bot_id: str = "MockBot"
    user_id: str = "10001"
    group_id: str | None = None
    user_type: str = "direct"
    user_pm: int = 6  # mock 宿主默认给足权限，方便走通全部指令
    raw_text: str = ""
    text: str = ""
    command: str = ""
    regex_dict: dict[str, str] = field(default_factory=dict)
    regex_group: tuple = ()
    at: Any = None
    at_list: list = field(default_factory=list)
    reply: Any = None
    image_list: list = field(default_factory=list)
    WS_BOT_ID: str = ""
    bot_self_id: str = "MockBot"
    sender: dict = field(default_factory=dict)


def make_event(
    raw_text: str,
    user_id: str = "10001",
    group_id: str | None = None,
    bot_id: str = "MockBot",
    images: list | None = None,
    user_pm: int = 6,
) -> MockEvent:
    """构造一条可直接分发的事件。"""
    uid = str(user_id)
    # 真宿主由网关填充 sender 头像；mock 对数字 QQ 号拼官方直链（与 onebot 同源），
    # 下游 get_event_avatar 会经缓存下载，失败则走原有 fallback。
    sender = {"avatar": f"http://q1.qlogo.cn/g?b=qq&nk={uid}&s=640", "nickname": uid} if uid.isdigit() else {}
    return MockEvent(
        bot_id=bot_id,
        real_bot_id=bot_id,
        user_id=uid,
        group_id=group_id,
        user_type="group" if group_id else "direct",
        user_pm=user_pm,
        raw_text=raw_text,
        text=raw_text,
        command="",
        image_list=list(images or []),
        sender=sender,
    )
