"""轮次归因：同一事件循环上交错的 chat 各自只认自己 handler 发出的消息。"""

from __future__ import annotations

from contextvars import ContextVar

current_turn: ContextVar[str | None] = ContextVar("mock_host_turn", default=None)
