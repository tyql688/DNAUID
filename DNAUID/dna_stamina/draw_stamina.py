import random
import time
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils import dna_api
from ..utils.api.model import DNARoleForToolRes, DNARoleShortNoteRes
from ..utils.database.models import DNABind
from ..utils.fonts.dna_fonts import dna_font_30, dna_font_36, dna_font_40
from ..utils.image import (
    COLOR_GREEN,
    COLOR_WHITE,
    add_footer,
    get_avatar_title_img,
)
from ..utils.msgs.notify import (
    dna_not_found,
    dna_token_invalid,
    dna_uid_invalid,
)

TEXT_PATH = Path(__file__).parent / "texture2d"
bg_list = ["bg2.jpg", "bg3.jpg", "bg5.jpg"]

running = Image.open(TEXT_PATH / "running.png").convert("RGBA")
success = Image.open(TEXT_PATH / "success.png").convert("RGBA")


async def draw_stamina_img(bot: Bot, ev: Event):
    uid = await DNABind.get_uid_by_game(ev.user_id, ev.bot_id)
    if not uid:
        await dna_uid_invalid(bot, ev)
        return

    dna_user = await dna_api.get_dna_user(uid, ev.user_id, ev.bot_id)
    if not dna_user:
        await dna_token_invalid(bot, ev)
        return

    short_note_info = await dna_api.get_short_note_info(
        dna_user.cookie, dna_user.dev_code
    )
    if not short_note_info.is_success:
        await dna_not_found(bot, ev, "日常便签数据")
        return
    short_note_info = DNARoleShortNoteRes.model_validate(short_note_info.data)

    role_for_tool_info = await dna_api.get_default_role_for_tool(
        dna_user.cookie, dna_user.dev_code
    )
    if not role_for_tool_info.is_success:
        await dna_not_found(bot, ev, "角色信息")
        return
    role_for_tool_info = DNARoleForToolRes.model_validate(role_for_tool_info.data)

    card = Image.open(TEXT_PATH / random.choice(bg_list)).convert("RGBA")
    fg = Image.open(TEXT_PATH / "fg.png").convert("RGBA")
    card.alpha_composite(fg, (0, 0))

    role_show = role_for_tool_info.roleInfo.roleShow
    other_info = [
        (i.paramKey, i.paramValue)
        for i in role_show.params
        if i.paramKey in ("总活跃天数", "成就达成", "获得角色数")
    ]
    # title
    avatar_title = await get_avatar_title_img(
        ev,
        role_show.roleId,
        role_show.roleName,
        user_level=role_show.level,
        other_info=other_info,
    )
    card.alpha_composite(avatar_title, (-50, 30))

    # div
    div = Image.open(TEXT_PATH / "div.png").convert("RGBA")
    card.alpha_composite(div, (80, 300))

    bar_bg = Image.open(TEXT_PATH / "bar_bg2.png").convert("RGBA")
    # 便签
    data_list = [
        (
            "备忘手记",
            short_note_info.currentTaskProgress,
            short_note_info.maxDailyTaskProgress,
        ),
        (
            "迷津",
            short_note_info.rougeLikeRewardCount,
            short_note_info.rougeLikeRewardTotal,
        ),
        (
            "梦魇残声",
            short_note_info.hardBossRewardCount,
            short_note_info.hardBossRewardTotal,
        ),
    ]

    for index, data_temp in enumerate(data_list):
        icon_path = Image.open(TEXT_PATH / f"icon{index + 1}.png").convert("RGBA")

        bar_bg_temp = bar_bg.copy()
        bar_bg_temp_draw = ImageDraw.Draw(bar_bg_temp)
        bar_bg_temp.alpha_composite(icon_path, (30, 10))

        bar_bg_temp_draw.text((150, 30), data_temp[0], COLOR_WHITE, dna_font_40, "lm")
        bar_bg_temp_draw.text(
            (990, 30),
            f"{data_temp[1]}/{data_temp[2]}",
            COLOR_WHITE,
            dna_font_40,
            "rm",
        )

        progress_per = data_temp[1] / data_temp[2] if data_temp[2] != 0 else 0
        if progress_per > 1:
            progress_per = 1

        progress = int(150 + 840 * progress_per)

        # 进度条 总长度为840
        bar_bg_temp_draw.rounded_rectangle((150, 70, progress, 90), 10, COLOR_WHITE)

        card.alpha_composite(bar_bg_temp, (80, 400 + index * 150))

    # 锻造
    draft_info = short_note_info.draftInfo

    if draft_info and draft_info.draftDoingNum > 0 and draft_info.draftDoingInfo:
        time_now = int(time.time())
        for index, draft in enumerate(draft_info.draftDoingInfo):
            draft_bg = Image.open(TEXT_PATH / "draft_bg.png").convert("RGBA")
            draft_bg_draw = ImageDraw.Draw(draft_bg)
            draft_bg_draw.text(
                (115, 33), draft.productName, COLOR_WHITE, dna_font_36, "lm"
            )

            if time_now > int(draft.endTime):
                # 已完成
                draft_bg.alpha_composite(success, (65, 22))
                draft_bg_draw.text((500, 32), "已完成", COLOR_GREEN, dna_font_30, "rm")
            else:
                # 进行中
                left_str = format_seconds(int(draft.endTime) - time_now)
                draft_bg.alpha_composite(running, (65, 22))
                draft_bg_draw.text(
                    (500, 32),
                    left_str,
                    COLOR_WHITE,
                    dna_font_30,
                    "rm",
                )

            # 2*2 4个 先上下两行 再左右两列
            card.alpha_composite(
                draft_bg, (30 + index // 2 * 590, 840 + index % 2 * 100)
            )

    card = add_footer(card, 600)
    res = await convert_img(card)
    await bot.send(res)


def format_seconds(seconds: float):
    hours = seconds // 3600
    minute = (seconds % 3600) // 60
    second = seconds % 60
    return f"{hours:02d}:{minute:02d}:{second:02d}"
