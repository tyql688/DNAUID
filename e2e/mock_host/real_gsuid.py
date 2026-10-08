"""装载上游 gsuid_core 的真实绘制链路。

``e2e/mock_host/_real/`` 下是 pin 到固定 commit 的上游源码（见
``sync_real_gsuid.py`` 与 ``_real/PINNED.txt``），这里用白名单 import hook
把以下 ``gsuid_core.*`` 模块指向真实实现，其余仍走 mock 存根：

- help.draw_new_plugin_help / help.model（真实帮助图版式）
- utils.image.convert / image_tools / image.utils（真实图片编解码）
- utils.fonts.fonts（真实字体加载；20MB 的 MiSansVF.ttf 不入库，
  缺失时回退到插件自带的 dna_fonts.ttf）
- pool / i18n（真实线程池装饰器与文案函数）

环境相关的两处用垫片解决（见 ``stubs.install``）：
``gs_config.pic_gen_config``（图片质量）与 ``data_store.get_res_path``。
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

REAL_DIR = Path(__file__).parent / "_real"

REAL_SUBMODULES = {
    "gsuid_core.pool": "pool.py",
    "gsuid_core.i18n": "i18n.py",
    "gsuid_core.help.model": "help/model.py",
    "gsuid_core.help.draw_new_plugin_help": "help/draw_new_plugin_help.py",
    "gsuid_core.utils.fonts.fonts": "utils/fonts/fonts.py",
    "gsuid_core.utils.image.convert": "utils/image/convert.py",
    "gsuid_core.utils.image.image_tools": "utils/image/image_tools.py",
    "gsuid_core.utils.image.utils": "utils/image/utils.py",
    "gsuid_core.utils.database.base_models": "utils/database/base_models.py",
    "gsuid_core.utils.database.write_gate": "utils/database/write_gate.py",
    "gsuid_core.utils.cookie_manager.qrlogin": "utils/cookie_manager/qrlogin.py",
    "gsuid_core.utils.plugins_config.models": "utils/plugins_config/models.py",
    "gsuid_core.utils.download_resource.download_file": "utils/download_resource/download_file.py",
}

_font_note = "not initialized"


class _RealGsuidFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: Any = None, target: Any = None):  # type: ignore[no-untyped-def]
        rel = REAL_SUBMODULES.get(fullname)
        if rel is None or fullname in sys.modules:
            return None
        file = REAL_DIR / rel
        if not file.exists():
            return None
        return importlib.util.spec_from_file_location(fullname, str(file))


_INSTALLED = False


def install_hook() -> None:
    """安装白名单 hook（必须排在通用 Dummy 兜底之前）。"""
    global _INSTALLED
    if _INSTALLED:
        return
    for finder in sys.meta_path:
        if isinstance(finder, _RealGsuidFinder):
            _INSTALLED = True
            return
    sys.meta_path.insert(0, _RealGsuidFinder())
    _INSTALLED = True


def ensure_core_font() -> str:
    """保证真实 ``core_font`` 可用，返回实际使用的字体说明。"""
    global _font_note
    try:
        import importlib as _il  # noqa: PLC0415

        # 必须用完整路径导入：Dummy 模块的 __getattr__ 会截胡 from-import
        real_fonts = _il.import_module("gsuid_core.utils.fonts.fonts")
    except Exception as exc:  # noqa: BLE001
        _font_note = f"real fonts module unavailable: {exc!r}"
        return _font_note
    bundled = REAL_DIR / "utils" / "fonts" / "MiSansVF.ttf"
    if bundled.exists():
        _font_note = f"upstream MiSansVF ({bundled.stat().st_size // 1024}KB)"
        return _font_note
    # 回退：插件自带的中文字体（仓库内真实文件，非占位）
    for candidate in (
        Path("DNAUID/utils/fonts/dna_fonts.ttf"),
        Path("DNAUID/utils/fonts/arial-unicode-ms-bold.ttf"),
    ):
        if candidate.exists():
            real_fonts.FONT_ORIGIN_PATH = candidate.resolve()
            _font_note = f"fallback to {candidate} (MiSansVF.ttf not vendored)"
            return _font_note
    try:
        import DNAUID  # type: ignore  # noqa: PLC0415

        fallback = Path(DNAUID.__file__).parent / "utils" / "fonts" / "dna_fonts.ttf"
        if fallback.exists():
            real_fonts.FONT_ORIGIN_PATH = fallback
            _font_note = f"fallback to {fallback} (MiSansVF.ttf not vendored)"
            return _font_note
    except Exception:  # noqa: BLE001
        pass
    _font_note = "no CJK font available; help drawing may fail"
    return _font_note


def is_real_available(module_name: str) -> bool:
    """上游真实模块文件是否存在（未被存根遮蔽时 hook 才会生效）。"""
    rel = REAL_SUBMODULES.get(module_name)
    return bool(rel) and (REAL_DIR / rel).exists() and module_name not in sys.modules


def get_real_function(module_name: str, attr: str) -> tuple[Any, str]:
    """取真实函数，返回 ``(func, note)``；失败时抛异常由调用方回退。"""
    install_hook()
    module = importlib.import_module(module_name)
    return getattr(module, attr), f"real {module_name}.{attr}"


def load_status() -> dict[str, Any]:
    """供 /api/state 展示：哪些真实模块可装载。"""
    available = {name: (REAL_DIR / rel).exists() for name, rel in REAL_SUBMODULES.items()}
    return {
        "real_dir": str(REAL_DIR),
        "modules": available,
        "font": _font_note,
    }


def _placeholder_module(name: str) -> ModuleType:  # pragma: no cover
    raise ImportError(f"real gsuid module not vendored: {name}")
