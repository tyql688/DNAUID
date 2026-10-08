"""同步上游 gsuid_core 的真实帮助绘制链路（pin 到固定 commit）。

只取纯 PIL 绘制链路所需的少量文件，放到 ``e2e/mock_host/_real/`` 下提交，
mock 宿主通过白名单 import hook 直接调用**真实的** ``get_new_help``，
而不是自己重写版式。

用法：``uv run --group e2e e2e/mock_host/sync_real_gsuid.py``
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

PINNED_COMMIT = "fb80b874533c23b565a74ebd8549ce09e4742a55"
BASE = f"https://raw.githubusercontent.com/Genshin-bots/gsuid_core/{PINNED_COMMIT}/gsuid_core"

# 上游相对路径 -> 本地相对路径（_real/ 下保持同名，hook 按原模块名装载）
FILES = [
    "help/model.py",
    "help/draw_new_plugin_help.py",
    "utils/fonts/fonts.py",
    "utils/image/convert.py",
    "utils/image/image_tools.py",
    "utils/image/utils.py",
    "pool.py",
    "i18n.py",
    "utils/database/base_models.py",
    "utils/database/write_gate.py",
    "utils/cookie_manager/qrlogin.py",
    "utils/plugins_config/models.py",
    "utils/download_resource/download_file.py",
]

# 真实帮助图版式依赖的底图/装饰素材（共约 470KB，一并入库）
TEXTURES = [
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
]

REAL_DIR = Path(__file__).parent / "_real"


def _fetch(rel: str) -> str:
    url = f"{BASE}/{rel}"
    req = urllib.request.Request(url, headers={"User-Agent": "DNAUID-e2e-sync"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def main() -> int:
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    (REAL_DIR / "PINNED.txt").write_text(
        f"commit={PINNED_COMMIT}\nsource=https://github.com/Genshin-bots/gsuid_core\n"
        f"files={','.join(FILES)}\n"
        "license=GPL-3.0-or-later (same as DNAUID)\n",
        encoding="utf-8",
    )
    ok = True
    for rel in FILES:
        try:
            text = _fetch(rel)
            dest = REAL_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
            print(f"OK {rel} ({len(text)} chars)")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"FAIL {rel}: {exc!r}")
    for name in TEXTURES:
        try:
            url = f"{BASE}/help/texture2d/{name}"
            req = urllib.request.Request(url, headers={"User-Agent": "DNAUID-e2e-sync"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                blob = resp.read()
            dest = REAL_DIR / "help" / "texture2d" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            print(f"OK help/texture2d/{name} ({len(blob)} bytes)")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"FAIL help/texture2d/{name}: {exc!r}")
    # 字体 20MB 不入库：运行时缺失则回退到插件自带字体（见 real_gsuid.py）
    print("note: MiSansVF.ttf (20MB) is NOT vendored; fallback font is used when absent.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
