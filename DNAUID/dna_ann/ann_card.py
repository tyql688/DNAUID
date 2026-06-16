from __future__ import annotations

import time
from pathlib import Path

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.utils.image.convert import convert_img

from .utils import (
    LIST_DISPLAY_LIMIT,
    pick_time,
    get_post_url,
    pick_preview,
    pick_subject,
    extract_blocks,
    fetch_ann_list,
    format_post_time,
    post_time_to_timestamp,
)
from ..utils import dna_api
from ._image import (
    DETAIL_CACHE_PATH,
    PREVIEW_CACHE_PATH,
    wrap_text,
    cache_name,
    fetch_image,
    line_height,
    load_qr_code,
    round_avatar,
    rounded_mask,
    draw_text_block,
    shrink_to_width,
)
from ..utils.image import (
    COLOR_GOLDENROD,
    COLOR_FIRE_BRICK,
    COLOR_PALE_GOLDENROD,
    get_dna_bg,
)
from ..dna_config.prefix import DNA_PREFIX
from ..utils.fonts.dna_fonts import (
    unicode_font_18,
    unicode_font_22,
    unicode_font_24,
    unicode_font_26,
    unicode_font_28,
    unicode_font_60,
)

WIDTH = 1080
PADDING = 40
GRID_GAP = 24
CARD_RADIUS = 22
PAGE_LIMIT = 6000

GRID_COLS = 3

# DNA 深色面板配色
COLOR_PANEL_DARK = (22, 18, 36, 220)
COLOR_PANEL_BORDER = (90, 70, 130, 180)
COLOR_TITLE_LIGHT = (245, 240, 225)
COLOR_TEXT_LIGHT = (210, 205, 220)
COLOR_MUTED_LIGHT = (150, 145, 175)
COLOR_DIVIDER_DARK = (95, 80, 130, 180)

_OFFICIAL_AVATAR = Path(__file__).parent / "texture2d" / "dna_official_avatar.jpeg"


async def _load_preview(url: str, width: int, height: int) -> Image.Image | None:
    if not url:
        return None
    try:
        image = await fetch_image(PREVIEW_CACHE_PATH, url, name=cache_name("preview", url))
    except OSError:
        return None
    return ImageOps.fit(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)


async def _load_detail_image(url: str, max_width: int) -> Image.Image:
    try:
        image = await fetch_image(DETAIL_CACHE_PATH, url, name=cache_name("detail", url))
    except OSError:
        return Image.new("RGB", (max_width, 320), (40, 30, 60))
    return shrink_to_width(image.convert("RGB"), max_width)


def _load_avatar(size: int) -> Image.Image:
    if _OFFICIAL_AVATAR.exists():
        return round_avatar(Image.open(_OFFICIAL_AVATAR).convert("RGBA"), size)
    return round_avatar(Image.new("RGB", (size, size), COLOR_FIRE_BRICK), size)


def _draw_dark_panel(canvas: Image.Image, box: tuple[int, int, int, int], *, radius: int = CARD_RADIUS) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(box, radius=radius, fill=COLOR_PANEL_DARK)
    draw.rounded_rectangle(box, radius=radius, outline=COLOR_PANEL_BORDER, width=2)
    canvas.alpha_composite(layer)


async def draw_ann_list_img() -> bytes | str:
    posts = await fetch_ann_list(prefer_cache=True)
    if not posts:
        return "获取公告列表失败"

    visible = posts[:LIST_DISPLAY_LIMIT]
    rows = (len(visible) + GRID_COLS - 1) // GRID_COLS

    grid_width = WIDTH - PADDING * 2
    card_width = (grid_width - GRID_GAP * (GRID_COLS - 1)) // GRID_COLS
    image_height = 156
    card_height = 308

    title_band_height = 168
    title_to_grid_gap = 32
    footer_card_height = 96
    grid_to_footer_gap = 36
    canvas_height = (
        title_band_height
        + title_to_grid_gap
        + rows * card_height
        + max(0, rows - 1) * GRID_GAP
        + grid_to_footer_gap
        + footer_card_height
        + PADDING
    )

    canvas = get_dna_bg(WIDTH, canvas_height).convert("RGBA")

    # 顶部加深一层让标题更显眼
    title_overlay = Image.new("RGBA", (WIDTH, title_band_height), (10, 8, 20, 80))
    canvas.alpha_composite(title_overlay, (0, 0))

    draw = ImageDraw.Draw(canvas)
    draw.text(
        (PADDING, title_band_height // 2),
        "二重螺旋公告",
        font=unicode_font_60,
        fill=COLOR_PALE_GOLDENROD,
        anchor="lm",
    )
    # 标题左侧装饰条
    draw.rounded_rectangle(
        (PADDING - 12, title_band_height // 2 - 32, PADDING - 4, title_band_height // 2 + 32),
        radius=4,
        fill=COLOR_FIRE_BRICK,
    )

    grid_top = title_band_height + title_to_grid_gap
    for idx, post in enumerate(visible, start=1):
        col = (idx - 1) % GRID_COLS
        row = (idx - 1) // GRID_COLS
        left = PADDING + col * (card_width + GRID_GAP)
        top = grid_top + row * (card_height + GRID_GAP)
        right = left + card_width
        bottom = top + card_height

        _draw_dark_panel(canvas, (left, top, right, bottom))
        draw = ImageDraw.Draw(canvas)

        preview = await _load_preview(pick_preview(post), card_width, image_height)
        if preview is not None:
            canvas.paste(preview, (left, top), rounded_mask((card_width, image_height), CARD_RADIUS))

        badge_w, badge_h = 76, 40
        badge_left = left + 14
        badge_top = top + 14
        draw.rounded_rectangle(
            (badge_left, badge_top, badge_left + badge_w, badge_top + badge_h),
            radius=12,
            fill=COLOR_FIRE_BRICK,
        )
        draw.text(
            (badge_left + badge_w // 2, badge_top + badge_h // 2),
            f"#{idx}",
            font=unicode_font_24,
            fill=COLOR_PALE_GOLDENROD,
            anchor="mm",
        )

        text_left = left + 18
        text_top = top + image_height + 16
        text_right = right - 18
        subject_bottom = draw_text_block(
            draw,
            (text_left, text_top),
            pick_subject(post),
            unicode_font_22,
            COLOR_TITLE_LIGHT,
            text_right - text_left,
            line_gap=4,
            max_lines=3,
        )
        time_text = pick_time(post)
        if time_text:
            draw.text(
                (text_left, subject_bottom + 12),
                time_text,
                font=unicode_font_18,
                fill=COLOR_MUTED_LIGHT,
            )

    footer_top = grid_top + rows * card_height + max(0, rows - 1) * GRID_GAP + grid_to_footer_gap
    _draw_dark_panel(canvas, (PADDING, footer_top, WIDTH - PADDING, footer_top + footer_card_height))
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (PADDING + 28, footer_top + footer_card_height // 2),
        f"发送 {DNA_PREFIX}公告 + 序号 查看详情，例如：{DNA_PREFIX}公告 1",
        font=unicode_font_22,
        fill=COLOR_TEXT_LIGHT,
        anchor="lm",
    )

    return await convert_img(canvas)


async def draw_ann_detail_img(post_id: int | str, *, is_check_time: bool = False) -> bytes | str | list[bytes]:
    post_id = str(post_id)
    posts = await fetch_ann_list(prefer_cache=True)
    matched = next((p for p in posts if str(p.get("postId")) == post_id), None)
    if matched is None:
        return "未找到该公告"

    res = await dna_api.get_post_detail(post_id)
    if not res.is_success or not isinstance(res.data, dict):
        return "未找到该公告"

    detail = res.data.get("postDetail") or {}
    if is_check_time:
        post_time = post_time_to_timestamp(detail.get("postTime"))
        now = int(time.time())
        logger.debug(f"[DNA公告] {post_id} post_time={post_time} now={now} delta={now - post_time}")
        if post_time and post_time < now - 86400:
            return "该公告已过期"

    blocks = extract_blocks(detail.get("postContent") or [])
    if not blocks:
        return "未找到该公告"

    subject = detail.get("postTitle") or pick_subject(matched)
    time_text = format_post_time(detail.get("postTime") or matched.get("postTime"))
    qr_image = await load_qr_code(get_post_url(post_id))
    avatar_image = _load_avatar(120)

    pages: list[Image.Image] = []
    page, draw, y = _start_page(0)
    qr_bottom = y

    page.paste(avatar_image, (PADDING, y), avatar_image)
    draw.text((PADDING + 140, y + 32), "二重螺旋官方", font=unicode_font_26, fill=COLOR_TITLE_LIGHT)
    draw.text((PADDING + 140, y + 74), "官方资讯发布", font=unicode_font_22, fill=COLOR_MUTED_LIGHT)
    y += 146

    qr_left = WIDTH - PADDING
    if qr_image:
        qr_size = 164
        qr_box_w = qr_size + 20
        qr_box_h = qr_size + 20
        qr_left = WIDTH - PADDING - qr_box_w
        qr_top = PADDING
        qr_bottom = qr_top + qr_box_h
        qr_panel = Image.new("RGBA", (qr_box_w, qr_box_h), (245, 240, 225, 245))
        page.alpha_composite(qr_panel, (qr_left, qr_top))
        page.paste(qr_image.resize((qr_size, qr_size), Image.Resampling.LANCZOS), (qr_left + 10, qr_top + 10))

    title_width = (qr_left - 24) - PADDING if qr_image else WIDTH - PADDING * 2
    y = draw_text_block(draw, (PADDING, y), subject, unicode_font_60, COLOR_PALE_GOLDENROD, title_width, line_gap=10)
    y += 18
    if time_text:
        draw.text((PADDING, y), f"时间：{time_text}", font=unicode_font_22, fill=COLOR_MUTED_LIGHT)
        y += 36

    y = max(y, qr_bottom + 20)
    draw.line((PADDING, y, WIDTH - PADDING, y), fill=COLOR_DIVIDER_DARK, width=2)
    y += 26

    content_width = WIDTH - PADDING * 2
    body_line_height = line_height(unicode_font_28)

    for kind, value in blocks:
        if kind == "text":
            lines = wrap_text(draw, value, unicode_font_28, content_width)
            for line in lines:
                if y + body_line_height + PADDING > PAGE_LIMIT:
                    pages.append(_finalize_page(page, y))
                    page, draw, y = _start_page(len(pages))
                fill = COLOR_GOLDENROD if line.startswith((">>>", "▸", "◆", "★")) else COLOR_TEXT_LIGHT
                draw.text((PADDING, y), line, font=unicode_font_28, fill=fill)
                y += body_line_height + 10
            y += 6
            continue

        image = await _load_detail_image(value, content_width)
        image_x = (WIDTH - image.width) // 2
        crop_top = 0
        while crop_top < image.height:
            remain = PAGE_LIMIT - y - PADDING
            if remain < 200:
                pages.append(_finalize_page(page, y))
                page, draw, y = _start_page(len(pages))
                remain = PAGE_LIMIT - y - PADDING

            crop_height = int(min(remain, image.height - crop_top))
            part = image.crop((0, crop_top, image.width, crop_top + crop_height))
            page.paste(part, (image_x, y))
            y += crop_height + 16
            crop_top += crop_height
            if crop_top < image.height:
                pages.append(_finalize_page(page, y))
                page, draw, y = _start_page(len(pages))

    pages.append(_finalize_page(page, y))

    rendered = [await convert_img(img) for img in pages]
    return rendered[0] if len(rendered) == 1 else rendered


def _start_page(page_index: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    page = get_dna_bg(WIDTH, PAGE_LIMIT + 200).convert("RGBA")
    draw = ImageDraw.Draw(page)
    y = PADDING
    if page_index > 0:
        draw.text((PADDING, y), f"继续阅读 · 第 {page_index + 1} 页", font=unicode_font_22, fill=COLOR_MUTED_LIGHT)
        y += 44
    return page, draw, y


def _finalize_page(page: Image.Image, bottom: int) -> Image.Image:
    return page.crop((0, 0, WIDTH, bottom + PADDING))
