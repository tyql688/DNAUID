from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe

from ..dna_config.prefix import dna_prefix
from ..utils.msgs.notify import send_dna_notify
from ..utils.constants.boardcast import BoardcastTypeEnum


def list2str(lst: list[str]) -> str:
    slst = set(lst)
    return ",".join(slst)


def str2list(s: str) -> list[str]:
    return s.split(",")


def subscribe_mh_key(mh_name: str, mh_type: str | None = None) -> str:
    return mh_name if not mh_type else f"{mh_type}:{mh_name}"


async def option_add_mh(bot: Bot, ev: Event, user_id: str, mh_name: str, mh_type: str | None = None):
    if mh_name == "全部":
        await send_dna_notify(bot, ev, f"禁止订阅全部密函, 请使用[{dna_prefix()}密函列表]命令查看可订阅密函")
        return

    if not mh_type:
        sub_list = [f"角色:{mh_name}", f"武器:{mh_name}", f"魔之楔:{mh_name}"]
    else:
        sub_list = [f"{mh_type}:{mh_name}"]

    data = await gs_subscribe.get_subscribe(
        BoardcastTypeEnum.MH_SUBSCRIBE,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        uid=user_id,
        WS_BOT_ID=ev.WS_BOT_ID,
    )
    if not data:
        await gs_subscribe.add_subscribe(
            "single",
            BoardcastTypeEnum.MH_SUBSCRIBE,
            ev,
            uid=user_id,
            extra_message=list2str(sub_list),
        )
        await send_dna_notify(bot, ev, f"成功订阅密函【{','.join(sub_list)}】")
    else:
        for item in data:
            if not item.extra_message:
                await gs_subscribe.add_subscribe(
                    "single",
                    BoardcastTypeEnum.MH_SUBSCRIBE,
                    ev,
                    uid=user_id,
                    extra_message=list2str(sub_list),
                )
                await send_dna_notify(bot, ev, f"成功订阅密函【{','.join(sub_list)}】")
                continue
            old_list = str2list(item.extra_message)

            if len(set(sub_list) & set(old_list)) == len(sub_list):
                await send_dna_notify(bot, ev, f"请勿重复订阅密函【{mh_name}】")
                continue

            extra_message = list2str(list(set(old_list + sub_list)))
            await gs_subscribe.update_subscribe_message(
                "single",
                BoardcastTypeEnum.MH_SUBSCRIBE,
                ev,
                uid=user_id,
                extra_message=extra_message,
            )
            await send_dna_notify(
                bot,
                ev,
                f"成功订阅密函【{mh_name}】!当前订阅密函: {extra_message}",
            )


async def option_delete_mh(bot: Bot, ev: Event, user_id: str, mh_name: str, mh_type: str | None = None):
    data = await gs_subscribe.get_subscribe(
        BoardcastTypeEnum.MH_SUBSCRIBE,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        uid=user_id,
        WS_BOT_ID=ev.WS_BOT_ID,
    )
    if not data:
        await send_dna_notify(bot, ev, "未曾订阅密函")
        return
    if mh_name == "全部":
        await gs_subscribe.delete_subscribe(
            "single",
            BoardcastTypeEnum.MH_SUBSCRIBE,
            ev,
            uid=user_id,
        )
        await send_dna_notify(bot, ev, "成功取消订阅全部密函!")
        return

    if not mh_type:
        sub_list = [f"角色:{mh_name}", f"武器:{mh_name}", f"魔之楔:{mh_name}"]
    else:
        sub_list = [f"{mh_type}:{mh_name}"]

    for item in data:
        if not item.extra_message:
            await send_dna_notify(bot, ev, f"未曾订阅密函【{mh_name}】")
            continue

        old_list = str2list(item.extra_message)
        extra_message = list2str(list(set(old_list) - set(sub_list)))
        await gs_subscribe.update_subscribe_message(
            "single",
            BoardcastTypeEnum.MH_SUBSCRIBE,
            ev,
            uid=user_id,
            extra_message=extra_message,
        )
        await send_dna_notify(
            bot,
            ev,
            f"成功取消订阅密函【{mh_name}】!当前订阅密函: {extra_message}",
        )


async def subscribe_mh(
    bot: Bot,
    ev: Event,
    mh_name: str,
    mh_type: str | None = None,
):
    if "取消" in ev.raw_text:
        await option_delete_mh(bot, ev, ev.user_id, mh_name, mh_type)
    else:
        await option_add_mh(bot, ev, ev.user_id, mh_name, mh_type)


async def subscribe_mh_time(
    bot: Bot,
    ev: Event,
    user_id: str,
    start_time: int,
    end_time: int,
):
    data = await gs_subscribe.get_subscribe(
        BoardcastTypeEnum.MH_SUBSCRIBE,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        WS_BOT_ID=ev.WS_BOT_ID,
        uid=user_id,
    )
    if not data:
        await send_dna_notify(bot, ev, "未曾订阅密函")
        return

    await gs_subscribe.update_subscribe_data(
        "single",
        BoardcastTypeEnum.MH_SUBSCRIBE,
        ev,
        extra_data=f"{start_time}:{end_time}",
        uid=user_id,
    )

    await get_mh_subscribe(bot, ev)


async def subscribe_mh_pic(
    bot: Bot,
    ev: Event,
):
    if "取消" in ev.raw_text:
        data = await gs_subscribe.get_subscribe(
            BoardcastTypeEnum.MH_PIC_SUBSCRIBE,
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            user_type=ev.user_type,
            WS_BOT_ID=ev.WS_BOT_ID,
        )
        if not data:
            await send_dna_notify(bot, ev, "未曾订阅密函图片")
            return

        await gs_subscribe.delete_subscribe(
            "session",
            BoardcastTypeEnum.MH_PIC_SUBSCRIBE,
            ev,
        )
        await send_dna_notify(bot, ev, "成功取消订阅密函图片")
    else:
        await gs_subscribe.add_subscribe(
            "session",
            BoardcastTypeEnum.MH_PIC_SUBSCRIBE,
            ev,
        )
        await send_dna_notify(bot, ev, "成功订阅密函图片")


async def subscribe_mh_text(
    bot: Bot,
    ev: Event,
):
    if "取消" in ev.raw_text:
        data = await gs_subscribe.get_subscribe(
            BoardcastTypeEnum.MH_TEXT_SUBSCRIBE,
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            user_type=ev.user_type,
            WS_BOT_ID=ev.WS_BOT_ID,
        )
        if not data:
            await send_dna_notify(bot, ev, "未曾订阅密函文本")
            return

        await gs_subscribe.delete_subscribe(
            "session",
            BoardcastTypeEnum.MH_TEXT_SUBSCRIBE,
            ev,
        )
        await send_dna_notify(bot, ev, "成功取消订阅密函文本")
    else:
        await gs_subscribe.add_subscribe(
            "session",
            BoardcastTypeEnum.MH_TEXT_SUBSCRIBE,
            ev,
        )
        await send_dna_notify(bot, ev, "成功订阅密函文本")


async def get_mh_subscribe_list(bot: Bot, ev: Event, user_id: str) -> tuple[list[str], str]:
    subscribe_data = await gs_subscribe.get_subscribe(
        BoardcastTypeEnum.MH_SUBSCRIBE,
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        user_type=ev.user_type,
        WS_BOT_ID=ev.WS_BOT_ID,
        uid=user_id,
    )
    if not subscribe_data:
        return [], ""
    if not subscribe_data[0].extra_message:
        return [], ""

    mh_list = str2list(subscribe_data[0].extra_message)
    push_time = subscribe_data[0].extra_data or ""
    return mh_list, push_time


async def get_mh_subscribe(bot: Bot, ev: Event):
    mh_list, push_time = await get_mh_subscribe_list(bot, ev, ev.user_id)
    if not mh_list:
        await send_dna_notify(bot, ev, "未曾订阅密函")
        return
    msg = [
        f"当前订阅密函: {','.join(mh_list)}",
    ]
    if push_time:
        start_time, end_time = push_time.split(":")
        msg.append(f"推送时间: {start_time}点-{end_time}点")
    else:
        msg.append("推送时间: 不限制")
        msg.append(f"可以使用命令设置推送时间: {dna_prefix()}订阅密函时间17:23")
    return await send_dna_notify(bot, ev, "\n".join(msg))
