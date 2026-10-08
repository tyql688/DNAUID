"""插件加载器：安装 mock 存根后导入 DNAUID 真实业务模块。

单个模块导入失败不会阻断整体（记录到 ``errors`` 并在 Web 界面展示），
以便在缺少第三方依赖的环境下仍可演示 mock 宿主链路。
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from typing import Any

from . import stubs


def _dna_packages() -> list[str]:
    try:
        import DNAUID  # noqa: PLC0415

        pkgs = [name for _, name, ispkg in pkgutil.iter_modules(DNAUID.__path__) if ispkg]
        return [f"DNAUID.{name}" for name in sorted(pkgs)]
    except Exception:  # noqa: BLE001
        return []


def ensure_demo_handlers() -> dict[str, Any]:
    """注册内置演示指令，保证 Web 聊天在插件未加载时也可交互。"""
    from gsuid_core.bot import Bot  # noqa: PLC0415
    from gsuid_core.models import Event  # noqa: PLC0415
    from gsuid_core.sv import SV  # noqa: PLC0415

    if any(h.get("func_name") == "demo_ping" for h in stubs.HANDLERS):
        return {"ok": True, "cached": True}
    sv_demo = SV("e2e演示", priority=999)

    @sv_demo.on_fullmatch("ping", block=True)
    async def demo_ping(bot: Bot, ev: Event):  # noqa: ARG001
        await bot.send("pong 🏓（mock 宿主链路正常）")

    @sv_demo.on_regex(r"^复读(?P<content>.+)$", block=True)
    async def demo_echo(bot: Bot, ev: Event):
        await bot.send(f"你说：{ev.regex_dict.get('content', '')}")

    @sv_demo.on_fullmatch("演示", block=True)
    async def demo_help(bot: Bot, ev: Event):  # noqa: ARG001
        await bot.send("mock 宿主演示指令：ping / 复读<内容>；插件指令需带前缀（如 dna帮助）")

    return {"ok": True, "cached": False}


def _purge_plugin_modules() -> None:
    """清掉已导入的插件模块，保证路由表可重建（测试/服务重启场景）。"""
    for name in [m for m in sys.modules if m == "DNAUID" or m.startswith("DNAUID.")]:
        del sys.modules[name]


def load_plugin() -> dict[str, Any]:
    """安装存根 → 导入插件 → 注册演示指令，返回加载报告。"""
    stubs.install()
    _purge_plugin_modules()
    stubs.HANDLERS.clear()
    loaded: list[str] = []
    errors: list[dict[str, str]] = []

    for mod_name in _dna_packages():
        try:
            importlib.import_module(mod_name)
            loaded.append(mod_name)
        except Exception as exc:  # noqa: BLE001,PERF203
            errors.append({"module": mod_name, "error": f"{type(exc).__name__}: {exc}"[:400]})

    # DNAUID/__init__.py 的 Plugins(...) 声明（前缀配置）也需要执行
    try:
        importlib.import_module("DNAUID")
        if "DNAUID" not in loaded:
            loaded.append("DNAUID")
    except Exception as exc:  # noqa: BLE001
        errors.append({"module": "DNAUID", "error": f"{type(exc).__name__}: {exc}"[:400]})

    demo = ensure_demo_handlers()
    return {
        "plugin": dict(stubs.PLUGIN_INFO),
        "prefixes": stubs.get_active_prefixes(),
        "handlers": len(stubs.HANDLERS),
        "loaded": loaded,
        "errors": errors,
        "demo": demo,
    }


async def init_runtime(reset_db: bool = False) -> dict[str, Any]:
    """插件 import 完成后必须调用：初始化真实数据库。"""
    from .database import init_plugin_db  # noqa: PLC0415

    return await init_plugin_db(reset=reset_db)
