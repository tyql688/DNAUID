import asyncio
from typing import Dict, List, Literal

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.boardcast.models import BoardCastMsg, BoardCastMsgDict

from ..dna_config.dna_config import DNASignConfig
from ..utils.boardcast import send_board_cast_msg
from ..utils.constants.boardcast import BoardcastTypeEnum
from ..utils.database.models import DNAUser
from ..utils.fonts.dna_fonts import dna_font_24
from ..utils.msgs.notify import send_dna_notify
from .sign_service import (
    SignService,
    can_bbs_sign,
    can_sign,
    get_sign_interval,
    master_sign,
    sched_sign,
    sign_concurrent_num,
)


async def sign_task(
    dna_user: DNAUser,
    is_manual: bool = True,
    private_msgs: Dict = {},
    group_msgs: Dict = {},
    all_msgs: Dict = {},
    private_bbs_msgs: Dict = {},
    group_bbs_msgs: Dict = {},
    all_bbs_msgs: Dict = {},
):
    expire_uids = []
    result_msgs = []

    def return_msg():
        for uid in expire_uids:
            result_msgs.append(f"失效UID: {uid}")
        return result_msgs

    if not dna_user.cookie or dna_user.status == "无效":
        expire_uids.append(dna_user.uid)
        return return_msg()

    ss = SignService(dna_user.uid, dna_user.cookie, dna_user.dev_code)
    if await ss.check_status():
        result_msgs.append(ss.turn_msg())
        return return_msg()

    if not await ss.token_check():
        expire_uids.append(dna_user.uid)
        return return_msg()

    await ss.do_sign()
    await ss.do_bbs_sign()

    result_msgs.append(ss.turn_msg())

    await ss.save_sign_data()

    if not is_manual:
        sign = ss.get_auto_sign_msg(False)
        await msg_sign(
            sign,
            dna_user.bot_id,
            dna_user.uid,
            dna_user.sign_switch,
            dna_user.user_id,
            private_msgs,
            group_msgs,
            all_msgs,
        )

        bbs_sign = ss.get_auto_sign_msg(True)
        await msg_sign(
            bbs_sign,
            dna_user.bot_id,
            dna_user.uid,
            dna_user.sign_switch,
            dna_user.user_id,
            private_bbs_msgs,
            group_bbs_msgs,
            all_bbs_msgs,
        )

    return return_msg()


async def manual_sign(bot: Bot, ev: Event):
    if not can_sign() and not can_bbs_sign():
        return await send_dna_notify(bot, ev, "签到功能未开启")

    dna_users: List[DNAUser] = await DNAUser.select_dna_users(ev.user_id, ev.bot_id)
    if not dna_users:
        return await send_dna_notify(bot, ev, "请检查登录有效性")

    result_msgs = []
    for dna_user in dna_users:
        _result_msgs = await sign_task(dna_user) or []
        result_msgs.extend(_result_msgs)

    if result_msgs:
        await send_dna_notify(bot, ev, "\n".join(result_msgs))


async def auto_sign():
    if not sched_sign():
        return "[二重螺旋]自动任务\n签到功能未开启"
    if not can_sign() and not can_bbs_sign():
        return "[二重螺旋]自动任务\n签到功能未开启"
    dna_users: List[DNAUser] = await DNAUser.get_dna_all_user()
    if not dna_users:
        return "[二重螺旋]自动任务\n没有需要签到的用户"

    need_sign_users = []
    if master_sign():
        need_sign_users = dna_users
    else:
        # 过滤需要签到的用户
        for dna_user in dna_users:
            if dna_user.sign_switch == "off":
                continue
            need_sign_users.append(dna_user)

    async def process_user(
        semaphore,
        user: DNAUser,
        private_sign_msgs: Dict,
        group_sign_msgs: Dict,
        all_sign_msgs: Dict,
        private_bbs_msgs: Dict,
        group_bbs_msgs: Dict,
        all_bbs_msgs: Dict,
    ):
        async with semaphore:
            return await sign_task(
                user,
                False,
                private_sign_msgs,
                group_sign_msgs,
                all_sign_msgs,
                private_bbs_msgs,
                group_bbs_msgs,
                all_bbs_msgs,
            )

    private_sign_msgs = {}
    group_sign_msgs = {}
    all_sign_msgs = {"failed": 0, "success": 0}

    private_bbs_msgs = {}
    group_bbs_msgs = {}
    all_bbs_msgs = {"failed": 0, "success": 0}

    max_concurrent: int = sign_concurrent_num()
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [
        process_user(
            semaphore,
            user,
            private_sign_msgs,
            group_sign_msgs,
            all_sign_msgs,
            private_bbs_msgs,
            group_bbs_msgs,
            all_bbs_msgs,
        )
        for user in need_sign_users
    ]
    for i in range(0, len(tasks), max_concurrent):
        batch = tasks[i : i + max_concurrent]
        results = await asyncio.gather(*batch, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                return f"{result.args[0]}"

        delay = get_sign_interval()
        logger.info(f"[DNAUID] [自动签到] 等待{delay:.2f}秒进行下一次签到")
        await asyncio.sleep(delay)

    sign_result = await to_board_cast_msg(
        private_sign_msgs, group_sign_msgs, "游戏签到", theme="blue"
    )
    if not DNASignConfig.get_config("PrivateSignReport").data:
        sign_result["private_msg_dict"] = {}
    if not DNASignConfig.get_config("GroupSignReport").data:
        sign_result["group_msg_dict"] = {}
    await send_board_cast_msg(sign_result, BoardcastTypeEnum.SIGN_DNA)

    bbs_result = await to_board_cast_msg(
        private_bbs_msgs, group_bbs_msgs, "社区签到", theme="yellow"
    )
    if not DNASignConfig.get_config("PrivateSignReport").data:
        bbs_result["private_msg_dict"] = {}
    if not DNASignConfig.get_config("GroupSignReport").data:
        bbs_result["group_msg_dict"] = {}
    await send_board_cast_msg(bbs_result, BoardcastTypeEnum.SIGN_DNA)

    return f"[二重螺旋]自动任务\n今日成功游戏签到 {all_sign_msgs['success']} 个账号\n今日社区签到 {all_bbs_msgs['success']} 个账号"


async def to_board_cast_msg(
    private_msgs,
    group_msgs,
    type: Literal["社区签到", "游戏签到"] = "社区签到",
    theme: str = "yellow",
):
    # 转为广播消息
    private_msg_dict: Dict[str, List[BoardCastMsg]] = {}
    group_msg_dict: Dict[str, BoardCastMsg] = {}
    for qid in private_msgs:
        msgs = []
        for i in private_msgs[qid]:
            msgs.extend(i["msg"])

        if qid not in private_msg_dict:
            private_msg_dict[qid] = []

        private_msg_dict[qid].append(
            {
                "bot_id": private_msgs[qid][0]["bot_id"],
                "messages": msgs,
            }
        )

    failed_num = 0
    success_num = 0
    for gid in group_msgs:
        success = group_msgs[gid]["success"]
        faild = group_msgs[gid]["failed"]
        success_num += int(success)
        failed_num += int(faild)
        title = f"✅[二重螺旋]今日{type}任务已完成！\n本群共签到成功{success}人\n共签到失败{faild}人"
        messages = []
        if DNASignConfig.get_config("GroupSignReportPic").data:
            image = create_sign_info_image(title, theme="yellow")
            messages.append(MessageSegment.image(image))
        else:
            messages.append(MessageSegment.text(title))
        if group_msgs[gid]["push_message"]:
            messages.append(MessageSegment.text("\n"))
            messages.extend(group_msgs[gid]["push_message"])
        group_msg_dict[gid] = {
            "bot_id": group_msgs[gid]["bot_id"],
            "messages": messages,
        }

    result: BoardCastMsgDict = {
        "private_msg_dict": private_msg_dict,
        "group_msg_dict": group_msg_dict,
    }
    return result


def create_gradient_background(width, height, start_color, end_color=(255, 255, 255)):
    """
    使用 PIL 创建渐变背景
    start_color: 起始颜色，如 (230, 230, 255) 浅蓝
    end_color: 结束颜色，默认白色
    """
    # 创建新图像
    image = Image.new("RGB", (width, height))

    for y in range(height):
        # 计算当前行的颜色比例
        ratio = y / height

        # 计算当前行的 RGB 值
        r = int(end_color[0] * ratio + start_color[0] * (1 - ratio))
        g = int(end_color[1] * ratio + start_color[1] * (1 - ratio))
        b = int(end_color[2] * ratio + start_color[2] * (1 - ratio))

        # 创建当前行的颜色
        line_color = (r, g, b)
        # 绘制当前行
        for x in range(width):
            image.putpixel((x, y), line_color)

    return image


def create_sign_info_image(text, theme="blue"):
    text = text[1:]
    # 创建图片
    width = 600
    height = 250  # 稍微减小高度使布局更紧凑

    # 预定义主题颜色
    themes = {
        "blue": (230, 230, 255),  # 浅蓝
        "yellow": (255, 255, 230),  # 浅黄
        "pink": (255, 230, 230),  # 浅粉
        "green": (230, 255, 230),  # 浅绿
    }

    # 获取主题颜色，默认浅蓝
    start_color = themes.get(theme, themes["blue"])

    # 创建渐变背景
    img = create_gradient_background(width, height, start_color)
    draw = ImageDraw.Draw(img)

    # 颜色定义
    title_color = (51, 51, 51)  # 标题色

    # 绘制装饰边框
    border_color = (200, 200, 200)
    draw.rectangle([(10, 10), (width - 10, height - 10)], outline=border_color, width=2)

    # 文本处理
    lines = text.split("\n")
    left_margin = 40  # 左边距
    y = 40  # 起始y坐标

    for i, line in enumerate(lines):
        draw.text((left_margin, y), line, font=dna_font_24, fill=title_color)
        if i == 0:
            y += 60
        else:
            y += 45

    return img


async def msg_sign(
    im: str,
    bot_id: str,
    uid: str,
    gid: str,
    qid: str,
    private_msgs: Dict,
    group_msgs: Dict,
    all_msgs: Dict,
):
    if "禁止" in im:
        return

    if gid == "on":
        if qid not in private_msgs:
            private_msgs[qid] = []
        private_msgs[qid].append(
            {"bot_id": bot_id, "uid": uid, "msg": [MessageSegment.text(content=im)]}
        )
        if "失败" in im:
            all_msgs["failed"] += 1
        else:
            all_msgs["success"] += 1
    elif gid == "off":
        if "失败" in im:
            all_msgs["failed"] += 1
        else:
            all_msgs["success"] += 1
    else:
        # 向群消息推送列表添加这个群
        if gid not in group_msgs:
            group_msgs[gid] = {
                "bot_id": bot_id,
                "success": 0,
                "failed": 0,
                "push_message": [],
            }
        if "失败" in im:
            all_msgs["failed"] += 1
            group_msgs[gid]["failed"] += 1
            group_msgs[gid]["push_message"].extend(
                [
                    MessageSegment.text("\n"),
                    MessageSegment.at(qid),
                    MessageSegment.text(im),
                ]
            )
        else:
            all_msgs["success"] += 1
            group_msgs[gid]["success"] += 1
