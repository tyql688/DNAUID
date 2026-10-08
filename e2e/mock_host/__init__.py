"""mock 宿主对外门面。"""

from .bot import MockBot
from .dispatcher import MockHost
from .event import MockEvent, make_event
from .loader import ensure_demo_handlers, init_runtime, load_plugin
from .segments import MessageSegment, SentMessage, normalize_message, serialize_segment
from .stubs import (
    HANDLERS,
    HELP_RENDERER,
    PLUGIN_INFO,
    core_config,
    install,
    reset_state,
    run_startup,
    set_custom_prefixes,
)

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
