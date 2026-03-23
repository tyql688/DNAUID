import math
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils import dna_api
from ..utils.image import (
    COLOR_GRAY,
    COLOR_GREEN,
    COLOR_WHITE,
    COLOR_GOLDENROD,
    COLOR_PALE_GOLDENROD,
    get_div,
    add_footer,
    get_dna_bg,
    get_smooth_drawer,
    get_avatar_title_img,
    download_pic_from_url,
)
from ..utils.utils import is_uid_hidden
from ..utils.api.model import (
    RoleShowForTool,
    DNARoleForToolRes,
    DNATaskProcessRes,
    DNACalendarSignRes,
)
from ..utils.msgs.notify import dna_not_found
from ..utils.database.models import DNABind
from ..utils.fonts.dna_fonts import (
    dna_font_20,
    dna_font_25,
    dna_font_26,
    dna_font_28,
    dna_font_50,
)
from ..utils.resource.RESOURCE_PATH import SIGN_PATH

TEXT_PATH = Path(__file__).parent / "texture2d"
global_line = Image.open(TEXT_PATH / "line.png")
global_green = Image.open(TEXT_PATH / "green.png")
global_red = Image.open(TEXT_PATH / "red.png")
global_item_bg = Image.open(TEXT_PATH / "item_BG.png")
cols = 7
rows = 5


async def _draw_sign_calendar(
    ev: Event,
    role_show: RoleShowForTool,
    sign_data: DNACalendarSignRes,
    task_process: DNATaskProcessRes,
    bbs_total_sign_in_day: int,
    uid_hidden: bool = False,
):
    task_list = task_process.dailyTask if task_process else None

    title_h = 270
    info_h = 120
    div_h = 100
    footer_h = 50
    h = 30 + title_h + info_h + div_h * 2 + footer_h
    if task_list and len(task_list) > 0:
        h += 60 * len(task_list)
        h += 20
    if sign_data.dayAward and len(sign_data.dayAward) > 0:
        h += 240 * math.ceil(len(sign_data.dayAward) / cols)

    card = get_dna_bg(1300, h, "bg1")

    start_y = 30
    # title
    avatar_title = await get_avatar_title_img(
        ev,
        role_show.roleId,
        role_show.roleName,
        user_level=role_show.level,
        uid_hidden=uid_hidden,
    )
    card.alpha_composite(avatar_title, (0, start_y))
    start_y += title_h

    # bar
    # 皎皎积分，社区累计签到，游戏累计签到，总活跃天数
    # 成就展示
    achievement_info = [
        ("皎皎积分", str(sign_data.userGoldNum)),
        ("社区累计签到", str(bbs_total_sign_in_day)),
        ("游戏累计签到", str(sign_data.signinTime)),
    ]
    achievement_info.extend([(i.paramKey, i.paramValue) for i in role_show.params if i.paramKey in ("总活跃天数")])
    info_bar = Image.new("RGBA", (1300, 88))
    info_bar_draw = ImageDraw.Draw(info_bar)
    bar = Image.open(TEXT_PATH / "bar.png")
    info_bar.alpha_composite(bar, (250, 0))

    for index, info in enumerate(achievement_info):
        # 数量
        info_bar_draw.text((315 + index * 215, 20), info[1], COLOR_WHITE, dna_font_50, "mm")
        # 描述
        info_bar_draw.text(
            (315 + index * 215, 63),
            info[0],
            COLOR_PALE_GOLDENROD,
            dna_font_25,
            "mm",
        )
    card.alpha_composite(info_bar, (0, start_y))
    start_y += info_h

    # div
    div = get_div()
    card.alpha_composite(div, (120, start_y))
    start_y += div_h

    # 社区签到
    if task_list and len(task_list) > 0:
        for task in task_list:
            icon = global_green if task.completeTimes >= task.times else global_red

            line = global_line.copy()
            line_draw = ImageDraw.Draw(line)
            line.alpha_composite(icon, (0, 5))

            line_draw.text((40, 20), task.remark, COLOR_WHITE, dna_font_26, "lm")

            progress = int(368 + 496 * task.process)
            # 进度条 总长度为496
            get_smooth_drawer().rounded_rectangle((372, 9, progress, 24), 10, COLOR_WHITE, target=line)
            card.alpha_composite(line, (200, start_y))
            start_y += 60

    start_y += 20
    # div
    div = get_div()
    card.alpha_composite(div, (120, start_y))
    start_y += div_h

    # 游戏签到
    award_dict = {award.dayInPeriod: award for award in sign_data.dayAward}
    for day in range(1, sign_data.period.overDays + 1):
        row = (day - 1) // cols
        col = (day - 1) % cols

        item_bg = global_item_bg.copy()
        item_bg_draw = ImageDraw.Draw(item_bg)

        is_signed = day <= sign_data.signinTime
        is_current = day == sign_data.signinTime

        award = award_dict.get(day)
        if award:
            icon_img = await download_pic_from_url(SIGN_PATH, award.iconUrl, size=(140, 140))
            item_bg.alpha_composite(icon_img, (-10, 0))
            item_bg_draw.text((60, 150), f"x{award.awardNum}", COLOR_WHITE, dna_font_28, "mm")

            if is_current:
                get_smooth_drawer().rounded_rectangle(
                    (3, 3, item_bg.width - 3 - 2, item_bg.height - 3 - 32),
                    10,
                    outline=COLOR_GOLDENROD,
                    width=3,
                    target=item_bg,
                )

        icon = global_green if is_signed else global_red
        temp_icon = icon.copy()
        temp_icon = temp_icon.resize((24, 24))
        item_bg.alpha_composite(temp_icon, (10, 190))

        color = COLOR_GRAY
        if is_signed:
            color = COLOR_GREEN

        item_bg_draw.text((70, 200), f"第{day}天", color, dna_font_20, "mm")
        card.alpha_composite(item_bg, (140 + col * 145, start_y + row * 240))

    card = add_footer(card, 600)
    card = await convert_img(card)
    return card


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

    task_process_resp = await dna_api.get_task_process(dna_user.cookie, dna_user.dev_code)
    if not task_process_resp.is_success:
        return

    task_process = DNATaskProcessRes.model_validate(task_process_resp.data)

    default_role = await dna_api.get_default_role_for_tool(dna_user.cookie, dna_user.dev_code)
    if not default_role.is_success:
        await dna_not_found(bot, ev, "角色列表信息")
        return
    default_role = DNARoleForToolRes.model_validate(default_role.data)
    role_show = default_role.roleInfo.roleShow

    # 检查 UID 是否应该被隐藏
    uid_hidden = await is_uid_hidden(ev.user_id, ev.bot_id, ev.group_id)

    msg = await _draw_sign_calendar(
        ev,
        role_show,
        sign_data,
        task_process,
        bbs_total_sign_in_day,
        uid_hidden,
    )
    await bot.send(msg)
