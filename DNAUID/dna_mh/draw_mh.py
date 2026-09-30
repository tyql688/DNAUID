import random
from pathlib import Path
from datetime import timedelta

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from .cache_mh import get_mh_result
from ..utils.image import (
    COLOR_BLUE,
    COLOR_GREEN,
    COLOR_WHITE,
    COLOR_GOLDENROD,
    COLOR_LIGHT_GRAY,
    COLOR_SADDLE_BROWN,
    add_footer,
)
from ..utils.utils import get_datetime
from .subscribe_mh import get_mh_subscribe_list
from ..utils.api.model import DNARoleForToolInstanceInfo
from ..utils.api.mh_map import get_mh_type_name
from ..utils.msgs.notify import send_dna_notify
from ..utils.fonts.dna_fonts import dna_font_20, dna_font_30, dna_font_36, dna_font_40

TEXT_PATH = Path(__file__).parent / "texture2d"
bg_list = ["bg1.jpg", "bg2.jpg", "bg3.jpg"]


def is_simple_picture() -> bool:
    from ..dna_config.dna_config import DNAConfig

    return DNAConfig.get_config("MHSimplePicture").data


async def draw_mh(bot: Bot, ev: Event):
    now = get_datetime()

    next_refresh = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    remaining_seconds = int((next_refresh - now).total_seconds())

    mh_result = await get_mh_result(int(next_refresh.timestamp()))
    if not mh_result:
        await send_dna_notify(bot, ev, "未找到有效的密函数据")
        return

    mh_list, _ = await get_mh_subscribe_list(bot, ev, ev.user_id)

    if is_simple_picture():
        card = await draw_mh_simple(mh_result, remaining_seconds, mh_list)
    else:
        card = await draw_mh_card(mh_result, remaining_seconds, mh_list)
    return await bot.send(card)


async def draw_mh_simple(
    mh_result: list[DNARoleForToolInstanceInfo],
    remaining_seconds: int,
    subscribe_list: list[str] | None = None,
):
    CARD_W, GUTTER, ICON_S = 320, 20, 256

    img = Image.new("RGBA", ((CARD_W + GUTTER) * len(mh_result) + GUTTER, ICON_S + 390), COLOR_WHITE)
    draw = ImageDraw.Draw(img)

    for i, mh in enumerate(mh_result):
        if not mh.mh_type:
            continue
        cx, cy = GUTTER + i * (CARD_W + GUTTER) + CARD_W // 2, 50
        if (icon_path := TEXT_PATH / f"mh_{mh.mh_type}.png").exists():
            img.alpha_composite(Image.open(icon_path).convert("RGBA").resize((ICON_S, ICON_S)), (cx - ICON_S // 2, cy))

        type_name = get_mh_type_name(mh.mh_type)
        draw.text((cx, cy + ICON_S + 20), type_name, fill=COLOR_SADDLE_BROWN, font=dna_font_40, anchor="mt")
        draw.line((cx - 130, cy + ICON_S + 70, cx + 130, cy + ICON_S + 70), (240, 240, 240), 2)

        for j, ins in enumerate(mh.instances):
            is_sub = subscribe_list and (ins.name in subscribe_list or f"{type_name}:{ins.name}" in subscribe_list)
            color, weight = (COLOR_GREEN, 1) if is_sub else (COLOR_BLUE, 0)
            draw.text((cx, cy + ICON_S + 100 + j * 50), ins.name, fill=color, font=dna_font_36, anchor="mt")
            if weight:
                draw.text((cx + 1, cy + ICON_S + 100 + j * 50), ins.name, fill=color, font=dna_font_36, anchor="mt")

        if i < len(mh_result) - 1:
            vx = GUTTER + (i + 1) * (CARD_W + GUTTER) - GUTTER // 2
            draw.line((vx, 80, vx, img.height - 100), (240, 240, 240), 2)

    draw.rectangle((0, img.height - 70, img.width, img.height - 10), fill=(248, 248, 248))
    now = get_datetime()
    time_range = f"{now.hour}:00 - {(now.hour + 1) % 24}:00"
    draw.text(
        (img.width // 2, img.height - 30),
        f"当前轮换: {time_range}   {format_seconds(remaining_seconds)}后刷新",
        fill=(50, 50, 50),
        font=dna_font_30,
        anchor="mm",
    )
    return await convert_img(img)


async def draw_mh_card(
    mh_result: list[DNARoleForToolInstanceInfo],
    remaining_seconds: int,
    subscribe_list: list[str] | None = None,
):
    card = Image.open(TEXT_PATH / random.choice(bg_list)).convert("RGBA")

    bar_bg = Image.open(TEXT_PATH / "bar.png")
    for i, mh in enumerate(mh_result):
        if not mh.mh_type:
            logger.warning(f"mh_type is None: {mh.model_json_schema()}")
            continue

        mh_card = Image.open(TEXT_PATH / "card.png")
        mh_card_draw = ImageDraw.Draw(mh_card)
        title_type_img = Image.open(TEXT_PATH / f"mh_{mh.mh_type}.png")
        mh_card.alpha_composite(title_type_img, (120, 70))

        for j, ins in enumerate(mh.instances):
            bar_bg_temp = bar_bg.copy()
            bar_bg_draw = ImageDraw.Draw(bar_bg_temp)
            if subscribe_list and (
                ins.name in subscribe_list or f"{get_mh_type_name(mh.mh_type)}:{ins.name}" in subscribe_list
            ):
                ins_color = COLOR_GREEN
            else:
                ins_color = COLOR_WHITE
            bar_bg_draw.text((180, 27), ins.name, ins_color, dna_font_36, "mm")

            mh_card.alpha_composite(bar_bg_temp, (70, j * 80 + 420))

        mh_type_name = get_mh_type_name(mh.mh_type)
        mh_card_draw.text((250, 350), mh_type_name, COLOR_GOLDENROD, dna_font_40, "mm")
        mh_card_draw.text((250, 400), "当前开放", COLOR_LIGHT_GRAY, dna_font_20, "mm")

        card.alpha_composite(mh_card, (i * 500 + 100, 70))

    refresh_bg = Image.open(TEXT_PATH / "refresh_time.png")
    draw_refresh_bg = ImageDraw.Draw(refresh_bg)
    draw_refresh_bg.text(
        (60, 25),
        f"{format_seconds(remaining_seconds)}后刷新",
        COLOR_WHITE,
        dna_font_20,
    )
    card.alpha_composite(refresh_bg, (1400, 20))

    title_bg = Image.open(TEXT_PATH / "title.png")
    card.alpha_composite(title_bg, (0, 0))

    card = add_footer(card, 600)
    res = await convert_img(card)
    return res


def format_seconds(seconds: int) -> str:
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}分钟{seconds}秒"
