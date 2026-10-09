"""装载上游 gsuid_core 的真实绘制链路。

``e2e/mock_host/_real/`` 下是从本地 core 同步来的源码（见
``sync_real_gsuid.py`` 与 ``_real/PINNED.txt``），这里用白名单 import hook
把以下 ``gsuid_core.*`` 模块指向真实实现，其余仍走 mock 存根：

- help.draw_new_plugin_help / help.model（真实帮助图版式）
- utils.image.convert / image_tools / image.utils（真实图片编解码）
- utils.fonts.fonts（真实字体加载；20MB 的 MiSansVF.ttf 不入库，
  换成插件自带的 dna_fonts.ttf）
- pool / i18n（真实线程池装饰器与文案函数）

环境相关的两处用垫片解决（见 ``stubs.install``）：
``gs_config.pic_gen_config``（图片质量）与 ``data_store.get_res_path``。
"""

from __future__ import annotations

import sys
import importlib
import importlib.abc
import importlib.util
from typing import Any
from pathlib import Path

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

PLUGIN_FONT = Path(__file__).parents[2] / "DNAUID" / "utils" / "fonts" / "dna_fonts.ttf"


class _RealGsuidFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: Any = None, target: Any = None):  # type: ignore[no-untyped-def]
        rel = REAL_SUBMODULES.get(fullname)
        if rel is None or fullname in sys.modules:
            return None
        return importlib.util.spec_from_file_location(fullname, str(REAL_DIR / rel))


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


def ensure_core_font() -> None:
    """真实 core_font 用的 MiSansVF.ttf 有 20MB 不入库，换成插件自带的中文字体。"""
    # 必须用完整路径导入：Dummy 模块的 __getattr__ 会截胡 from-import
    fonts = importlib.import_module("gsuid_core.utils.fonts.fonts")
    fonts.FONT_ORIGIN_PATH = PLUGIN_FONT
