import time
import random
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import tint_image, crop_center_img

from ..utils import dna_api
from ..utils.image import (
    COLOR_GREEN,
    COLOR_KHAKI,
    COLOR_WHITE,
    add_footer,
    get_smooth_drawer,
    get_avatar_title_img,
)
from ..utils.utils import get_using_id, is_uid_hidden
from ..utils.api.model import DNARoleForToolRes, DNARoleShortNoteRes
from ..utils.msgs.notify import (
    dna_not_found,
    dna_uid_invalid,
    dna_peek_blocked,
    dna_token_invalid,
)
from ..utils.database.models import DNABind
from ..utils.fonts.dna_fonts import dna_font_30, dna_font_36, dna_font_40

TEXT_PATH = Path(__file__).parent / "texture2d"
running = Image.open(TEXT_PATH / "running.png")
success = Image.open(TEXT_PATH / "success.png")


def get_bg_list():
    bg_path = TEXT_PATH / "bg"
    bg_list = [str(path) for path in bg_path.iterdir() if path.suffix.lower() in (".jpg", ".png", ".webp")]
    return random.choice(bg_list)


async def draw_stamina_img(bot: Bot, ev: Event):
    user_id = await get_using_id(ev)
    # 检查是否被防偷窥阻止（有@目标但被阻止）
    if ev.at and user_id == ev.user_id:
        await dna_peek_blocked(bot, ev)
        return
    uid = await DNABind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        await dna_uid_invalid(bot, ev)
        return

    dna_user = await dna_api.get_dna_user(uid, user_id, ev.bot_id)
    if not dna_user:
        await dna_token_invalid(bot, ev)
        return

    short_note_info = await dna_api.get_short_note_info(dna_user.cookie, dna_user.dev_code)
    if not short_note_info.is_success:
        await dna_not_found(bot, ev, "日常便签数据")
        return
    short_note_info = DNARoleShortNoteRes.model_validate(short_note_info.data)

    role_for_tool_info = await dna_api.get_default_role_for_tool(dna_user.cookie, dna_user.dev_code)
    if not role_for_tool_info.is_success:
        await dna_not_found(bot, ev, "角色列表信息")
        return
    role_for_tool_info = DNARoleForToolRes.model_validate(role_for_tool_info.data)

    card = Image.open(get_bg_list()).convert("RGBA")
    card = crop_center_img(card, 2000, 1100)
    fg = Image.open(TEXT_PATH / "fg.png")
    card.alpha_composite(fg, (0, 0))

    role_show = role_for_tool_info.roleInfo.roleShow
    other_info = [
        (i.paramKey, i.paramValue) for i in role_show.params if i.paramKey in ("总活跃天数", "游戏时长", "获得角色数")
    ]
    # 检查 UID 是否应该被隐藏
    uid_hidden = await is_uid_hidden(user_id, ev.bot_id, ev.group_id)
    # title
    avatar_title = await get_avatar_title_img(
        ev,
        role_show.roleId,
        role_show.roleName,
        user_level=role_show.level,
        other_info=other_info,
        avatar_user_id=user_id,
        uid_hidden=uid_hidden,
    )
    card.alpha_composite(avatar_title, (-50, 30))

    # div
    div = Image.open(TEXT_PATH / "div.png")
    card.alpha_composite(div, (80, 300))

    bar_bg = Image.open(TEXT_PATH / "bar_bg2.png")
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
        (
            "竞逐",
            short_note_info.dungeonReward,
            short_note_info.dungeonRewardTotal,
        ),
    ]

    for index, data_temp in enumerate(data_list):
        icon_path = Image.open(TEXT_PATH / f"icon{index + 1}.png").convert("RGBA")
        icon_path = tint_image(icon_path, COLOR_KHAKI)

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

        progress = int(152 + 837 * progress_per)

        # 进度条 总长度为837
        get_smooth_drawer().rounded_rectangle((152, 73, progress, 90), 10, COLOR_WHITE, target=bar_bg_temp)

        card.alpha_composite(bar_bg_temp, (80, 400 + index * 150))

    # 锻造
    draft_info = short_note_info.draftInfo

    if draft_info and draft_info.draftDoingNum > 0 and draft_info.draftDoingInfo:
        time_now = int(time.time())
        for index, draft in enumerate(draft_info.draftDoingInfo):
            draft_bg = Image.open(TEXT_PATH / "draft_bg.png")
            draft_bg_draw = ImageDraw.Draw(draft_bg)
            draft_bg_draw.text((115, 33), draft.productName, COLOR_WHITE, dna_font_36, "lm")

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

            card.alpha_composite(draft_bg, (1400, 980 - (index + 1) * 100))

    card = add_footer(card, 600)
    res = await convert_img(card)
    await bot.send(res)


def format_seconds(seconds: float):
    hours = seconds // 3600
    minute = (seconds % 3600) // 60
    second = seconds % 60
    return f"{hours:02d}:{minute:02d}:{second:02d}"
