"""MockBot：模拟 ``gsuid_core.bot.Bot`` 的发送侧。"""

from __future__ import annotations

import itertools
from typing import Any

from .segments import SentMessage, normalize_message
from .turn import current_turn

_msg_id = itertools.count(1)


class MockBot:
    """捕获所有 ``send``/``send_option`` 调用的假 Bot。"""

    def __init__(self, bot_id: str = "MockBot", bot_name: str = "MockHost") -> None:
        self.bot_id = bot_id
        self.bot_name = bot_name
        self.inbox: list[SentMessage] = []

    async def send(
        self,
        msg: Any,
        at_sender: bool = False,
        wait_recall: bool = False,  # noqa: FBT001,FBT002
        **kwargs: Any,
    ) -> list[int]:
        msg_id = next(_msg_id)
        record = SentMessage(
            segments=normalize_message(msg),
            at_sender=bool(at_sender),
            extra={"wait_recall": bool(wait_recall), "turn": current_turn.get(), **kwargs},
            msg_id=msg_id,
        )
        self.inbox.append(record)
        return [msg_id]

    async def send_option(self, msg: Any, **kwargs: Any) -> list[int]:
        msg_id = next(_msg_id)
        record = SentMessage(
            segments=normalize_message(msg),
            at_sender=False,
            extra={"option": True, "turn": current_turn.get(), **kwargs},
            msg_id=msg_id,
        )
        self.inbox.append(record)
        return [msg_id]

    def clear(self) -> None:
        self.inbox.clear()

    @property
    def last(self) -> SentMessage | None:
        return self.inbox[-1] if self.inbox else None
