from __future__ import annotations

import random
import asyncio

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.subscribe import gs_subscribe

from .utils import resolve_index, fetch_ann_list, build_index_map
from .ann_card import draw_ann_list_img, draw_ann_detail_img
from ..utils.dna_api import dna_api
from ..utils.msgs.notify import send_dna_notify
from ..dna_config.dna_config import DNAConfig

sv_ann = SV("DNA公告")
sv_ann_sub = SV("订阅DNA公告", pm=3)

TASK_NAME_ANN = "订阅DNA公告"
ANN_MIN_CHECK: int = DNAConfig.get_config("AnnMinuteCheck").data or 10


def _as_message(img: bytes | list[bytes]) -> bytes | list[Message]:
    return img if isinstance(img, bytes) else [Message(type="image", data=part) for part in img]


@sv_ann.on_command("公告")
async def ann_dna(bot: Bot, ev: Event):
    text = ev.text.strip().replace("#", "")

    if not text:
        result = await draw_ann_list_img()
        if isinstance(result, str):
            return await send_dna_notify(bot, ev, result)
        return await bot.send(result)

    posts = await fetch_ann_list(prefer_cache=True)
    if not posts:
        return await send_dna_notify(bot, ev, "获取公告列表失败")

    post_id = resolve_index(text, build_index_map(posts))
    if post_id is None:
        return await send_dna_notify(bot, ev, "公告序号不正确，发送 公告 查看可用列表")

    result = await draw_ann_detail_img(post_id)
    if isinstance(result, str):
        return await send_dna_notify(bot, ev, result)
    return await bot.send(_as_message(result))


@sv_ann_sub.on_fullmatch("订阅公告")
async def sub_ann_dna(bot: Bot, ev: Event):
    if not ev.group_id:
        return await send_dna_notify(bot, ev, "请在群聊中订阅")
    if not DNAConfig.get_config("DNAAnnOpen").data:
        return await send_dna_notify(bot, ev, "二重螺旋公告推送功能已关闭")

    data = await gs_subscribe.get_subscribe(TASK_NAME_ANN)
    if data and any(sub.group_id == ev.group_id for sub in data):
        return await send_dna_notify(bot, ev, "已经订阅了二重螺旋公告！")

    await gs_subscribe.add_subscribe("session", TASK_NAME_ANN, ev, extra_message="")
    await send_dna_notify(bot, ev, "成功订阅二重螺旋公告！")


@sv_ann_sub.on_fullmatch(("取消订阅公告", "取消公告", "退订公告"))
async def unsub_ann_dna(bot: Bot, ev: Event):
    if not ev.group_id:
        return await send_dna_notify(bot, ev, "请在群聊中取消订阅")

    data = await gs_subscribe.get_subscribe(TASK_NAME_ANN)
    if data and any(sub.group_id == ev.group_id for sub in data):
        await gs_subscribe.delete_subscribe("session", TASK_NAME_ANN, ev)
        return await send_dna_notify(bot, ev, "成功取消订阅二重螺旋公告！")

    if not DNAConfig.get_config("DNAAnnOpen").data:
        return await send_dna_notify(bot, ev, "二重螺旋公告推送功能已关闭")
    return await send_dna_notify(bot, ev, "未曾订阅二重螺旋公告！")


@scheduler.scheduled_job("interval", minutes=ANN_MIN_CHECK)
async def check_dna_ann():
    if not DNAConfig.get_config("DNAAnnOpen").data:
        return
    await check_dna_ann_state()


async def check_dna_ann_state():
    logger.info("[二重螺旋公告] 定时任务: 二重螺旋公告查询..")
    subs = await gs_subscribe.get_subscribe(TASK_NAME_ANN)
    if not subs:
        logger.info("[二重螺旋公告] 暂无群订阅")
        return

    new_ann_list = await dna_api.get_ann_list()
    if not new_ann_list:
        return

    known_ids: list[int] = DNAConfig.get_config("DNAAnnIds").data or []
    fresh_ids = [int(post["postId"]) for post in new_ann_list]

    if not known_ids:
        DNAConfig.set_config("DNAAnnIds", fresh_ids)
        logger.info("[二重螺旋公告] 初始成功, 将在下个轮询中更新.")
        return

    pending = [post_id for post_id in fresh_ids if post_id not in known_ids]
    if not pending:
        logger.info("[二重螺旋公告] 没有最新公告")
        return

    logger.info(f"[二重螺旋公告] 更新公告id: {pending}")
    merged = sorted(set(known_ids) | set(fresh_ids), reverse=True)[:50]
    DNAConfig.set_config("DNAAnnIds", merged)

    for post_id in pending:
        try:
            img = await draw_ann_detail_img(post_id, is_check_time=True)
            if isinstance(img, str):
                continue
            for sub in subs:
                await sub.send(_as_message(img))
                await asyncio.sleep(random.uniform(1, 3))
        except Exception as e:
            logger.exception(e)

    logger.info("[二重螺旋公告] 推送完毕")
