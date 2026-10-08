"""DOB 榜单/构筑图片渲染：与角色卡同视觉语言（bg2 底 + 页脚来源行），密度克制。

三张卡共用页眉/行/页脚构件：榜单（多版块名次行）、角色构筑列表（序号行）、
单构筑（标题 + 四维双暴 + 目标 DPS）。
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from ..utils.image import (
    COLOR_GOLD,
    COLOR_WHITE,
    COLOR_GOLDENROD,
    get_div,
    add_footer,
    get_dna_bg,
    get_avatar_img,
    get_smooth_drawer,
)
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
DIM = (205, 205, 212)
FAINT = (150, 150, 160)
TILE_BG = (38, 44, 62, 235)
BADGE_BG = (23, 48, 95, 255)
BADGE_TX = (147, 197, 253)


def _fetch_bytes(url: str, timeout: int = 15) -> bytes | None:
    """头像直链下载（不走本地 bundling，失败返回 None 由调用方垫底）。"""
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DNAUID-board/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return data or None
    except Exception:
        return None


def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    return mask


def _initial_tile(text: str, size: int) -> Image.Image:
    """下载失败垫底：首字方章（仅兜底，不作首选）。"""
    tile = _rounded_tile((size, size), size // 4, TILE_BG)
    draw = ImageDraw.Draw(tile)
    first = (text or "?").strip()[:1] or "?"
    draw.text((size / 2, size / 2), first, fill=COLOR_WHITE, font=dna_font_30, anchor="mm")
    return tile


async def _head_image(char_id: int | str | None, name: str, head_url: str | None = None, size: int = 64) -> Image.Image:
    """角色头图：info 卡同一份本地头像；缺失时 head 直链补进同一文件，再缺垫底。"""
    if char_id is None:
        return _initial_tile(name, size)
    try:
        avatar = await get_avatar_img(char_id, head_url)
        avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(avatar, (0, 0), _circle_mask(size))
        # 空白图（缓存缺失且无可用直链）则垫底，避免透明洞
        if avatar.getbbox() is None:
            return _initial_tile(name, size)
        return out
    except OSError:
        return _initial_tile(name, size)


def _qq_avatar(qq: str | int | None, name: str, size: int = 28) -> Image.Image:
    """QQ 头像直链，失败垫底。"""
    from io import BytesIO

    from .service import qq_avatar_url

    url = qq_avatar_url(qq)
    data = _fetch_bytes(url) if url else None
    if data:
        try:
            with Image.open(BytesIO(data)) as img:
                head = img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
            out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            out.paste(head, (0, 0), _circle_mask(size))
            return out
        except OSError:
            pass
    return _initial_tile(name, size)


def _clip(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    """按像素宽度截断，尾部加省略号。"""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…" if text else "…"


def _rounded_tile(size: tuple[int, int], radius: int, fill: tuple) -> Image.Image:
    tile = Image.new("RGBA", size, (0, 0, 0, 0))
    get_smooth_drawer().rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=fill, target=tile)
    return tile


def _emoji_sprite(emoji: str, target_size: int = 52) -> Image.Image:
    d = ImageDraw.Draw(Image.new("RGBA", (218, 218), (0, 0, 0, 0)))
    bbox = d.textbbox((0, 0), emoji, font=emoji_font, anchor="lt")
    w, h = int(max(1, bbox[2] - bbox[0])), int(max(1, bbox[3] - bbox[1]))
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dc = ImageDraw.Draw(canvas)
    try:
        dc.text((-bbox[0], -bbox[1]), emoji, font=emoji_font, embedded_color=True)
    except TypeError:
        dc.text((-bbox[0], -bbox[1]), emoji, font=emoji_font, fill=(0, 0, 0, 255))
    scale = target_size / max(w, h)
    return canvas.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)


def _header(title: str, emoji: str | None = None) -> Image.Image:
    """页眉：emoji + 大标题，高度随内容固定 120。"""
    head = Image.new("RGBA", (W, 120), (0, 0, 0, 0))
    x = PAD
    if emoji:
        sprite = _emoji_sprite(emoji)
        head.alpha_composite(sprite, (x, (120 - sprite.height) // 2))
        x += sprite.width + 16
    ImageDraw.Draw(head).text((x, 60), title, fill=COLOR_WHITE, font=dna_font_44, anchor="lm")
    return head


def _footer(card: Image.Image, pack_version: str | None) -> Image.Image:
    line = "Data Source: DNA Builder (DOB)"
    if pack_version:
        line += f" | Pack Version: {pack_version}"
    return add_footer(card, 600, source_line=line)


def _name_badge(line: Image.Image, draw: ImageDraw.ImageDraw, text: str, x: int, y: int) -> int:
    """角色名方章（上游同款小蓝章），返回章宽度。"""
    label = _clip(draw, text, dna_font_20, 150)
    w = int(draw.textlength(label, font=dna_font_20)) + 20
    badge = _rounded_tile((w, 30), 6, BADGE_BG)
    ImageDraw.Draw(badge).text((w / 2, 15), label, fill=BADGE_TX, font=dna_font_20, anchor="mm")
    line.alpha_composite(badge, (x, y))
    return w


def _paint_rank_row(
    line: Image.Image,
    avatar: Image.Image,
    badge_text: str,
    title: str,
    author: str,
    author_qq,
    update_at: str,
    target_fn: str,
    dps_str: str,
    rank_no: int,
) -> None:
    """榜单/列表共用行：头像/名章标题/作者日期/目标函数/DPS/名次（上游同粒度）。"""
    h = line.height
    line.alpha_composite(avatar, (PAD, (h - 64) // 2))
    draw = ImageDraw.Draw(line)
    bw = _name_badge(line, draw, badge_text, PAD + 84, 18)
    title_clipped = _clip(draw, title, dna_font_26, W - (PAD + 84 + bw + 16) - 300)
    draw.text((PAD + 84 + bw + 16, 33), title_clipped, fill=COLOR_WHITE, font=dna_font_26, anchor="lm")
    line.alpha_composite(_qq_avatar(author_qq, author), (PAD + 84, 72))
    meta = f"{author}  {update_at}".strip()
    draw.text((PAD + 84 + 36, 86), _clip(draw, meta, dna_font_22, 320), fill=DIM, font=dna_font_22, anchor="lm")
    draw.text((W - PAD, 24), _clip(draw, target_fn, dna_font_20, 220), fill=FAINT, font=dna_font_20, anchor="rm")
    draw.text((W - PAD, 58), dps_str, fill=COLOR_GOLDENROD, font=dna_font_26, anchor="rm")
    draw.text((W - PAD, 92), f"#{rank_no}", fill=DIM, font=dna_font_22, anchor="rm")


async def draw_board_image(boards: list[dict], pack_version: str | None = None) -> Image.Image:
    """榜单卡：上游 RankingView 同粒度（头像/名章标题/作者日期/目标函数/DPS/名次）。"""
    blocks: list[Image.Image] = [_header("DOB 榜单", "🏆")]
    for board in boards:
        rows = board.get("rows") or []
        bar = Image.new("RGBA", (W, 84), (0, 0, 0, 0))
        bar_draw = ImageDraw.Draw(bar)
        bar_draw.text(
            (PAD, 42),
            _clip(bar_draw, board.get("name") or "榜单", dna_font_30, 640),
            fill=COLOR_GOLD,
            font=dna_font_30,
            anchor="lm",
        )
        count = f"{len(rows)} 席"
        bar_draw.text((W - PAD, 42), count, fill=FAINT, font=dna_font_24, anchor="rm")
        blocks.append(bar)
        for row in rows:
            line = Image.new("RGBA", (W, 118), (0, 0, 0, 0))
            avatar = await _head_image(row.get("char_id"), row.get("char_name") or "", row.get("head"))
            _paint_rank_row(
                line,
                avatar,
                row.get("char_name") or "",
                row.get("title") or "",
                row.get("author") or "匿名",
                row.get("author_qq"),
                row.get("update_at") or "",
                row.get("target_fn") or "-",
                row.get("dps_str") or "0",
                row.get("rank", 0),
            )
            blocks.append(line)
        blocks.append(get_div())
    total_h = sum(b.height for b in blocks) + 240
    card = get_dna_bg(W, total_h, "bg")
    y = 30
    for block in blocks:
        card.alpha_composite(block, (0, y))
        y += block.height
    return _footer(card, pack_version)


async def draw_build_list_image(char_name: str, rows: list[dict], pack_version: str | None = None) -> Image.Image:
    """角色构筑列表卡：与榜单同行版式（序号即名次），序号与“DOBxx构筑 n”对应。"""
    blocks: list[Image.Image] = [_header(f"{char_name}构筑", "📋")]
    avatar = await _head_image(rows[0].get("char_id"), char_name, rows[0].get("head")) if rows else None
    for row in rows:
        line = Image.new("RGBA", (W, 118), (0, 0, 0, 0))
        _paint_rank_row(
            line,
            avatar,
            row.get("char_name") or char_name,
            row.get("title") or "",
            row.get("author") or "匿名",
            row.get("author_qq"),
            row.get("update_at") or "",
            row.get("target_fn") or "-",
            row.get("dps_str") or "0",
            row.get("idx", 0),
        )
        blocks.append(line)
    hint = Image.new("RGBA", (W, 60), (0, 0, 0, 0))
    ImageDraw.Draw(hint).text(
        (PAD, 30), f"发送「DOB{char_name}构筑 序号」查看指定构筑", fill=FAINT, font=dna_font_22, anchor="lm"
    )
    blocks.append(hint)
    total_h = sum(b.height for b in blocks) + 240
    card = get_dna_bg(W, total_h, "bg")
    y = 30
    for block in blocks:
        card.alpha_composite(block, (0, y))
        y += block.height
    return _footer(card, pack_version)
