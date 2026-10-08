"""伪造 ``gsuid_core`` 包：让插件在没有真实宿主的情况下可导入、可分发。

设计要点
--------
1. ``sv / bot / models / segment / logger / server / aps / subscribe`` 等
   插件高频使用的模块提供**有真实行为**的最小实现（SV 注册路由表、
   Bot 捕获发送、Event 复刻字段、scheduler/subscribe 内存实现）。
2. 其余 ``gsuid_core.*`` 子模块通过 ``MetaPathFinder`` 兜底为
   ``Dummy`` 对象（可调用、可等待、可做基类、可做装饰器），保证
   ``from gsuid_core.xxx import yyy`` 永远不会在导入期炸掉。
3. 少数影响演示效果的函数（``convert_img`` / ``get_new_help`` /
   ``get_qrcode_base64``）提供可工作的特化实现。
"""

from __future__ import annotations

import asyncio
import importlib.abc
import importlib.machinery
import logging
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Callable

from .bot import MockBot
from .event import MockEvent, MockMessage
from .segments import MessageSegment

# ---------------------------------------------------------------------------
# 全局注册表（测试间可 reset）
# ---------------------------------------------------------------------------

HANDLERS: list[dict[str, Any]] = []
PLUGIN_INFO: dict[str, Any] = {}
STARTUP_FUNCS: list[Callable] = []
SCHEDULED_JOBS: list[dict[str, Any]] = []
HELP_ENTRIES: list[dict[str, Any]] = []
STATUS_ENTRIES: list[dict[str, Any]] = []
_CUSTOM_PREFIXES: list[str] | None = None


def reset_state() -> None:
    HANDLERS.clear()
    PLUGIN_INFO.clear()
    STARTUP_FUNCS.clear()
    SCHEDULED_JOBS.clear()
    HELP_ENTRIES.clear()
    STATUS_ENTRIES.clear()
    global _CUSTOM_PREFIXES
    _CUSTOM_PREFIXES = None


def set_custom_prefixes(prefixes: list[str] | None) -> None:
    global _CUSTOM_PREFIXES
    _CUSTOM_PREFIXES = [p for p in (prefixes or []) if p]


def get_active_prefixes() -> list[str]:
    if _CUSTOM_PREFIXES:
        return list(_CUSTOM_PREFIXES)
    force = PLUGIN_INFO.get("force_prefix") or ["dna"]
    if isinstance(force, str):
        force = [force]
    return list(force)


def get_plugin_available_prefix(plugin_name: str = "") -> str:  # noqa: ARG001
    prefixes = get_active_prefixes()
    return prefixes[0] if prefixes else ""


# ---------------------------------------------------------------------------
# SV / Plugins
# ---------------------------------------------------------------------------

def _as_tuple(value: Any) -> tuple:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(value)
    return (value,)


class SV:
    """路由注册器：只记录，不做任何权限/场景拦截（mock 宿主默认放行）。"""

    def __init__(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.sv_name = name
        self.args = args
        self.kwargs = kwargs

    def _record(self, kind: str, triggers: Any, func: Callable, extra: dict) -> Callable:
        HANDLERS.append(
            {
                "sv": self.sv_name,
                "kind": kind,
                "triggers": _as_tuple(triggers),
                "func": func,
                "func_name": getattr(func, "__name__", repr(func)),
                # 真宿主默认值：priority=5，pm=6
                "priority": self.kwargs.get("priority", 5),
                "pm": self.kwargs.get("pm", 6),
                "block": bool(extra.get("block", False)),
            }
        )
        return func

    def _deco(self, kind: str, triggers: Any, **kw: Any) -> Callable:
        def wrapper(func: Callable) -> Callable:
            return self._record(kind, triggers, func, kw)

        return wrapper

    def on_fullmatch(self, keywords: Any, **kw: Any) -> Callable:
        return self._deco("fullmatch", keywords, **kw)

    def on_prefix(self, prefixes: Any, **kw: Any) -> Callable:
        return self._deco("prefix", prefixes, **kw)

    def on_regex(self, pattern: Any, **kw: Any) -> Callable:
        return self._deco("regex", pattern, **kw)

    def on_command(self, commands: Any, **kw: Any) -> Callable:
        return self._deco("command", commands, **kw)

    def on_keyword(self, keywords: Any, **kw: Any) -> Callable:
        return self._deco("keyword", keywords, **kw)

    # 兼容可能存在的其它装饰形态：直接当作 fullmatch 记录
    def __getattr__(self, name: str) -> Any:
        if name.startswith("on_"):
            def _fallback(triggers: Any = (), **kw: Any) -> Callable:
                return self._deco(name[3:], triggers, **kw)

            return _fallback
        raise AttributeError(name)


class Plugins:
    def __init__(self, name: str = "", **kwargs: Any) -> None:
        PLUGIN_INFO["name"] = name
        PLUGIN_INFO.update(kwargs)


# ---------------------------------------------------------------------------
# logger / scheduler / subscribe / server
# ---------------------------------------------------------------------------

_base_logger = logging.getLogger("mock_host.gsuid_core")


class _Logger:
    def _log(self, level: int, msg: Any, *a: Any) -> None:
        try:
            _base_logger.log(level, str(msg), *a)
        except Exception:  # pragma: no cover
            pass

    def debug(self, msg: Any, *a: Any) -> None:
        self._log(logging.DEBUG, msg, *a)

    def info(self, msg: Any, *a: Any) -> None:
        self._log(logging.INFO, msg, *a)

    def success(self, msg: Any, *a: Any) -> None:
        self._log(logging.INFO, f"[SUCCESS] {msg}", *a)

    def warning(self, msg: Any, *a: Any) -> None:
        self._log(logging.WARNING, msg, *a)

    def error(self, msg: Any, *a: Any) -> None:
        self._log(logging.ERROR, msg, *a)

    def exception(self, msg: Any, *a: Any) -> None:
        self._log(logging.ERROR, msg, *a)

    def trace(self, msg: Any, *a: Any) -> None:
        self._log(logging.DEBUG, msg, *a)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        def _level(msg: Any, *a: Any) -> None:
            self._log(logging.DEBUG, f"[{name}] {msg}", *a)

        return _level


logger = _Logger()


class _Scheduler:
    def scheduled_job(self, *args: Any, **kwargs: Any) -> Callable:
        def wrapper(func: Callable) -> Callable:
            SCHEDULED_JOBS.append({"func": func, "args": args, "kwargs": kwargs})
            return func

        return wrapper

    def __getattr__(self, name: str) -> Any:
        return Dummy()  # type: ignore[return-value]


class _BotAdapter:
    """gss.active_bot 中的单 Bot 适配器：target_send 落到 MockBot 收件箱。"""

    def __init__(self, bot: Any) -> None:
        self._bot = bot

    async def target_send(self, msg: Any, target_type: str = "", target_id: Any = None,
                          *args: Any, **kwargs: Any) -> None:
        from .segments import SentMessage, normalize_message  # noqa: PLC0415

        self._bot.inbox.append(SentMessage(
            segments=normalize_message(msg),
            extra={"push": True, "target_type": target_type,
                   "target_id": str(target_id)},
        ))


class _Gss:
    def __init__(self) -> None:
        self._bots: dict[str, Any] = {}

    def register(self, bot: Any) -> None:
        self._bots[getattr(bot, "bot_id", "MockBot")] = _BotAdapter(bot)

    @property
    def active_bot(self) -> dict[str, _BotAdapter]:
        return dict(self._bots)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return Dummy()


scheduler = _Scheduler()


class _Subscription:
    """与真实 Subscribe 记录同构的订阅条目（handlers 只读字段 + send 投递）。"""

    def __init__(self, task_name: str, ev: Any, store: "_SubscribeStore", **kwargs: Any) -> None:
        self.task_name = task_name
        self.group_id = getattr(ev, "group_id", None)
        self.user_id = getattr(ev, "user_id", None)
        self.bot_id = getattr(ev, "bot_id", None)
        self.bot_self_id = getattr(ev, "real_bot_id", None) or getattr(ev, "bot_id", None)
        self.user_type = getattr(ev, "user_type", None)
        self.WS_BOT_ID = getattr(ev, "WS_BOT_ID", None)
        self.uid = kwargs.get("uid")
        self.extra_message = str(kwargs.get("extra_message", "") or "")
        self.extra_data = kwargs.get("extra_data")
        self.data: dict[str, Any] = {}
        self._store = store

    def matches(self, filters: dict[str, Any]) -> bool:
        for key, value in filters.items():
            if value is None:
                continue
            mine = getattr(self, key, None)
            if mine is None and key in self.data:
                mine = self.data.get(key)
            if str(mine) != str(value):
                return False
        return True

    async def send(self, msg: Any) -> None:
        from .segments import normalize_message  # noqa: PLC0415

        self._store.outbox.append({
            "task": self.task_name,
            "group_id": self.group_id,
            "user_id": self.user_id,
            "segments": normalize_message(msg),
        })


class _SubscribeStore:
    def __init__(self) -> None:
        self.data: dict[str, list] = {}
        self.outbox: list[dict[str, Any]] = []

    # 写入载荷，不参与条目匹配
    _PAYLOAD_KEYS = frozenset({"extra_message", "extra_data", "data"})

    def _find(self, key: str, ev: Any, **kwargs: Any) -> list:
        subs = self.data.get(key, [])
        if ev is None and not kwargs:
            return list(subs)
        filters = {k: v for k, v in kwargs.items() if k not in self._PAYLOAD_KEYS}
        if ev is not None:
            for field in ("group_id", "user_id", "bot_id"):
                value = getattr(ev, field, None)
                if value is not None:
                    filters.setdefault(field, value)
        return [s for s in subs if s.matches(filters)]

    async def add_subscribe(self, *args: Any, **kwargs: Any) -> None:
        key = str(args[1]) if len(args) > 1 else "default"
        ev = args[2] if len(args) > 2 else None
        entry = _Subscription(key, ev, self, **kwargs)
        subs = self.data.setdefault(key, [])
        subs[:] = [s for s in subs
                   if not (s.group_id == entry.group_id and s.user_id == entry.user_id
                           and s.uid == entry.uid)]
        subs.append(entry)

    async def delete_subscribe(self, *args: Any, **kwargs: Any) -> None:
        key = str(args[1]) if len(args) > 1 else "default"
        ev = args[2] if len(args) > 2 else None
        if ev is None and not kwargs:
            self.data.pop(key, None)
            return
        victims = self._find(key, ev, **kwargs)
        subs = self.data.get(key, [])
        for victim in victims:
            if victim in subs:
                subs.remove(victim)

    async def update_subscribe_message(self, *args: Any, **kwargs: Any) -> None:
        key = str(args[1]) if len(args) > 1 else "default"
        ev = args[2] if len(args) > 2 else None
        for entry in self._find(key, ev, **{k: v for k, v in kwargs.items() if k != "extra_message"}):
            entry.extra_message = str(kwargs.get("extra_message", "") or "")

    async def update_subscribe_data(self, *args: Any, **kwargs: Any) -> None:
        key = str(args[1]) if len(args) > 1 else "default"
        ev = args[2] if len(args) > 2 else None
        reserved = {"extra_message"}
        for entry in self._find(key, ev, **{k: v for k, v in kwargs.items() if k not in reserved}):
            for k, v in kwargs.items():
                if k == "extra_message":
                    entry.extra_message = str(v or "")
                elif hasattr(entry, k):
                    setattr(entry, k, v)
                else:
                    entry.data[k] = v

    async def get_subscribe(self, *args: Any, **kwargs: Any) -> list:
        if not args:
            return []
        return self._find(str(args[0]), None, **kwargs)


gs_subscribe = _SubscribeStore()


def on_core_start(func: Callable) -> Callable:
    STARTUP_FUNCS.append(func)
    return func


# ---------------------------------------------------------------------------
# 特化小函数
# ---------------------------------------------------------------------------

async def convert_img(img: Any) -> bytes:
    """尽力把图片载荷转成 bytes（mock 宿主不做真实绘图）。"""
    if isinstance(img, (bytes, bytearray)):
        return bytes(img)
    try:
        from PIL import Image  # type: ignore

        if isinstance(img, Image.Image):
            import io as _io

            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except ImportError:
        pass
    if isinstance(img, str):
        return img.encode("utf-8", errors="ignore")
    return repr(img).encode("utf-8", errors="ignore")


async def convert_img(img: Any) -> bytes:
    """优先走上游真实 ``convert_img``，缺失时本地透传。"""
    from . import real_gsuid as _rg  # noqa: PLC0415

    if _rg.is_real_available("gsuid_core.utils.image.convert"):
        try:
            from gsuid_core.utils.image.convert import (  # type: ignore[import-not-found]  # noqa: PLC0415
                convert_img as real_convert_img,
            )

            return await real_convert_img(img)
        except Exception:  # noqa: BLE001
            pass
    return _passthrough_image(img)


async def _passthrough_image(img: Any) -> bytes:
    """本地透传：bytes/PIL/其它 -> bytes。"""
    if isinstance(img, (bytes, bytearray)):
        return bytes(img)
    try:
        from PIL import Image  # type: ignore  # noqa: PLC0415

        if isinstance(img, Image.Image):
            import io as _io  # noqa: PLC0415

            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except ImportError:
        pass
    if isinstance(img, str):
        return img.encode("utf-8", errors="ignore")
    return repr(img).encode("utf-8", errors="ignore")


async def get_new_help(**kwargs: Any) -> bytes:
    """调用上游 gsuid_core 的真实 ``get_new_help`` 渲染帮助图。

    真实链路缺失（未执行 sync 脚本）时才回退到本地渲染器。
    """
    from . import real_gsuid as _rg  # noqa: PLC0415

    if _rg.is_real_available("gsuid_core.help.draw_new_plugin_help"):
        try:
            _rg.ensure_core_font()
            from gsuid_core.help.draw_new_plugin_help import (  # type: ignore[import-not-found]  # noqa: PLC0415
                get_new_help as real_get_new_help,
            )

            result = await real_get_new_help(**kwargs)
            if isinstance(result, (bytes, bytearray)):
                HELP_RENDERER.update(mode="real", detail="gsuid_core.help.draw_new_plugin_help")
                return bytes(result)
        except Exception as exc:  # noqa: BLE001
            HELP_RENDERER.update(mode="fallback", detail=f"real failed: {exc!r}"[:200])
    try:
        from .help_image import draw_plugin_help  # noqa: PLC0415

        return draw_plugin_help(**kwargs)
    except Exception:  # noqa: BLE001
        return b"mock-help-image"


async def get_qrcode_base64(*args: Any, **kwargs: Any) -> bytes:  # noqa: ARG001
    return await get_new_help()


_RES_DIR = Path(tempfile.gettempdir()) / "mock_host_res"


def get_res_path(*parts: Any) -> Path:
    """兼容真实签名 ``get_res_path(*parts)`` 的最小实现（也接受 list 参数）。"""
    flat: list[str] = []
    for part in parts:
        if isinstance(part, (list, tuple)):
            flat.extend(str(p) for p in part)
        elif part is not None:
            flat.append(str(part))
    path = _RES_DIR.joinpath(*flat) if flat else _RES_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


HELP_RENDERER: dict[str, str] = {"mode": "unknown", "detail": ""}


class _CoreConfig:
    """core 侧 HOST/PORT 可随服务启动参数更新（登录页 URL 依赖它）。"""

    def __init__(self) -> None:
        self.values: dict[str, Any] = {"HOST": "127.0.0.1", "PORT": 8765}

    def configure(self, host: str | None = None, port: int | None = None) -> None:
        if host:
            self.values["HOST"] = host
        if port:
            self.values["PORT"] = port

    def get_config(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


core_config = _CoreConfig()


def with_session(func: Callable) -> Callable:
    """注入 ``session=None`` 的透传装饰器。

    mock 宿主没有真实数据库：handler 内首次使用 session 即抛错，
    由 dispatcher 转为错误回显，而不是在导入期/调用期出现诡异行为。
    """

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("session", None)
        return await func(*args, **kwargs)

    wrapper.__name__ = getattr(func, "__name__", "wrapped")
    return wrapper


class _Site:
    def register_admin(self, cls: Any) -> Any:
        return cls

    def __getattr__(self, name: str) -> Any:
        return Dummy()  # type: ignore[return-value]


site = _Site()


# ---------------------------------------------------------------------------
# 通用 Dummy：可调用 / 可等待 / 可继承 / 可做装饰器
# ---------------------------------------------------------------------------

class _DummyMeta(type):
    def __getattr__(cls, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return Dummy()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        return type.__call__(cls, *args, **kwargs)


class Dummy(metaclass=_DummyMeta):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._args = args
        self._kwargs = kwargs

    def __call__(self, *args: Any, **kwargs: Any) -> "Dummy":
        return Dummy(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return Dummy()

    def __await__(self):  # type: ignore[no-untyped-def]
        async def _none() -> None:
            return None

        return _none().__await__()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        pass

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(())

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __repr__(self) -> str:  # pragma: no cover
        return "Dummy()"


# ---------------------------------------------------------------------------
# 模块装配
# ---------------------------------------------------------------------------

def _mod(name: str, **attrs: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    module.__getattr__ = lambda attr, _n=name: _dummy_attr(_n, attr)  # type: ignore[attr-defined]
    sys.modules[name] = module
    return module


def _dummy_attr(mod_name: str, attr: str) -> Any:  # noqa: ARG001
    return Dummy()


class _FallbackFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """兜底所有未显式装配的 ``gsuid_core.*`` 子模块。"""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None):  # type: ignore[no-untyped-def]
        if fullname == "gsuid_core" or fullname.startswith("gsuid_core."):
            if fullname in sys.modules:
                return None
            try:
                from .real_gsuid import REAL_DIR, REAL_SUBMODULES  # noqa: PLC0415

                rel = REAL_SUBMODULES.get(fullname)
                if rel and (REAL_DIR / rel).exists():
                    return None  # 白名单真实模块优先
            except Exception:  # noqa: BLE001
                pass
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec: Any) -> Any:  # type: ignore[no-untyped-def]
        return None

    def exec_module(self, module: types.ModuleType) -> None:
        module.__path__ = []  # type: ignore[attr-defined]
        module.__getattr__ = lambda attr, _n=module.__name__: _dummy_attr(_n, attr)  # type: ignore[attr-defined]


_INSTALLED = False


def install() -> None:
    """把伪造的 ``gsuid_core`` 包注入 ``sys.modules``（幂等）。"""
    global _INSTALLED
    if _INSTALLED:
        return
    sys.modules.pop("gsuid_core", None)
    from . import real_gsuid as _rg_early  # noqa: PLC0415

    _rg_early.install_hook()
    if not any(isinstance(f, _FallbackFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _FallbackFinder())

    pkg = types.ModuleType("gsuid_core")
    pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["gsuid_core"] = pkg

    _mod("gsuid_core.sv", SV=SV, Plugins=Plugins,
         get_plugin_available_prefix=get_plugin_available_prefix)
    _mod("gsuid_core.bot", Bot=MockBot)
    _mod("gsuid_core.models", Event=MockEvent, Message=MockMessage)
    _mod("gsuid_core.logger", logger=logger)
    _mod("gsuid_core.segment", MessageSegment=MessageSegment)
    _mod("gsuid_core.server", on_core_start=on_core_start)
    _mod("gsuid_core.aps", scheduler=scheduler)
    _mod("gsuid_core.subscribe", gs_subscribe=gs_subscribe)
    _mod("gsuid_core.config", core_config=core_config)
    _mod("gsuid_core.data_store", get_res_path=get_res_path)
    _mod("gsuid_core.gss", gss=_Gss())
    try:
        from fastapi import FastAPI  # noqa: PLC0415

        _mod("gsuid_core.web_app", app=FastAPI(title="mock-host"))
    except ImportError:
        _mod("gsuid_core.web_app", app=Dummy())
    from . import real_gsuid as _rg  # noqa: PLC0415

    _rg.install_hook()
    _mod("gsuid_core.help", PluginHelp=Dummy)
    # 真实链路缺失时才预装本地存根，否则白名单 hook 提供真实模块
    if not _rg.is_real_available("gsuid_core.help.draw_new_plugin_help"):
        _mod("gsuid_core.help.draw_new_plugin_help", get_new_help=get_new_help)
    if not _rg.is_real_available("gsuid_core.help.model"):
        _mod("gsuid_core.help.model", PluginHelp=Dummy)
    if not _rg.is_real_available("gsuid_core.utils.image.convert"):
        _mod(
            "gsuid_core.utils.image.convert",
            convert_img=convert_img,
            convert_img_sync=lambda img, *a, **k: img,
        )
    from .gs_config_real import (  # noqa: PLC0415
        StringConfig as RealStringConfig,
        make_database_config,
        make_pic_gen_config,
    )

    _config_dir = get_res_path("config")
    _mod(
        "gsuid_core.utils.plugins_config.gs_config",
        StringConfig=RealStringConfig,
        pic_gen_config=make_pic_gen_config(_config_dir),
        database_config=make_database_config(_config_dir),
    )
    # mihoyo 扫码专用（DNAUID 未使用）：仅保证 import 通过
    _mod("gsuid_core.utils.api.mys_api", mys_api=Dummy())
    _mod("gsuid_core.help.utils", register_help=lambda *a, **k: HELP_ENTRIES.append((a, k)))
    _mod("gsuid_core.status", register_status=lambda *a, **k: None)
    _mod("gsuid_core.status.plugin_status",
         register_status=lambda *a, **k: STATUS_ENTRIES.append((a, k)))
    # NOTE: gsuid_core.utils.image.* 真实模块由白名单 hook 按需装载，此处不再预装
    _mod("gsuid_core.utils.database.startup", exec_list=[])
    if not _rg.is_real_available("gsuid_core.utils.database.base_models"):
        _mod("gsuid_core.utils.database.base_models",
             Bind=Dummy, User=Dummy, BaseIDModel=Dummy, with_session=with_session)
    _mod("gsuid_core.utils.cookie_manager.qrlogin", get_qrcode_base64=get_qrcode_base64)
    _mod("gsuid_core.webconsole.mount_app",
         PageSchema=Dummy, GsAdminModel=Dummy, site=site)

    sys.meta_path.insert(0, _FallbackFinder())
    # 白名单必须在兜底之前：重新插到最 front，保证真实模块优先命中
    _rg.install_hook()
    # 真实 core_font 需要的 MiSansVF.ttf 未入库时，回退到插件自带字体
    _rg.ensure_core_font()
    for _finder in [f for f in sys.meta_path if isinstance(f, _FallbackFinder)]:
        sys.meta_path.remove(_finder)
        sys.meta_path.append(_finder)
    _INSTALLED = True


async def run_startup(trace: list[dict] | None = None) -> list[dict]:
    """运行收集到的 ``on_core_start`` 钩子（结果写入 trace 做工具回显）。"""
    results: list[dict] = []
    for func in list(STARTUP_FUNCS):
        name = getattr(func, "__name__", repr(func))
        try:
            if asyncio.iscoroutinefunction(func):
                await func()
            else:
                func()
            results.append({"tool": f"startup:{name}", "ok": True})
        except Exception as exc:  # noqa: BLE001
            results.append({"tool": f"startup:{name}", "ok": False, "error": repr(exc)[:300]})
    if trace is not None:
        trace.extend({"kind": "tool", **r} for r in results)
    return results
