import re
import html
import time
from datetime import datetime
from typing import List, Union

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import easy_paste

from ..utils import dna_api
from ..utils.image import download_pic_from_url
from ..utils.fonts.dna_fonts import unicode_font_26
from ..utils.resource.RESOURCE_PATH import ANN_CARD_PATH


async def ann_batch_card(post_content: List, drow_height: float) -> bytes:
    im = Image.new("RGB", (1080, drow_height), "#f9f6f2")  # type: ignore
    draw = ImageDraw.Draw(im)
    x, y = 0, 0

    for temp in post_content:
        if temp["contentType"] == 1:
            content = temp["content"]
            drow_duanluo, _, drow_line_height, _ = split_text(content)
            for duanluo, line_count in drow_duanluo:
                draw.text((x, y), duanluo, fill=(0, 0, 0), font=unicode_font_26)
                y += drow_line_height * line_count + 30
        elif (
            temp["contentType"] == 2
            and "url" in temp
            and temp["url"].endswith(("jpg", "png", "jpeg"))
        ):
            # img = await get_pic(temp["url"], (temp["imgWidth"], temp["imgHeight"]))
            img = await download_pic_from_url(ANN_CARD_PATH, temp["url"])
            img_x = 0
            if img.width > im.width:
                ratio = im.width / img.width
                img = img.resize((int(img.width * ratio), int(img.height * ratio)))
            else:
                img_x = (im.width - img.width) // 2
            easy_paste(im, img, (img_x, y))
            y += img.size[1] + 40
        elif (
            temp["contentType"] == 5
            and "contentVideo" in temp
            and "coverUrl" in temp["contentVideo"]
            and temp["contentVideo"]["coverUrl"].endswith(("jpg", "png", "jpeg"))
        ):
            try:
                video_temp = temp["contentVideo"]
                img = await download_pic_from_url(ANN_CARD_PATH, video_temp["coverUrl"])
                img_x = 0
                if img.width > im.width:
                    ratio = im.width / img.width
                    img = img.resize((int(img.width * ratio), int(img.height * ratio)))
                else:
                    img_x = (im.width - img.width) // 2
                easy_paste(im, img, (img_x, y))
                y += img.size[1] + 40
            except Exception:
                pass

    if hasattr(unicode_font_26, "getbbox"):
        bbox = unicode_font_26.getbbox("囗")
        padding = (
            int(bbox[2] - bbox[0]),
            int(bbox[3] - bbox[1]),
            int(bbox[2] - bbox[0]),
            int(bbox[3] - bbox[1]),
        )
    else:
        w, h = unicode_font_26.getsize("囗")  # type: ignore
        padding = (w, h, w, h)
    return await convert_img(ImageOps.expand(im, padding, "#f9f6f2"))


async def ann_detail_card(
    post_id: Union[int, str], is_check_time=False
) -> Union[bytes, str, List[bytes]]:
    post_id = str(post_id)
    ann_list = await dna_api.get_ann_list(True)
    if not ann_list:
        raise Exception("获取游戏公告失败,请检查接口是否正常")
    content = [x for x in ann_list if x["postId"] == post_id]
    if not content:
        return "未找到该公告"

    res = await dna_api.get_post_detail(post_id)
    if not res.is_success or not res.data or not isinstance(res.data, dict):
        return "未找到该公告"

    post_data = res.data
    post_detail = post_data["postDetail"]

    if is_check_time:
        post_time = format_post_time(post_detail["postTime"])
        now_time = int(time.time())
        logger.debug(
            f"公告id: {post_id}, post_time: {post_time}, now_time: {now_time}, delta: {now_time-post_time}"
        )
        if post_time and post_time < now_time - 86400:
            return "该公告已过期"

    post_content = post_detail["postContent"]
    if not post_content:
        return "未找到该公告"

    drow_height = 0
    index_start = 0
    index_end = 0
    imgs = []
    for index, temp in enumerate(post_content):
        content_type = temp["contentType"]
        if content_type == 1:
            # 文案
            content = temp["content"]
            (
                x_drow_duanluo,
                x_drow_note_height,
                x_drow_line_height,
                x_drow_height,
            ) = split_text(content)
            drow_height += x_drow_height + 30
        elif (
            content_type == 2
            and "url" in temp
            and temp["url"].endswith(("jpg", "png", "jpeg"))
        ):
            # 图片
            img = await download_pic_from_url(ANN_CARD_PATH, temp["url"])
            img_height = img.size[1]
            if img.width > 1080:
                ratio = 1080 / img.width
                img_height = int(img.height * ratio)
            drow_height += img_height + 40
        elif (
            content_type == 5
            and "contentVideo" in temp
            and "coverUrl" in temp["contentVideo"]
            and temp["contentVideo"]["coverUrl"].endswith(("jpg", "png", "jpeg"))
        ):
            try:
                # 视频图片
                video_temp = temp["contentVideo"]
                img = await download_pic_from_url(ANN_CARD_PATH, video_temp["coverUrl"])
                img_height = img.size[1]
                if img.width > 1080:
                    ratio = 1080 / img.width
                    img_height = int(img.height * ratio)
                drow_height += img_height + 40
            except Exception:
                pass

        index_end = index + 1
        if drow_height > 5000:
            img = await ann_batch_card(post_content[index_start:index_end], drow_height)
            index_start = index_end
            index_end = index + 1
            drow_height = 0
            imgs.append(img)

    if index_start == 0:
        return await ann_batch_card(post_content[index_start:], drow_height)
    else:
        return imgs


def split_text(content: str):
    # 常见 HTML 实体与换行的预处理
    content = _normalize_content(content)
    # 按规定宽度分组
    max_line_height, total_lines = 0, 0
    allText = []
    for text in content.split("\n"):
        duanluo, line_height, line_count = get_duanluo(text)
        max_line_height = max(line_height, max_line_height)
        total_lines += line_count
        allText.append((duanluo, line_count))
    line_height = max_line_height
    total_height = total_lines * line_height
    drow_height = total_lines * line_height
    return allText, total_height, line_height, drow_height


def get_duanluo(text: str):
    txt = Image.new("RGBA", (600, 800), (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt)
    # 所有文字的段落
    duanluo = ""
    max_width = 1050
    # 宽度总和
    sum_width = 0
    # 几行
    line_count = 1
    # 行高
    line_height = 0
    for char in text:
        left, top, right, bottom = draw.textbbox((0, 0), char, unicode_font_26)
        width, height = (right - left, bottom - top)
        sum_width += width
        if sum_width > max_width:  # 超过预设宽度就修改段落 以及当前行数
            line_count += 1
            sum_width = 0
            duanluo += "\n"
        duanluo += char
        line_height = max(height, line_height)
    if not duanluo.endswith("\n"):
        duanluo += "\n"
    return duanluo, line_height, line_count


def _normalize_content(content: str) -> str:
    try:
        text = html.unescape(content)
    except Exception:
        text = content
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace("\u00a0", " ")

    return text


def format_post_time(post_time: str) -> int:
    try:
        full_time = f"{datetime.now().year}-{post_time}"
        timestamp = datetime.strptime(full_time, "%Y-%m-%d").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    # 17小时前 正则转化为timestamp
    try:
        match = re.search(r"(\d+)小时前", post_time)
        if match:
            hours = int(match.group(1))
            return int(time.time()) - hours * 3600
    except Exception:
        pass

    try:
        timestamp = datetime.strptime(post_time, "%Y-%m-%d").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    try:
        timestamp = datetime.strptime(post_time, "%Y-%m-%d %H:%M").timestamp()
        return int(timestamp)
    except ValueError:
        pass

    return 0
