import math
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils import dna_api
from ..utils.image import (
    COLOR_WHITE,
    COLOR_PALE_GOLDENROD,
    add_footer,
    get_dna_bg,
    get_avatar_title_img,
    download_pic_from_url,
)
from ..utils.utils import get_using_id, is_uid_hidden, is_peek_blocked
from ..utils.api.model import (
    DNARoleForToolRes,
    DNAWeeklyReportItem,
    DNAItemWeeklyReportRes,
    DNAWeeklyReportCategory,
)
from ..utils.msgs.notify import (
    dna_not_found,
    dna_uid_invalid,
    dna_peek_blocked,
    dna_token_invalid,
)
from ..utils.database.models import DNABind
from ..utils.fonts.dna_fonts import dna_font_22, dna_font_25, dna_font_28, dna_font_30, dna_font_36
from ..utils.resource.RESOURCE_PATH import WEEKLY_ITEM_PATH


async def draw_weekly_report_img(bot: Bot, ev: Event, week_type: int = 1):
    user_id = await get_using_id(ev)
    if is_peek_blocked(ev, user_id):
        return await dna_peek_blocked(bot, ev)

    uid = await DNABind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        return await dna_uid_invalid(bot, ev)

    dna_user = await dna_api.get_dna_user(uid, user_id, ev.bot_id)
    if not dna_user:
        return await dna_token_invalid(bot, ev)

    report_resp = await dna_api.get_item_weekly_report(dna_user, week_type)
    if not report_resp.is_success:
        return await dna_not_found(bot, ev, "周报数据")
    report = DNAItemWeeklyReportRes.model_validate(report_resp.data)

    role_resp = await dna_api.get_default_role_for_tool(dna_user)
    if not role_resp.is_success:
        return await dna_not_found(bot, ev, "角色列表信息")
    role_show = DNARoleForToolRes.model_validate(role_resp.data).roleInfo.roleShow

    # 布局参数（全部 local，避免污染模块全局）
    card_w, side_pad, per_row = 1200, 70, 5
    item_w, item_h = (card_w - side_pad * 2) // per_row, 230
    oval_size, icon_size = 140, 105
    title_h, banner_cy, cat_h, footer_pad = 400, 320, 70, 100
    quality_dir = Path(__file__).parent / "texture2d" / "quality"

    def fmt_date(s: str) -> str:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s

    def cat_height(c: DNAWeeklyReportCategory) -> int:
        return cat_h + max(1, math.ceil(len(c.items) / per_row)) * item_h + 20

    async def load_icon(item: DNAWeeklyReportItem) -> Image.Image:
        name = f"item_{item.itemId}.png"
        path = WEEKLY_ITEM_PATH / name
        if path.exists():
            return Image.open(path).convert("RGBA").resize((icon_size, icon_size))
        img = await download_pic_from_url(WEEKLY_ITEM_PATH, item.icon, size=(icon_size, icon_size), name=name)
        return img.convert("RGBA")

    async def draw_tile(item: DNAWeeklyReportItem) -> Image.Image:
        q = item.quality if 0 <= item.quality <= 5 else 0
        tile = Image.new("RGBA", (item_w, item_h))
        oval = Image.open(quality_dir / f"q{q}.png").convert("RGBA").resize((oval_size, oval_size))
        tile.alpha_composite(oval, ((item_w - oval_size) // 2, 0))
        tile.alpha_composite(await load_icon(item), ((item_w - icon_size) // 2, (oval_size - icon_size) // 2 + 4))
        d = ImageDraw.Draw(tile)
        name = item.itemName if len(item.itemName) <= 8 else item.itemName[:7] + "…"
        d.text((item_w // 2, oval_size + 22), name, COLOR_WHITE, dna_font_28, "mm")
        d.text((item_w // 2, oval_size + 60), f"× {item.totalNum}", COLOR_PALE_GOLDENROD, dna_font_30, "mm")
        return tile

    async def draw_category(start_y: int, category: DNAWeeklyReportCategory) -> int:
        d = ImageDraw.Draw(card)
        bl, br = side_pad - 20, card_w - side_pad + 20
        d.rectangle((bl, start_y + 10, bl + 8, start_y + cat_h - 10), fill=COLOR_PALE_GOLDENROD)
        d.text((bl + 25, start_y + cat_h // 2), category.categoryName, COLOR_WHITE, dna_font_36, "lm")
        d.line((bl + 25, start_y + cat_h - 10, br, start_y + cat_h - 10), fill=(255, 255, 255, 80), width=2)
        y = start_y + cat_h
        if not category.items:
            d.text((card_w // 2, y + item_h // 2), "本周暂无相关资源获取", (200, 200, 200), dna_font_25, "mm")
            return y + item_h + 20
        for i, item in enumerate(category.items):
            tile = await draw_tile(item)
            card.alpha_composite(tile, (side_pad + (i % per_row) * item_w, y + (i // per_row) * item_h))
        return y + math.ceil(len(category.items) / per_row) * item_h + 20

    def draw_banner() -> None:
        d = ImageDraw.Draw(card)
        label = "本周周报" if week_type == 1 else "上周周报"
        period = f"{fmt_date(report.startDate)}  ~  {fmt_date(report.endDate)}"
        cx, ly = card_w // 2, banner_cy
        gold_s, gold_w = (*COLOR_PALE_GOLDENROD, 220), (*COLOR_PALE_GOLDENROD, 110)
        le, rs = cx - 120, cx + 120
        d.line((le - 180, ly, le, ly), fill=gold_s, width=2)
        d.line((le - 210, ly, le - 180, ly), fill=gold_w, width=2)
        d.line((rs, ly, rs + 180, ly), fill=gold_s, width=2)
        d.line((rs + 180, ly, rs + 210, ly), fill=gold_w, width=2)
        for dx in (le, rs):
            d.polygon([(dx, ly - 5), (dx + 5, ly), (dx, ly + 5), (dx - 5, ly)], fill=COLOR_PALE_GOLDENROD)
        d.text((cx, ly), label, COLOR_PALE_GOLDENROD, dna_font_36, "mm")
        d.text((cx, ly + 45), period, COLOR_WHITE, dna_font_22, "mm")

    h = title_h + sum(cat_height(c) for c in report.categories) + footer_pad
    card = get_dna_bg(card_w, h, "bg1")

    other_info = [
        (i.paramKey, i.paramValue) for i in role_show.params if i.paramKey in ("总活跃天数", "游戏时长", "获得角色数")
    ]
    avatar_title = await get_avatar_title_img(
        ev,
        role_show.roleId,
        role_show.roleName,
        user_level=role_show.level,
        other_info=other_info,
        avatar_user_id=user_id,
        uid_hidden=await is_uid_hidden(user_id, ev.bot_id, ev.group_id),
    )
    card.alpha_composite(avatar_title, (-50, 30))
    draw_banner()

    cursor_y = title_h
    for category in report.categories:
        cursor_y = await draw_category(cursor_y, category)

    await bot.send(await convert_img(add_footer(card, 600)))
