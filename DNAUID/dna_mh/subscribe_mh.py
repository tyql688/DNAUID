import asyncio
import random
from collections import defaultdict
from datetime import timedelta
from typing import List, Literal, Optional

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

from ..dna_config.prefix import DNA_PREFIX
from ..utils import dna_api, get_datetime
from ..utils.api.mh_map import get_mh_type_name
from ..utils.constants.boardcast import BoardcastTypeEnum
from ..utils.database.models import DNABind
from ..utils.msgs.notify import (
    dna_token_invalid,
    dna_uid_invalid,
    send_dna_notify,
)
from .cache_mh import get_mh_result


def list2str(lst: List[str]) -> str:
    slst = set(lst)
    return ",".join(slst)


def str2list(s: str) -> List[str]:
    return s.split(",")


async def option_add_mh(bot: Bot, ev: Event, uid: str, mh_name: str):
    if mh_name == "全部":
        await send_dna_notify(
            bot, ev, f"禁止订阅全部密函, 请使用[{DNA_PREFIX}密函列表]命令查看可订阅密函"
        )
        return
    data = await gs_subscribe.get_subscribe(
        BoardcastTypeEnum.MH_SUBSCRIBE,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        uid=uid,
        WS_BOT_ID=ev.WS_BOT_ID,
    )
    if not data:
        await gs_subscribe.add_subscribe(
            "single",
            BoardcastTypeEnum.MH_SUBSCRIBE,
            ev,
            uid=uid,
            extra_message=list2str([mh_name]),
        )
        await send_dna_notify(bot, ev, f"成功订阅密函【{mh_name}】")
    else:
        for item in data:
            if not item.extra_message:
                await gs_subscribe.add_subscribe(
                    "single",
                    BoardcastTypeEnum.MH_SUBSCRIBE,
                    ev,
                    uid=uid,
                    extra_message=list2str([mh_name]),
                )
                await send_dna_notify(bot, ev, f"成功订阅密函【{mh_name}】")
                continue
            if mh_name in item.extra_message:
                await send_dna_notify(bot, ev, f"请勿重复订阅密函【{mh_name}】")
                continue
            extra_message = list2str(str2list(item.extra_message) + [mh_name])
            await gs_subscribe.update_subscribe_message(
                "single",
                BoardcastTypeEnum.MH_SUBSCRIBE,
                ev,
                uid=uid,
                extra_message=extra_message,
            )
            await send_dna_notify(
                bot,
                ev,
                f"成功订阅密函【{mh_name}】!当前订阅密函: {extra_message}",
            )


async def option_delete_mh(bot: Bot, ev: Event, uid: str, mh_name: str):
    data = await gs_subscribe.get_subscribe(
        BoardcastTypeEnum.MH_SUBSCRIBE,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        uid=uid,
        WS_BOT_ID=ev.WS_BOT_ID,
    )
    if not data:
        await send_dna_notify(bot, ev, f"未曾订阅密函【{mh_name}】")
        return
    if mh_name == "全部":
        await gs_subscribe.delete_subscribe(
            "single",
            BoardcastTypeEnum.MH_SUBSCRIBE,
            ev,
            uid=uid,
        )
        await send_dna_notify(bot, ev, "成功取消订阅全部密函!")
        return

    for item in data:
        if not item.extra_message or mh_name not in item.extra_message:
            await send_dna_notify(bot, ev, f"未曾订阅密函【{mh_name}】")
            continue

        extra_message = list2str(
            [i for i in str2list(item.extra_message) if i != mh_name]
        )
        await gs_subscribe.update_subscribe_message(
            "single",
            BoardcastTypeEnum.MH_SUBSCRIBE,
            ev,
            uid=uid,
            extra_message=extra_message,
        )
        await send_dna_notify(
            bot,
            ev,
            f"成功取消订阅密函【{mh_name}】!当前订阅密函: {extra_message}",
        )


async def subscribe_mh(bot: Bot, ev: Event, mh_name: str):
    dna_uid = await DNABind.get_uid_by_game(ev.user_id, ev.bot_id)
    if not dna_uid:
        await dna_uid_invalid(bot, ev)
        return

    dna_user = await dna_api.get_dna_user(dna_uid, ev.user_id, ev.bot_id)
    if not dna_user:
        await dna_token_invalid(bot, ev)
        return

    if "取消" in ev.raw_text:
        await option_delete_mh(bot, ev, dna_user.uid, mh_name)
    else:
        await option_add_mh(bot, ev, dna_user.uid, mh_name)


async def get_mh_subscribe_list(bot: Bot, ev: Event, uid: str) -> Optional[List[str]]:
    subscribe_data = await gs_subscribe.get_subscribe(
        BoardcastTypeEnum.MH_SUBSCRIBE,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        WS_BOT_ID=ev.WS_BOT_ID,
        uid=uid,
    )
    if not subscribe_data:
        return
    if not subscribe_data[0].extra_message:
        return

    mh_list = str2list(subscribe_data[0].extra_message)
    return mh_list


async def get_mh_subscribe(bot: Bot, ev: Event):
    dna_uid = await DNABind.get_uid_by_game(ev.user_id, ev.bot_id)
    if not dna_uid:
        await dna_uid_invalid(bot, ev)
        return

    dna_user = await dna_api.get_dna_user(dna_uid, ev.user_id, ev.bot_id)
    if not dna_user:
        await dna_token_invalid(bot, ev)
        return

    mh_list = await get_mh_subscribe_list(bot, ev, dna_user.uid)
    if not mh_list:
        await send_dna_notify(bot, ev, "未曾订阅密函")
        return
    return await send_dna_notify(bot, ev, f"当前订阅密函: {','.join(mh_list)}")


async def send_mh_notify():
    subscribe_data = await gs_subscribe.get_subscribe(BoardcastTypeEnum.MH_SUBSCRIBE)
    if not subscribe_data:
        return

    now = get_datetime()

    next_refresh = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    mh_result = await get_mh_result(int(next_refresh.timestamp()))
    if not mh_result:
        logger.warning("未找到有效的密函数据")
        return

    mh_datas = {"role": [], "weapon": [], "mzx": []}
    # {"拆解": ["role", "weapon"]}
    mh_re_datas: defaultdict[str, list[Literal["role", "weapon", "mzx"]]] = defaultdict(
        list
    )
    for ins in mh_result:
        if not ins.mh_type:
            continue

        for m in ins.instances:
            mh_name = m.name.split("/")[0]
            mh_datas[ins.mh_type].append(mh_name)
            mh_re_datas[mh_name].append(ins.mh_type)
    # set("拆解", "勘探", "追缉")
    mh_name_set = set(mh_re_datas.keys())

    async def private_push(subscribe: Subscribe, valid_mh_list: list[str]):
        if not valid_mh_list:
            return

        push_msg = []
        for mh_name in valid_mh_list:
            mh_type_list = mh_re_datas[mh_name]
            for mh_type in mh_type_list:
                mh_type_name = get_mh_type_name(mh_type)
                push_msg.append(f"{mh_type_name} : {mh_name}")

        if push_msg:
            push_msg.insert(0, "当前订阅密函已刷新:")
            await subscribe.send("\n".join(push_msg))
            await asyncio.sleep(0.5 + random.randint(1, 3))

    # 群聊数据
    groupid2sub = {}
    # {group_id: {"mh_type_name: mh_name": [@user_id]}}
    groupid2push_msg: defaultdict[str, defaultdict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )

    async def group_push(subscribe: Subscribe, valid_mh_list: list[str]):
        if not valid_mh_list:
            return
        if not subscribe.group_id:
            return
        for mh_name in valid_mh_list:
            mh_type_list = mh_re_datas[mh_name]
            for mh_type in mh_type_list:
                mh_type_name = get_mh_type_name(mh_type)
                groupid2push_msg[subscribe.group_id][
                    f"{mh_type_name} : {mh_name}"
                ].append(subscribe.user_id)

        if subscribe.group_id not in groupid2sub:
            groupid2sub[subscribe.group_id] = subscribe

    for subscribe in subscribe_data:
        if not subscribe.extra_message:
            continue

        valid_mh_list = []
        for i in mh_name_set:
            if i in subscribe.extra_message:
                valid_mh_list.append(i)

        if subscribe.user_type == "direct":
            await private_push(subscribe, valid_mh_list)
        elif subscribe.user_type == "group" and subscribe.group_id:
            await group_push(subscribe, valid_mh_list)

    for group_id, _sub in groupid2sub.items():
        _sub: Subscribe
        push_msg = groupid2push_msg[group_id]
        if not push_msg:
            continue

        build_push_msg: List[Message] = [
            MessageSegment.text("当前订阅密函已刷新"),
            MessageSegment.text("\n"),
        ]

        for key, user_list in push_msg.items():
            build_push_msg.append(MessageSegment.text(f"{key}"))
            build_push_msg.append(MessageSegment.text("\n"))
            for user_id in user_list:
                build_push_msg.append(MessageSegment.at(user_id))
            build_push_msg.append(MessageSegment.text("\n"))

        await _sub.send(build_push_msg)
        await asyncio.sleep(0.5 + random.randint(1, 3))
