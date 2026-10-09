from __future__ import annotations

import asyncio

from PIL import Image, ImageDraw, ImageFont

from .service import Board, BuildRow
from ..utils.image import (
    COLOR_GOLD,
    COLOR_WHITE,
    COLOR_GOLDENROD,
    get_div,
    add_footer,
    get_dna_bg,
    get_avatar_img,
    get_qq_avatar_img,
    get_smooth_drawer,
)
from ..utils.dob.pack import source_line
from ..dna_config.prefix import dna_prefix
from ..utils.fonts.dna_fonts import (
    emoji_font,
    dna_font_20,
    dna_font_22,
    dna_font_24,
    dna_font_26,
    dna_font_30,
    dna_font_44,
)

W = 1000
PAD = 50
TOP = 30
# 页脚条（22）+ 数据来源行（22）+ 底边（20），再留 36 与内容隔开
BOTTOM = 100
ROW_HEIGHT = 118
DIM = (205, 205, 212)
FAINT = (150, 150, 160)
TILE_BG = (38, 44, 62, 235)
BADGE_BG = (23, 48, 95, 255)
BADGE_TEXT = (147, 197, 253)


def _rounded_tile(size: tuple[int, int], radius: int, fill: tuple[int, int, int, int]) -> Image.Image:
    tile = Image.new("RGBA", size, (0, 0, 0, 0))
    get_smooth_drawer().rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=fill, target=tile)
    return tile


def _initial_tile(text: str, size: int) -> Image.Image:
    """头像取不到时用首字方章。"""
    tile = _rounded_tile((size, size), size // 4, TILE_BG)
    first = text.strip()[:1] or "?"
    ImageDraw.Draw(tile).text((size / 2, size / 2), first, fill=COLOR_WHITE, font=dna_font_30, anchor="mm")
    return tile


def _circle(image: Image.Image, size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(image.resize((size, size), Image.Resampling.LANCZOS), (0, 0), mask)
    return out


async def _char_head(row: BuildRow, size: int = 64) -> Image.Image:
    avatar = await get_avatar_img(row.char_id, row.head_url)
    # 本地没缓存又没有直链时是空白图
    if avatar.getbbox() is None:
        return _initial_tile(row.char_name, size)
    return _circle(avatar, size)


async def _author_head(row: BuildRow, size: int = 28) -> Image.Image:
    head = await get_qq_avatar_img(row.author_qq)
    return _circle(head, size) if head is not None else _initial_tile(row.author, size)


def _clip(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """按像素宽度截断，尾部加省略号。"""
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text + "…"


def _emoji_sprite(emoji: str, target_size: int = 52) -> Image.Image:
    probe = ImageDraw.Draw(Image.new("RGBA", (218, 218), (0, 0, 0, 0)))
    left, top, right, bottom = probe.textbbox((0, 0), emoji, font=emoji_font, anchor="lt")
    width, height = int(max(1, right - left)), int(max(1, bottom - top))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text((-left, -top), emoji, font=emoji_font, embedded_color=True)
    scale = target_size / max(width, height)
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return canvas.resize(size, Image.Resampling.LANCZOS)


def _header(title: str, emoji: str) -> Image.Image:
    head = Image.new("RGBA", (W, 120), (0, 0, 0, 0))
    sprite = _emoji_sprite(emoji)
    head.alpha_composite(sprite, (PAD, (120 - sprite.height) // 2))
    x = PAD + sprite.width + 16
    ImageDraw.Draw(head).text((x, 60), title, fill=COLOR_WHITE, font=dna_font_44, anchor="lm")
    return head


def _name_badge(line: Image.Image, draw: ImageDraw.ImageDraw, text: str, x: int, y: int) -> int:
    """角色名小蓝章，返回章宽度。"""
    label = _clip(draw, text, dna_font_20, 150)
    width = int(draw.textlength(label, font=dna_font_20)) + 20
    badge = _rounded_tile((width, 30), 6, BADGE_BG)
    ImageDraw.Draw(badge).text((width / 2, 15), label, fill=BADGE_TEXT, font=dna_font_20, anchor="mm")
    line.alpha_composite(badge, (x, y))
    return width


async def _row_line(row: BuildRow, char_head: Image.Image) -> Image.Image:
    """一行：角色头像 / 名章 + 标题 / 作者 + 日期 / 目标函数 / DPS / 名次。"""
    line = Image.new("RGBA", (W, ROW_HEIGHT), (0, 0, 0, 0))
    line.alpha_composite(char_head, (PAD, (ROW_HEIGHT - 64) // 2))
    draw = ImageDraw.Draw(line)
    badge_width = _name_badge(line, draw, row.char_name, PAD + 84, 18)
    title_x = PAD + 84 + badge_width + 16
    draw.text((title_x, 33), _clip(draw, row.title, dna_font_26, W - title_x - 300), COLOR_WHITE, dna_font_26, "lm")
    line.alpha_composite(await _author_head(row), (PAD + 84, 72))
    meta = _clip(draw, f"{row.author}  {row.update_at}", dna_font_22, 320)
    draw.text((PAD + 84 + 36, 86), meta, fill=DIM, font=dna_font_22, anchor="lm")
    draw.text((W - PAD, 24), _clip(draw, row.target_fn, dna_font_20, 220), fill=FAINT, font=dna_font_20, anchor="rm")
    draw.text((W - PAD, 58), f"{row.dps:,}", fill=COLOR_GOLDENROD, font=dna_font_26, anchor="rm")
    draw.text((W - PAD, 92), f"#{row.rank}", fill=DIM, font=dna_font_22, anchor="rm")
    return line


def _assemble(blocks: list[Image.Image]) -> Image.Image:
    card = get_dna_bg(W, TOP + sum(block.height for block in blocks) + BOTTOM, "bg")
    y = TOP
    for block in blocks:
        card.alpha_composite(block, (0, y))
        y += block.height
    return add_footer(card, 600, source_line=source_line())


async def draw_board_card(boards: list[Board]) -> Image.Image:
    blocks = [_header("DOB 榜单", "🏆")]
    for index, board in enumerate(boards):
        if index:
            blocks.append(get_div())
        bar = Image.new("RGBA", (W, 84), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(bar)
        bar_draw.text((PAD, 42), _clip(bar_draw, board.name, dna_font_30, 640), COLOR_GOLD, dna_font_30, "lm")
        bar_draw.text((W - PAD, 42), f"{len(board.rows)} 席", fill=FAINT, font=dna_font_24, anchor="rm")
        blocks.append(bar)
        # 角色头像走本地缓存，逐个取避免同图并发下载；作者 QQ 头像要联网，并发取
        heads = [await _char_head(row) for row in board.rows]
        blocks += await asyncio.gather(*(_row_line(row, head) for row, head in zip(board.rows, heads)))
    return _assemble(blocks)


async def draw_build_list_card(char_name: str, rows: list[BuildRow]) -> Image.Image:
    """角色构筑列表，序号对应「DOB角色构筑 序号」。"""
    char_head = await _char_head(rows[0])
    blocks = [_header(f"{char_name}构筑", "📋")]
    blocks += await asyncio.gather(*(_row_line(row, char_head) for row in rows))
    hint = Image.new("RGBA", (W, 60), (0, 0, 0, 0))
    ImageDraw.Draw(hint).text(
        (PAD, 30),
        f"发送「{dna_prefix()}DOB{char_name}构筑 序号」查看指定构筑",
        fill=FAINT,
        font=dna_font_22,
        anchor="lm",
    )
    blocks.append(hint)
    return _assemble(blocks)
