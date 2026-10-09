"""mock 宿主对外门面。"""

from .bot import MockBot
from .event import MockEvent, make_event
from .stubs import (
    HANDLERS,
    PLUGIN_INFO,
    HELP_RENDERER,
    install,
    core_config,
    reset_state,
    run_startup,
    set_custom_prefixes,
)
from .loader import load_plugin, init_runtime, ensure_demo_handlers
from .segments import SentMessage, MessageSegment, normalize_message, serialize_segment
from .dispatcher import MockHost

__all__ = [
    "HANDLERS",
    "PLUGIN_INFO",
    "HELP_RENDERER",
    "MessageSegment",
    "MockBot",
    "MockEvent",
    "MockHost",
    "SentMessage",
    "core_config",
    "ensure_demo_handlers",
    "init_runtime",
    "install",
    "load_plugin",
    "make_event",
    "normalize_message",
    "reset_state",
    "run_startup",
    "serialize_segment",
    "set_custom_prefixes",
]
