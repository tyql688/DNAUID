"""把外层 gsuid_core 工作区里 mock 宿主要装载的真实模块与帮助图素材同步到 ``_real/``。

插件开发时放在 ``gsuid_core/plugins/DNAUID`` 下，直接复制同一棵树里的文件，
保证 e2e 跑的就是当前 core 的代码（``tests/test_real_sync.py`` 会检查是否一致）。

用法：``python e2e/mock_host/sync_real_gsuid.py``
"""

from __future__ import annotations

import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e2e.mock_host.real_gsuid import REAL_DIR, REAL_SUBMODULES  # noqa: E402

# 插件在 <仓库>/gsuid_core/plugins/DNAUID，往上两级是 core 的包目录
CORE_PKG = ROOT.parents[1]
# 真实帮助图版式依赖的底图/装饰素材（共约 470KB）
TEXTURES = (
    "banner_bg_dark.jpg",
    "banner_bg_light.jpg",
    "bg_dark.jpg",
    "bg_light.jpg",
    "cag_bg_dark.png",
    "cag_bg_light.png",
    "footer_dark.png",
    "footer_light.png",
    "highlight.png",
    "item_bg_dark.png",
    "item_bg_light.png",
    "item_dark.png",
    "item_light.png",
)


def inside_core() -> bool:
    return (CORE_PKG / "help" / "draw_new_plugin_help.py").is_file()


def synced_files() -> list[str]:
    return [*REAL_SUBMODULES.values(), *(f"help/texture2d/{name}" for name in TEXTURES)]


def main() -> int:
    if not inside_core():
        print(f"FAIL 没找到 gsuid_core（{CORE_PKG}），需要把插件放在 gsuid_core/plugins/ 下运行")
        return 1
    commit = subprocess.run(
        ["git", "-C", str(CORE_PKG), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    for rel in synced_files():
        dest = REAL_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CORE_PKG / rel, dest)
        print(f"OK {rel}")
    (REAL_DIR / "PINNED.txt").write_text(
        f"commit={commit}\nsource=local gsuid_core working tree\n"
        f"files={','.join(REAL_SUBMODULES.values())}\n"
        "license=GPL-3.0-or-later (same as DNAUID)\n",
        encoding="utf-8",
    )
    # MiSansVF.ttf 有 20MB 不入库，real_gsuid.ensure_core_font 换成插件自带字体
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
