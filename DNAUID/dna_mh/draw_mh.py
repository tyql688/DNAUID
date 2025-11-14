import random
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils import get_datetime
from ..utils.api.mh_map import get_mh_type_name
from ..utils.fonts.dna_fonts import dna_font_20, dna_font_25, dna_font_30
from ..utils.image import (
    COLOR_GOLDENROD,
    COLOR_GREEN,
    COLOR_LIGHT_GRAY,
    COLOR_WHITE,
    add_footer,
)
from ..utils.msgs.notify import send_dna_notify
from .cache_mh import get_mh_result
from .subscribe_mh import get_mh_subscribe_list

TEXT_PATH = Path(__file__).parent / "texture2d"
bg_list = ["bg1.jpg", "bg2.jpg", "bg3.jpg"]


async def draw_mh(bot: Bot, ev: Event):
    now = get_datetime()

    next_refresh = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    remaining_seconds = int((next_refresh - now).total_seconds())

    mh_result = await get_mh_result(int(next_refresh.timestamp()))
    if not mh_result:
        await send_dna_notify(bot, ev, "未找到有效的密函数据")
        return

    mh_list = await get_mh_subscribe_list(bot, ev, ev.user_id)

    card = Image.open(TEXT_PATH / random.choice(bg_list)).convert("RGBA")

    bar_bg = Image.open(TEXT_PATH / "bar.png").convert("RGBA")
    for i, mh in enumerate(mh_result):
        if not mh.mh_type:
            logger.warning(f"mh_type is None: {mh.model_json_schema()}")
            continue

        mh_card = Image.open(TEXT_PATH / "card.png").convert("RGBA")
        mh_card_draw = ImageDraw.Draw(mh_card)
        title_type_img = Image.open(TEXT_PATH / f"mh_{mh.mh_type}.png").convert("RGBA")
        mh_card.alpha_composite(title_type_img, (120, 70))

        for j, ins in enumerate(mh.instances):
            bar_bg_temp = bar_bg.copy()
            bar_bg_draw = ImageDraw.Draw(bar_bg_temp)
            if (
                ins.name in mh_list
                or f"{get_mh_type_name(mh.mh_type)}:{ins.name}" in mh_list
            ):
                ins_color = COLOR_GREEN
            else:
                ins_color = COLOR_WHITE
            bar_bg_draw.text((50, 15), ins.name, ins_color, dna_font_25)

            mh_card.alpha_composite(bar_bg_temp, (70, j * 80 + 420))

        mh_type_name = get_mh_type_name(mh.mh_type)
        mh_card_draw.text((250, 340), mh_type_name, COLOR_GOLDENROD, dna_font_30, "mm")
        mh_card_draw.text((250, 375), "当前开放", COLOR_LIGHT_GRAY, dna_font_20, "mm")

        card.alpha_composite(mh_card, (i * 500 + 100, 70))

    refresh_bg = Image.open(TEXT_PATH / "refresh_time.png").convert("RGBA")
    draw_refresh_bg = ImageDraw.Draw(refresh_bg)
    draw_refresh_bg.text(
        (60, 25), f"{format_seconds(remaining_seconds)}后刷新", COLOR_WHITE, dna_font_20
    )
    card.alpha_composite(refresh_bg, (1400, 20))

    title_bg = Image.open(TEXT_PATH / "title.png").convert("RGBA")
    card.alpha_composite(title_bg, (0, 0))

    card = add_footer(card, 600)
    res = await convert_img(card)
    await bot.send(res)


def format_seconds(seconds: int) -> str:
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}分钟{seconds}秒"
