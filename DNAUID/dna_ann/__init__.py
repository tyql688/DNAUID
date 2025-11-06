import asyncio
import random

from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.sv import SV

from ..dna_ann.ann_card import ann_detail_card
from ..dna_config.dna_config import DNAConfig
from ..utils.dna_api import dna_api
from ..utils.msgs.notify import send_dna_notify

sv_ann = SV("DNA公告")
sv_ann_sub = SV("订阅DNA公告", pm=3)

task_name_ann = "订阅DNA公告"
ann_minute_check: int = DNAConfig.get_config("AnnMinuteCheck").data


@sv_ann.on_command("公告")
async def ann_(bot: Bot, ev: Event):
    ann_id = ev.text
    if not ann_id:
        ann_list = await dna_api.get_ann_list()
        if not ann_list:
            return await bot.send("获取公告列表失败")
        anns = "\n".join([f"{x['postId']}" for x in ann_list])
        return await send_dna_notify(bot, ev, f"公告列表: \n{anns}")

    ann_id = ann_id.replace("#", "")
    if not ann_id.isdigit():
        raise Exception("公告ID不正确")

    img = await ann_detail_card(ann_id)
    return await bot.send(img)  # type: ignore


@sv_ann_sub.on_fullmatch("订阅公告")
async def sub_ann_(bot: Bot, ev: Event):
    if ev.bot_id != "onebot":
        logger.debug(f"非onebot禁止订阅二重螺旋公告 【{ev.bot_id}】")
        return

    if ev.group_id is None:
        return await bot.send("请在群聊中订阅")
    if not DNAConfig.get_config("DNAAnnOpen").data:
        return await bot.send("二重螺旋公告推送功能已关闭")

    data = await gs_subscribe.get_subscribe(task_name_ann)
    if data:
        for subscribe in data:
            if subscribe.group_id == ev.group_id:
                return await bot.send("已经订阅了二重螺旋公告！")

    await gs_subscribe.add_subscribe(
        "session",
        task_name=task_name_ann,
        event=ev,
        extra_message="",
    )

    logger.info(data)
    await bot.send("成功订阅二重螺旋公告!")


@sv_ann_sub.on_fullmatch(("取消订阅公告", "取消公告", "退订公告"))
async def unsub_ann_(bot: Bot, ev: Event):
    if ev.bot_id != "onebot":
        logger.debug(f"非onebot禁止订阅二重螺旋公告 【{ev.bot_id}】")
        return

    if ev.group_id is None:
        return await bot.send("请在群聊中取消订阅")

    data = await gs_subscribe.get_subscribe(task_name_ann)
    if data:
        for subscribe in data:
            if subscribe.group_id == ev.group_id:
                await gs_subscribe.delete_subscribe("session", task_name_ann, ev)
                return await bot.send("成功取消订阅二重螺旋公告!")
    else:
        if not DNAConfig.get_config("DNAAnnOpen").data:
            return await bot.send("二重螺旋公告推送功能已关闭")

    return await bot.send("未曾订阅二重螺旋公告！")


@scheduler.scheduled_job("interval", minutes=ann_minute_check)
async def check_dna_ann():
    if not DNAConfig.get_config("DNAAnnOpen").data:
        return
    await check_dna_ann_state()


async def check_dna_ann_state():
    logger.info("[二重螺旋公告] 定时任务: 二重螺旋公告查询..")
    datas = await gs_subscribe.get_subscribe(task_name_ann)
    if not datas:
        logger.info("[二重螺旋公告] 暂无群订阅")
        return

    ids = DNAConfig.get_config("DNAAnnNewIds").data
    new_ann_list = await dna_api.get_ann_list()
    if not new_ann_list:
        return

    new_ann_ids = [x["postId"] for x in new_ann_list]
    if not ids:
        DNAConfig.set_config("DNAAnnNewIds", new_ann_ids)
        logger.info("[二重螺旋公告] 初始成功, 将在下个轮询中更新.")
        return

    new_ann_need_send = []
    for ann_id in new_ann_ids:
        if ann_id not in ids:
            new_ann_need_send.append(ann_id)

    if not new_ann_need_send:
        logger.info("[二重螺旋公告] 没有最新公告")
        return

    logger.info(f"[二重螺旋公告] 更新公告id: {new_ann_need_send}")
    save_ids = sorted(ids, reverse=True)[:50] + new_ann_ids
    DNAConfig.set_config("DNAAnnNewIds", list(set(save_ids)))

    for ann_id in new_ann_need_send:
        try:
            img = await ann_detail_card(ann_id, is_check_time=True)
            if isinstance(img, str):
                continue
            for subscribe in datas:
                await subscribe.send(img)  # type: ignore
                await asyncio.sleep(random.uniform(1, 3))
        except Exception as e:
            logger.exception(e)

    logger.info("[二重螺旋公告] 推送完毕")
