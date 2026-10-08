"""mock 宿主的帮助图渲染：复刻真实宿主 ``get_new_help`` 的版式.

用插件真实传入的 ``plugin_help``（help.json）、命令图标、banner/底图，
逐组绘制指令表，保证 ``dna帮助`` 回显的是插件的真实指令，而非占位图。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

W = 1000
MARGIN = 36
BANNER_H = 236
COLUMNS = 2

BG = (18, 20, 28, 255)
CARD = (30, 34, 46, 255)
CARD_LINE = (58, 64, 84, 255)
TXT = (235, 238, 245, 255)
DIM = (158, 165, 184, 255)
ACCENT = (124, 140, 255, 255)
BAR_COLORS = [
    (124, 140, 255, 255),
    (63, 185, 127, 255),
    (232, 192, 122, 255),
    (224, 101, 101, 255),
    (86, 200, 220, 255),
]

_font_cache: dict[int, Any] = {}
_font_path: Path | None = None


def _find_font() -> Path | None:
    global _font_path
    if _font_path is not None:
        return _font_path
    candidates: list[Path] = []
    try:
        import DNAUID  # type: ignore  # noqa: PLC0415

        candidates.append(Path(DNAUID.__file__).parent / "utils" / "fonts" / "dna_fonts.ttf")
    except Exception:  # noqa: BLE001
        pass
    candidates += [
        Path("DNAUID/utils/fonts/dna_fonts.ttf"),
        Path("DNAUID/utils/fonts/arial-unicode-ms-bold.ttf"),
    ]
    for path in candidates:
        if path.exists():
            _font_path = path
            return path
    return None


def _font(size: int):  # type: ignore[no-untyped-def]
    from PIL import ImageFont  # type: ignore

    if size not in _font_cache:
        path = _find_font()
        _font_cache[size] = (
            ImageFont.truetype(str(path), size=size) if path else ImageFont.load_default()
        )
    return _font_cache[size]


def _wrap(draw: Any, text: str, font: Any, max_w: int) -> list[str]:
    lines, current = [], ""
    for ch in (text or ""):
        if draw.textlength(current + ch, font=font) <= max_w:
            current += ch
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines or [""]


def _fit_cover(img: Any, w: int, h: int) -> Any:
    scale = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1))
    x = (img.width - w) // 2
    y = (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _round_mask(size: tuple[int, int], radius: int) -> Any:
    from PIL import Image, ImageDraw  # type: ignore

    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0], size[1]], radius=radius, fill=255)
    return mask


def _find_icon(icon_dir: Any, name: str) -> Path | None:
    if not icon_dir:
        return None
    base = Path(str(icon_dir))
    for candidate in (f"{name}.png", f"{name}.jpg", f"{name}.jpeg"):
        path = base / candidate
        if path.exists():
            return path
    return None


def draw_plugin_help(
    plugin_name: str = "DNAUID",
    plugin_info: dict | None = None,
    plugin_icon: Any = None,
    plugin_help: dict | None = None,
    plugin_prefix: str = "",
    help_mode: str = "dark",  # noqa: ARG001
    banner_bg: Any = None,
    banner_sub_text: str = "",
    help_bg: Any = None,
    cag_bg: Any = None,  # noqa: ARG001
    item_bg: Any = None,  # noqa: ARG001
    icon_path: Any = None,
    footer: Any = None,
    enable_cache: bool = False,  # noqa: ARG001,FBT001,FBT002
    column: int = COLUMNS,
    pm: int = 99,
) -> bytes:
    """绘制完整帮助图并返回 PNG bytes。"""
    from PIL import Image, ImageDraw, ImageFilter  # type: ignore

    groups: dict = dict(plugin_help or {})
    prefix = plugin_prefix or ""
    version = ""
    if plugin_info:
        version = "  ".join(f"{k}{v}" if v else k for k, v in plugin_info.items())

    f_title = _font(46)
    f_sub = _font(24)
    f_group = _font(30)
    f_desc = _font(22)
    f_cmd = _font(26)
    f_meta = _font(20)

    # -- 先排版，计算高度 -------------------------------------------------
    col_w = (W - MARGIN * 2 - 20) // max(column, 1)
    cards: list[list[dict]] = []
    for group_name, group in groups.items():
        items = (group or {}).get("data", []) if isinstance(group, dict) else []
        rows: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if pm < 4 and (item.get("need_admin")):
                continue
            name = str(item.get("name", ""))
            desc = str(item.get("desc", ""))
            eg = str(item.get("eg", ""))
            cmd = f"{prefix}{eg or name}"
            text_w = col_w - 118
            desc_lines = _wrap(ImageDraw.Draw(Image.new("RGB", (8, 8))), desc, f_desc, text_w)[:3]
            card_h = max(104, 30 + len(desc_lines) * 30 + 30)
            rows.append({
                "name": name, "desc_lines": desc_lines, "cmd": cmd,
                "lock": bool(item.get("need_admin")), "h": card_h,
                "icon": _find_icon(icon_path, name),
            })
        group_desc = str((group or {}).get("desc", "")) if isinstance(group, dict) else ""
        cards.append({"group": str(group_name), "desc": group_desc, "rows": rows})

    body_h = 0
    for block in cards:
        n = len(block["rows"])
        rows_h = sum(max(block["rows"][i]["h"], block["rows"][i + 1]["h"] if i + 1 < n else 0)
                     for i in range(0, n, column)) if n else 0
        block["h"] = 84 + rows_h + (16 * ((n + column - 1) // column)) + 10
        body_h += block["h"]

    footer_h = 120
    H = BANNER_H + body_h + footer_h + 40
    canvas = Image.new("RGBA", (W, H), BG)
    if help_bg is not None:
        try:
            canvas = _fit_cover(help_bg.convert("RGBA"), W, H)
            dark = Image.new("RGBA", (W, H), (10, 12, 20, 190))
            canvas = Image.alpha_composite(canvas, dark)
        except Exception:  # noqa: BLE001
            pass
    draw = ImageDraw.Draw(canvas)

    # -- banner ------------------------------------------------------------
    if banner_bg is not None:
        try:
            banner = _fit_cover(banner_bg.convert("RGBA"), W, BANNER_H)
            banner = banner.filter(ImageFilter.GaussianBlur(1))
            canvas.paste(banner, (0, 0), banner)
            draw = ImageDraw.Draw(canvas)
        except Exception:  # noqa: BLE001
            pass
    draw.rectangle([0, 0, W, BANNER_H], fill=(10, 12, 20, 110))
    if plugin_icon is not None:
        try:
            icon = plugin_icon.convert("RGBA").resize((128, 128))
            icon.putalpha(_round_mask((128, 128), 28))
            canvas.paste(icon, (MARGIN + 8, 52), icon)
            draw = ImageDraw.Draw(canvas)
        except Exception:  # noqa: BLE001
            pass
    tx = MARGIN + 160
    draw.text((tx, 56), plugin_name, font=f_title, fill=TXT)
    if version:
        draw.text((tx, 118), version.strip(), font=f_sub, fill=DIM)
    draw.text((tx, 152), f"指令前缀：{prefix}帮助", font=f_sub, fill=ACCENT)
    if banner_sub_text:
        draw.text((tx, 184), str(banner_sub_text), font=f_meta, fill=DIM)

    # -- 分组卡片 -----------------------------------------------------------
    y = BANNER_H + 16
    for index, block in enumerate(cards):
        bar = BAR_COLORS[index % len(BAR_COLORS)]
        draw.rounded_rectangle([MARGIN, y, W - MARGIN, y + block["h"]], radius=18, fill=(24, 27, 38, 235))
        draw.rectangle([MARGIN + 18, y + 22, MARGIN + 26, y + 52], fill=bar)
        draw.text((MARGIN + 40, y + 16), block["group"], font=f_group, fill=TXT)
        if block["desc"]:
            for line in _wrap(draw, block["desc"], f_meta, W - MARGIN * 2 - 60)[:1]:
                draw.text((MARGIN + 40, y + 54), line, font=f_meta, fill=DIM)
        cy = y + 92
        rows = block["rows"]
        for i in range(0, len(rows), column):
            line = rows[i:i + column]
            line_h = max(r["h"] for r in line)
            for j, card in enumerate(line):
                x0 = MARGIN + 18 + j * (col_w + 20)
                x1 = x0 + col_w
                draw.rounded_rectangle([x0, cy, x1, cy + line_h], radius=14, fill=CARD, outline=CARD_LINE, width=2)
                # 图标
                ix, iy, isize = x0 + 14, cy + (line_h - 72) // 2, 72
                icon_img = None
                if card["icon"] is not None:
                    try:
                        icon_img = Image.open(card["icon"]).convert("RGBA").resize((isize, isize))
                    except Exception:  # noqa: BLE001
                        icon_img = None
                if icon_img is not None:
                    icon_img.putalpha(_round_mask((isize, isize), 16))
                    canvas.paste(icon_img, (ix, iy), icon_img)
                else:
                    draw.ellipse([ix, iy, ix + isize, iy + isize], fill=bar)
                    ch = (card["name"] or "?")[:1]
                    bbox = draw.textbbox((0, 0), ch, font=f_cmd)
                    draw.text((ix + (isize - (bbox[2] - bbox[0])) / 2, iy + 12), ch, font=f_cmd, fill=(16, 18, 26, 255))
                draw = ImageDraw.Draw(canvas)
                tx2 = x0 + 100
                title = card["cmd"] + (" 🔒" if card["lock"] else "")
                draw.text((tx2, cy + 10), title[:18], font=f_cmd, fill=TXT)
                for k, line_text in enumerate(card["desc_lines"]):
                    draw.text((tx2, cy + 46 + k * 30), line_text, font=f_desc, fill=DIM)
            cy += line_h + 16
        y += block["h"] + 12

    # -- 页脚 ----------------------------------------------------------------
    if footer is not None:
        try:
            fw = Image.open(footer) if isinstance(footer, (str, Path)) else footer
            fw = fw.convert("RGBA")
            scale = min(1.0, (W - MARGIN * 2) / fw.width)
            fw = fw.resize((int(fw.width * scale), int(fw.height * scale)))
            canvas.paste(fw, ((W - fw.width) // 2, H - fw.height - 16), fw)
            draw = ImageDraw.Draw(canvas)
        except Exception:  # noqa: BLE001
            pass
    draw.text((MARGIN, H - 34), "mock-host 渲染 · 与真实宿主版式一致", font=f_meta, fill=(110, 116, 136, 255))

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
