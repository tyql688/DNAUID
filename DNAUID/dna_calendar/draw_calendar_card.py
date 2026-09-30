from enum import StrEnum
from pathlib import Path
from datetime import datetime, timedelta

from PIL import Image, ImageDraw
from pydantic import BaseModel

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import crop_center_img

from ..utils.image import COLOR_GOLDENROD, add_footer, download_pic_from_url
from ..utils.dna_api import dna_api
from ..utils.fonts.dna_fonts import dna_font_origin
from ..utils.resource.RESOURCE_PATH import CALENDAR_PATH

TEXT_PATH = Path(__file__).parent / "texture2d"
time_icon = Image.open(TEXT_PATH / "time_icon.png")


class TimeType(StrEnum):
    MOLING = "moling"
    MIHAN = "mihan"
    ZHOUBEN = "zhouben"


START_TIME = {
    TimeType.MOLING: {
        "start_time": datetime(2026, 1, 3, 5, 0),
        "date_range": 86400 * 3,
    },
    TimeType.MIHAN: {
        "start_time": datetime(2026, 1, 3, 5, 0),
        "date_range": 3600,
    },
    TimeType.ZHOUBEN: {
        "start_time": datetime(2025, 12, 29, 5, 0),
        "date_range": 86400 * 7,
    },
}


def get_time(now: datetime, time_type: TimeType):
    start_time = START_TIME[time_type]["start_time"]
    date_range = START_TIME[time_type]["date_range"]
    date_range_td = timedelta(seconds=date_range)
    elapsed_time = (now - start_time).total_seconds()
    period_index = int(elapsed_time // date_range)
    period_start = start_time + period_index * date_range_td
    period_end = period_start + date_range_td
    start_date_str = period_start.strftime("%Y-%m-%d %H:%M")
    end_date_str = period_end.strftime("%Y-%m-%d %H:%M")

    return {
        "start_time": period_start,
        "end_time": period_end,
        "start_date_str": start_date_str,
        "end_date_str": end_date_str,
    }


class CalendarContent(BaseModel):
    title: str  # 活动标题
    pic: str  # 活动图片
    start_time: str | int  # 活动开始时间
    end_time: str | int  # 活动结束时间


async def draw_calendar_img(ev: Event):
    # 新接口
    activity_res = await dna_api.get_activity_info()
    if activity_res.is_success and isinstance(activity_res.data, dict):
        activity_list = activity_res.data.get("activities", [])
    else:
        activity_list = []

    # 旧接口
    wiki_list = []
    # 旧接口
    wiki_list = []
    wiki_home = await dna_api.get_calendar_info()
    if wiki_home:
        jumu = next(
            filter(
                lambda x: x["sectionType"] == 3 and x.get("activityUps", None) is not None,
                wiki_home,
            ),
            None,
        )
        old_activity_list = next(
            filter(
                lambda x: x["sectionType"] == 3 and x.get("activities", None) is not None,
                wiki_home,
            ),
            None,
        )
        if jumu:
            wiki_list.append(jumu)
        if old_activity_list:
            wiki_list.append(old_activity_list)

    if not activity_list and not wiki_list:
        return "获取日历失败"

    # 当前时间
    now = datetime.now()

    # 魔灵
    moling_time = get_time(now, TimeType.MOLING)
    cc = CalendarContent(
        title="魔灵",
        pic="moling.png",
        start_time=moling_time["start_date_str"],
        end_time=moling_time["end_date_str"],
    )
    content = [cc]

    # 周本
    zhouben_time = get_time(now, TimeType.ZHOUBEN)
    cc = CalendarContent(
        title="周本",
        pic="zhouben.png",
        start_time=zhouben_time["start_date_str"],
        end_time=zhouben_time["end_date_str"],
    )
    content.append(cc)

    # 处理旧接口数据
    if wiki_list:
        for item in wiki_list:
            # jumu activityUps
            if "activityUps" in item:
                for activityUp in item["activityUps"]:
                    start_time = activityUp.get("createTime")
                    end_time = activityUp.get("endTime")
                    name = activityUp.get("name")
                    up_list = [
                        CalendarContent(
                            title=name or c["name"],
                            pic=c["pic"],
                            start_time=int(start_time / 1000) if start_time else "",
                            end_time=int(end_time / 1000) if end_time else "",
                        )
                        for c in activityUp["contents"]
                    ]
                    content.extend(up_list)

            # activities
            if "activities" in item:
                for activity in item["activities"]:
                    cc = CalendarContent(
                        title=activity["name"],
                        pic=activity["pic"],
                        start_time=int(activity["createTime"] / 1000) if activity["createTime"] else "",
                        end_time=int(activity["endTime"] / 1000) if activity["endTime"] else "",
                    )
                    content.append(cc)

    # 处理新接口数据
    if activity_list:
        for activity in activity_list:
            if activity.get("cycleDay", -1) != -1:
                continue
            if "委托密函轮换" in activity["name"]:
                continue
            start_time = activity.get("startTime")
            end_time = activity.get("endTime")
            cc = CalendarContent(
                title=activity["name"],
                pic=activity.get("icon", ""),
                start_time=int(start_time / 1000) if start_time else "",
                end_time=int(end_time / 1000) if end_time else "",
            )
            content.append(cc)

    title_high = 150
    banner_high = 550
    event_high = 170
    bar_high = 60
    temp_high = 20
    footer_high = 100
    content_total_row = 1 + (len(content) - 1) // 2 if content else 0
    total_high = title_high + banner_high + temp_high + content_total_row * event_high + bar_high + footer_high

    img = await get_calendar_bg(1200, total_high)

    # title
    img_draw = ImageDraw.Draw(img)
    img_draw.text((600, 150), "DNAUID | 二重螺旋活动列表一栏 | 皎皎角", (255, 255, 255), dna_font_origin(50), "mm")

    # banner
    await draw_banner(img)
    _high = title_high + banner_high

    # 活动bar
    _high += temp_high
    bar = Image.open(TEXT_PATH / "bar.png")

    img.paste(bar, (0, _high), bar)
    _high += bar_high

    for i, cont in enumerate(content):
        event_bg = Image.open(TEXT_PATH / "event_bg.png")
        event_bg_draw = ImageDraw.Draw(event_bg)

        dateRange = []
        if isinstance(cont.start_time, str):
            dateRange.append(cont.start_time)
        if isinstance(cont.end_time, str):
            dateRange.append(cont.end_time)

        if isinstance(cont.start_time, int) and cont.start_time > 0:
            dateRange.append(datetime.fromtimestamp(cont.start_time).strftime("%Y-%m-%d %H:%M"))
        if isinstance(cont.end_time, int) and cont.end_time > 0:
            dateRange.append(datetime.fromtimestamp(cont.end_time).strftime("%Y-%m-%d %H:%M"))

        if dateRange:
            start_time = datetime.strptime(dateRange[0], "%Y-%m-%d %H:%M")
            end_time = datetime.strptime(dateRange[1], "%Y-%m-%d %H:%M")

            status, left, color = get_date_range(dateRange, now)
            if left:
                event_bg_draw.text((140, 130), f"{left}", color, dna_font_origin(20), "lm")
                status = f"{status}: "

            # 格式化
            formatted_start = start_time.strftime("%m.%d %H:%M")
            formatted_end = end_time.strftime("%m.%d %H:%M")

            # 起止时间
            formatted_date_range = f"{formatted_start} ~ {formatted_end}"
            event_bg_draw.text(
                (40, 95),
                f"{formatted_date_range}",
                "white",
                dna_font_origin(20),
                "lm",
            )
            # 时间小图标
            event_bg.alpha_composite(time_icon, (35, 115))
            # 状态
            event_bg_draw.text(
                (70, 130),
                f"{status}",
                "white",
                dna_font_origin(20),
                "lm",
            )

            # 添加进度条
            progress_x = 25
            progress_y = 155
            progress_width = 485
            progress_height = 8

            # 计算进度百分比
            if status == "已结束":
                # 已结束
                progress = 1
                fill_color = "white"
            else:
                # 进行中
                total_duration = (end_time - start_time).total_seconds()
                elapsed_duration = (now - start_time).total_seconds()
                progress = elapsed_duration / total_duration if total_duration > 0 else 0
                fill_color = "gold" if color == "white" else color

            # 绘制进度条背景
            event_bg_draw.rectangle(
                [
                    progress_x,
                    progress_y,
                    progress_x + progress_width,
                    progress_y + progress_height,
                ],
                fill=(100, 100, 100),  # 灰色背景
            )

            # 绘制进度条前景
            if progress > 0:
                progress_fill_width = int(progress_width * progress)

                event_bg_draw.rectangle(
                    [
                        progress_x,
                        progress_y,
                        progress_x + progress_fill_width,
                        progress_y + progress_height,
                    ],
                    fill=fill_color,
                )

        if cont.pic:
            if "http" in cont.pic:
                linkUrl = await download_pic_from_url(CALENDAR_PATH, cont.pic)
            else:
                linkUrl = Image.open(TEXT_PATH / cont.pic)

            linkUrl = linkUrl.resize((100, 100))
            event_bg.paste(linkUrl, (400, 40), linkUrl)
        event_bg_draw.text(
            (40, 60),
            f"{cont.title}",
            COLOR_GOLDENROD,
            dna_font_origin(30),
            "lm",
        )

        img.alpha_composite(event_bg, (70 + (i % 2) * 540, _high))
        if i % 2 == 1:
            _high += event_high

    img = add_footer(img)
    img = await convert_img(img)
    return img


async def draw_banner(img):
    banner_bg = Image.open(TEXT_PATH / "banner_bg.webp")
    banner_bg = banner_bg.resize((1200, 675))
    banner_mask = Image.open(TEXT_PATH / "banner_mask.png")
    banner_bg = crop_center_img(banner_bg, banner_mask.size[0], banner_mask.size[1])

    banner_bg_temp = Image.new("RGBA", banner_mask.size, (255, 255, 255, 0))
    banner_bg_temp.paste(banner_bg, (0, 0), banner_mask)
    banner_frame_img = Image.open(TEXT_PATH / "banner_frame.png")

    img.paste(banner_bg, (0, 150), banner_mask)
    img.paste(banner_frame_img, (0, 150), banner_frame_img)


async def get_calendar_bg(w: int, h: int, bg: str = "bg") -> Image.Image:
    img = Image.open(TEXT_PATH / f"{bg}.jpg").convert("RGBA")
    return crop_center_img(img, w, h)


def get_left_time_str(remaining_time):
    # 提取天数、小时数和分钟数
    remaining_days = remaining_time.days
    remaining_hours, remaining_minutes = divmod(remaining_time.seconds, 3600)
    remaining_minutes, remaining_seconds = divmod(remaining_minutes, 60)
    # 剩余时间
    return f"还剩{remaining_days}天{remaining_hours}小时{remaining_minutes}分钟"


def get_date_range(dateRange, now):
    start_time = datetime.strptime(dateRange[0], "%Y-%m-%d %H:%M")
    end_time = datetime.strptime(dateRange[1], "%Y-%m-%d %H:%M")
    left = ""
    color = "white"
    if start_time <= now <= end_time:
        # 进行中
        status = "进行中"
        if end_time >= now:
            remaining_time = end_time - now
            left = get_left_time_str(remaining_time)
            if remaining_time.days < 1:
                color = "red"
    elif now > end_time:
        # 已结束
        status = "已结束"
    else:
        # 未开始
        status = "未开始"

    return status, left, color
