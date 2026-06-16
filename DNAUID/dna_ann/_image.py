from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import quote_plus

from PIL import Image, ImageDraw, ImageFont

from gsuid_core.utils.download_resource.download_file import download

from ..utils.resource.RESOURCE_PATH import ANN_CARD_PATH

Color = tuple[int, int, int] | tuple[int, int, int, int]
Size = tuple[int, int]

DEFAULT_LINE_GAP = 8
DEFAULT_ELLIPSIS = "..."

QR_CACHE_PATH = ANN_CARD_PATH / "qr"
PREVIEW_CACHE_PATH = ANN_CARD_PATH / "preview"
DETAIL_CACHE_PATH = ANN_CARD_PATH / "detail"


def cache_name(*parts: object, ext: str = "png") -> str:
    raw = "|".join(str(part) for part in parts)
    return f"{hashlib.sha1(raw.encode('utf-8')).hexdigest()}.{ext}"


async def fetch_image(path: Path, pic_url: str, *, name: str | None = None) -> Image.Image:
    path.mkdir(parents=True, exist_ok=True)
    file_name = name or pic_url.split("/")[-1]
    target = path / file_name
    if not target.exists():
        await download(pic_url, path, file_name, tag="[DNA]")
    return Image.open(target).convert("RGBA")


async def load_qr_code(url: str, size: int = 220) -> Image.Image | None:
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={quote_plus(url)}"
    try:
        image = await fetch_image(QR_CACHE_PATH, qr_url, name=cache_name("qr", url, size))
    except OSError:
        return None
    return image.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)


def shrink_to_width(image: Image.Image, max_width: int) -> Image.Image:
    if image.width <= max_width:
        return image
    ratio = max_width / image.width
    return image.resize((int(max_width), int(image.height * ratio)), Image.Resampling.LANCZOS)


def rounded_mask(size: Size, radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def line_height(font: ImageFont.FreeTypeFont) -> int:
    return sum(font.getmetrics())


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int | None = None,
    ellipsis: str = DEFAULT_ELLIPSIS,
) -> list[str]:
    lines: list[str] = []
    raw_lines = text.splitlines() if text else [""]
    for raw_line in raw_lines:
        current = ""
        for char in raw_line:
            trial = f"{current}{char}"
            width = draw.textbbox((0, 0), trial, font=font)[2]
            if current and width > max_width:
                lines.append(current)
                current = char
            else:
                current = trial
        lines.append(current if current else " ")

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + ellipsis
    return lines


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Color,
    max_width: int,
    *,
    line_gap: int = DEFAULT_LINE_GAP,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width, max_lines)
    text_height = line_height(font)
    for index, line in enumerate(lines):
        draw.text((x, y), line, font=font, fill=fill)
        y += text_height
        if index != len(lines) - 1:
            y += line_gap
    return y


def round_avatar(avatar: Image.Image, size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    head = avatar.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    canvas.paste(head, (0, 0), mask)
    return canvas
