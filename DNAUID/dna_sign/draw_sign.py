from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.fonts.fonts import core_font
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import (
    draw_pic_with_ring,
    get_event_avatar,
)

from ..utils import dna_api
from ..utils.api.model import DNACalendarSignRes, DNATaskProcessRes
from ..utils.database.models import DNABind
from ..utils.image import download_pic_from_url
from ..utils.resource.RESOURCE_PATH import SIGN_PATH

font_title = core_font(36)
font_large = core_font(24)
font_medium = core_font(20)
font_small = core_font(16)
font_tiny = core_font(14)

color_black = (0, 0, 0)
color_gray = (128, 128, 128)
color_light_gray = (230, 230, 230)
color_white = (255, 255, 255)
color_red = (255, 0, 0)
color_green = (76, 175, 80)
color_dark_blue = (30, 40, 60)
color_gold = (255, 215, 0)
color_purple = (138, 43, 226)
color_orange = (255, 165, 0)


TEXT_PATH = Path(__file__).parent / "texture2d"
role_bg = Image.open(TEXT_PATH / "role_bg.png").convert("RGBA")


async def _draw_sign_calendar(
    ev: Event,
    sign_data: DNACalendarSignRes,
    task_process: DNATaskProcessRes,
    bbs_total_sign_in_day: int,
):
    task_list = task_process.dailyTask if task_process else None
    cell_size = 80
    cell_padding = 8
    cols = 7
    rows = 5

    canvas_width = 900
    canvas_height = 1400
    img = Image.new("RGBA", (canvas_width, canvas_height), color=color_white)
    draw = ImageDraw.Draw(img)

    role_bg_img = role_bg.resize(
        (int(role_bg.size[0] * canvas_height / role_bg.size[1]), canvas_height)
    )

    blurred_bg = role_bg_img.filter(ImageFilter.GaussianBlur(radius=5))

    img.alpha_composite(blurred_bg, (canvas_width - blurred_bg.size[0], 0))

    current_y = 20

    role_info = sign_data.roleInfo
    card_height = 100
    card_y = current_y

    draw.rectangle(
        [20, card_y, canvas_width - 20, card_y + card_height],
        fill=color_dark_blue,
        outline=None,
    )

    avatar_size = 80
    avatar_x = 40
    avatar_y = card_y + 10

    avatar_img = await draw_pic_with_ring(await get_event_avatar(ev), avatar_size)
    img.paste(avatar_img, (avatar_x, avatar_y), avatar_img)

    level = role_info.level
    badge_size = 28
    badge_x = avatar_x + avatar_size - badge_size
    badge_y = avatar_y + avatar_size - badge_size

    badge_points = [
        (badge_x + badge_size // 2, badge_y),
        (badge_x + badge_size, badge_y + badge_size // 2),
        (badge_x + badge_size // 2, badge_y + badge_size),
        (badge_x, badge_y + badge_size // 2),
    ]
    draw.polygon(badge_points, fill=color_white, outline=color_gold)
    draw.polygon(badge_points, fill=None, outline=color_gold, width=2)
    level_text = str(level)
    level_bbox = font_small.getbbox(level_text)
    level_width = level_bbox[2] - level_bbox[0]
    level_height = level_bbox[3] - level_bbox[1]
    draw.text(
        (
            badge_x + (badge_size - level_width) // 2,
            badge_y + (badge_size - level_height) // 2,
        ),
        level_text,
        fill=color_black,
        font=font_small,
    )

    role_name = role_info.roleName
    role_id = role_info.roleId

    text_x = avatar_x + avatar_size + 20
    text_y = card_y + 20

    draw.text((text_x, text_y), role_name, fill=color_white, font=font_large)

    uid_text = f"UID: {role_id}"
    draw.text((text_x, text_y + 35), uid_text, fill=color_white, font=font_medium)

    current_y = card_y + card_height + 20

    title_text = "签到福利"
    title_bbox = font_title.getbbox(title_text)
    title_width = title_bbox[2] - title_bbox[0]
    draw.text(
        ((canvas_width - title_width) // 2, current_y),
        title_text,
        fill=color_black,
        font=font_title,
    )
    current_y += 60

    if task_list and len(task_list) > 0:
        calendar_grid_width = cols * (cell_size + cell_padding) - cell_padding
        grid_start_x = (canvas_width - calendar_grid_width) // 2

        task_title_y = current_y + 20
        task_title_text = "皎皎角社区任务"
        draw.text(
            (50, task_title_y),
            task_title_text,
            fill=color_black,
            font=font_large,
        )

        gold_num = sign_data.userGoldNum
        gold_text = f"皎皎积分: {gold_num}"
        task_title_width = (
            font_large.getbbox(task_title_text)[2]
            - font_large.getbbox(task_title_text)[0]
        )
        gold_text_x = 50 + task_title_width + 20
        draw.text(
            (gold_text_x, task_title_y + 10),
            gold_text,
            fill=color_gold,
            font=font_medium,
        )
        prefix_text = "累计签到"
        num_text = str(bbs_total_sign_in_day)
        suffix_text = "天"

        prefix_width = (
            font_large.getbbox(prefix_text)[2] - font_large.getbbox(prefix_text)[0]
        )
        num_width = font_large.getbbox(num_text)[2] - font_large.getbbox(num_text)[0]
        suffix_width = (
            font_large.getbbox(suffix_text)[2] - font_large.getbbox(suffix_text)[0]
        )

        total_width = prefix_width + num_width + suffix_width
        sign_day_x = canvas_width - total_width - 50

        draw.text(
            (sign_day_x, task_title_y),
            prefix_text,
            fill=color_black,
            font=font_large,
        )
        draw.text(
            (sign_day_x + prefix_width, task_title_y),
            num_text,
            fill=color_orange,
            font=font_large,
        )
        draw.text(
            (sign_day_x + prefix_width + num_width, task_title_y),
            suffix_text,
            fill=color_black,
            font=font_large,
        )

        current_y = task_title_y + 70

        task_content_start_x = grid_start_x
        grid_end_x = grid_start_x + calendar_grid_width

        for task in task_list:
            task_y = current_y

            reward_x = task_content_start_x
            reward_y = task_y

            icon_size = 20
            icon_x = reward_x
            icon_y = reward_y
            draw.ellipse(
                [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
                fill=color_purple,
                outline=color_purple,
            )

            desc_text = task.remark
            desc_x = icon_x + icon_size + 10
            desc_y = reward_y
            draw.text(
                (desc_x, desc_y),
                desc_text,
                fill=color_black,
                font=font_small,
            )

            exp_text = f"{task.gainExp}"
            exp_label = "经验值"
            exp_label_text = f"{exp_label}+{exp_text}"
            exp_label_y = desc_y + 18
            draw.text(
                (desc_x, exp_label_y),
                exp_label_text,
                fill=color_black,
                font=font_small,
            )

            progress_bar_width = 300
            progress_bar_height = 6
            progress_bar_x = grid_end_x - progress_bar_width - 10
            progress_bar_y = desc_y + 15
            draw.rectangle(
                [
                    progress_bar_x,
                    progress_bar_y,
                    progress_bar_x + progress_bar_width,
                    progress_bar_y + progress_bar_height,
                ],
                fill=color_light_gray,
                outline=None,
            )

            filled_width = int(progress_bar_width * task.process)
            is_completed = task.process >= 1.0 or task.completeTimes >= task.times
            progress_color = color_green if is_completed else color_red
            if filled_width > 0:
                draw.rectangle(
                    [
                        progress_bar_x,
                        progress_bar_y,
                        progress_bar_x + filled_width,
                        progress_bar_y + progress_bar_height,
                    ],
                    fill=progress_color,
                    outline=None,
                )

            progress_text = f"{task.completeTimes}/{task.times}"
            draw.text(
                (
                    progress_bar_x + progress_bar_width + 10,
                    progress_bar_y - 2,
                ),
                progress_text,
                fill=color_black,
                font=font_tiny,
            )

            current_y = exp_label_y + 30

        current_y += 25

    calendar_start_y = current_y + 30

    period_text = "游戏签到"
    start_date = datetime.fromtimestamp(sign_data.period.startDate / 1000)
    end_date = datetime.fromtimestamp(sign_data.period.endDate / 1000)
    period_text += f" ({start_date.month:02d}.{start_date.day:02d} - {end_date.month:02d}.{end_date.day:02d})"

    draw.text((50, current_y), period_text, fill=color_black, font=font_large)

    current_y = calendar_start_y + 50

    grid_start_x = (
        canvas_width - (cols * (cell_size + cell_padding) - cell_padding)
    ) // 2
    grid_start_y = current_y

    award_dict = {award.dayInPeriod: award for award in sign_data.dayAward}

    total_days = sign_data.period.overDays

    signed_days = sign_data.signinTime
    for day in range(1, total_days + 1):
        row = (day - 1) // cols
        col = (day - 1) % cols

        x = grid_start_x + col * (cell_size + cell_padding)
        y = grid_start_y + row * (cell_size + cell_padding + 20)

        is_signed = day <= signed_days
        is_current = day == signed_days

        bg_color = color_white
        border_color = color_gray

        if is_signed:
            border_width = 2
        else:
            border_width = 2

        if is_current:
            border_width = 3
            border_color = color_gold
        draw.rectangle(
            [x, y, x + cell_size, y + cell_size],
            fill=bg_color,
            outline=border_color,
            width=border_width,
        )

        award = award_dict.get(day)
        if award:
            icon_img = await download_pic_from_url(
                SIGN_PATH, award.iconUrl, size=(50, 50)
            )
            if icon_img:
                icon_x = x + (cell_size - 50) // 2
                icon_y = y + 5
                img.alpha_composite(icon_img, (icon_x, icon_y))

            num_text = f"x{award.awardNum}"
            num_bbox = font_tiny.getbbox(num_text)
            num_width = num_bbox[2] - num_bbox[0]
            num_color = color_black if is_signed else color_gray
            draw.text(
                (x + (cell_size - num_width) // 2, y + 55),
                num_text,
                fill=num_color,
                font=font_tiny,
            )

        day_text = f"第{day}天"
        day_bbox = font_tiny.getbbox(day_text)
        day_width = day_bbox[2] - day_bbox[0]
        day_color = color_black
        draw.text(
            (x + (cell_size - day_width) // 2, y + cell_size + 5),
            day_text,
            fill=day_color,
            font=font_tiny,
        )

        if is_signed:
            check_size = 24
            check_x = x + (cell_size - check_size) // 2
            check_y = y + (cell_size - check_size) // 2
            draw.line(
                [
                    check_x + check_size * 0.2,
                    check_y + check_size * 0.5,
                    check_x + check_size * 0.45,
                    check_y + check_size * 0.75,
                ],
                fill=color_green,
                width=3,
            )
            draw.line(
                [
                    check_x + check_size * 0.45,
                    check_y + check_size * 0.75,
                    check_x + check_size * 0.8,
                    check_y + check_size * 0.25,
                ],
                fill=color_green,
                width=3,
            )

    bottom_y = grid_start_y + rows * (cell_size + cell_padding + 20) + 30

    prefix_text = "本期累计签到"
    num_text = str(sign_data.signinTime)
    suffix_text = "天"

    prefix_width = (
        font_medium.getbbox(prefix_text)[2] - font_medium.getbbox(prefix_text)[0]
    )
    num_width = font_medium.getbbox(num_text)[2] - font_medium.getbbox(num_text)[0]
    suffix_width = (
        font_medium.getbbox(suffix_text)[2] - font_medium.getbbox(suffix_text)[0]
    )

    total_width = prefix_width + num_width + suffix_width
    start_x = (canvas_width - total_width) // 2

    draw.text((start_x, bottom_y), prefix_text, fill=color_black, font=font_medium)
    draw.text(
        (start_x + prefix_width, bottom_y), num_text, fill=color_red, font=font_medium
    )
    draw.text(
        (start_x + prefix_width + num_width, bottom_y),
        suffix_text,
        fill=color_black,
        font=font_medium,
    )

    tip_text = "(*奖励通过游戏内邮件发放,请查收)"
    tip_width = font_tiny.getbbox(tip_text)[2] - font_tiny.getbbox(tip_text)[0]
    draw.text(
        ((canvas_width - tip_width) // 2, bottom_y + 35),
        tip_text,
        fill=color_gray,
        font=font_tiny,
    )

    img = await convert_img(img)
    return img


async def draw_sign_calendar(bot: Bot, ev: Event):
    uid = await DNABind.get_uid_by_game(ev.user_id, ev.bot_id)
    if not uid:
        return

    dna_user = await dna_api.get_dna_user(uid, ev.user_id, ev.bot_id)
    if not dna_user:
        return

    have_sign_in_resp = await dna_api.have_sign_in(dna_user.cookie, dna_user.dev_code)
    if not have_sign_in_resp.is_success or not isinstance(have_sign_in_resp.data, dict):
        return
    bbs_total_sign_in_day = have_sign_in_resp.data.get("totalSignInDay", 0)

    sign_resp = await dna_api.sign_calendar(dna_user.cookie, dna_user.dev_code)
    if not sign_resp.is_success:
        return

    sign_raw_data = sign_resp.data if isinstance(sign_resp.data, dict) else {}
    sign_data = DNACalendarSignRes.model_validate(sign_raw_data)

    task_process_resp = await dna_api.get_task_process(
        dna_user.cookie, dna_user.dev_code
    )
    if not task_process_resp.is_success:
        return

    task_process = DNATaskProcessRes.model_validate(task_process_resp.data)

    msg = await _draw_sign_calendar(ev, sign_data, task_process, bbs_total_sign_in_day)
    await bot.send(msg)
