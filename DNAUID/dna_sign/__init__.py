from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.sv import SV

from ..dna_config.dna_config import DNASignConfig
from ..utils.constants.boardcast import BoardcastTypeEnum
from ..utils.database.models import DNASign
from ..utils.utils import get_two_days_ago_date
from .draw_sign import draw_sign_calendar
from .sign import auto_sign, manual_sign

sv_dna_sign = SV("dna签到", priority=1)
sv_dna_sign_all = SV("dna全部签到", pm=1)
sv_dna_sign_calendar = SV("dna签到日历")

SIGN_TIME = DNASignConfig.get_config("SignTime").data
try:
    hour, minute = SIGN_TIME.split(":")
    int_hour = int(hour)
    int_minute = int(minute)
    if int_hour < 0 or int_hour > 23 or int_minute < 0 or int_minute > 59:
        hour = "0"
        minute = "5"
except ValueError:
    hour = "0"
    minute = "5"


@sv_dna_sign.on_fullmatch(
    (
        "签到",
        "社区签到",
        "每日任务",
        "社区任务",
        "库街区签到",
        "sign",
    ),
    block=True,
)
async def dna_user_sign(bot: Bot, ev: Event):
    await manual_sign(bot, ev)


@sv_dna_sign_calendar.on_fullmatch(
    (
        "签到日历",
        "签到记录",
        "签到历史",
        "签到记录",
    ),
    block=True,
)
async def sign_calendar(bot: Bot, ev: Event):
    await draw_sign_calendar(bot, ev)


@scheduler.scheduled_job("cron", hour=hour, minute=minute)
async def dna_auto_sign():
    msg = await auto_sign()
    subscribes = await gs_subscribe.get_subscribe(BoardcastTypeEnum.SIGN_RESULT)
    if subscribes:
        logger.info(f"[DNAUID]推送主人签到结果: {msg}")
        for sub in subscribes:
            await sub.send(msg)


@sv_dna_sign_all.on_fullmatch(("全部签到"))
async def dna_sign_recheck_all(bot: Bot, ev: Event):
    await bot.send("[DNAUID] [全部签到] 已开始执行!")
    msg = await auto_sign()
    await bot.send("[DNAUID] [全部签到] 执行完成!")
    await bot.send(msg)


@sv_dna_sign_all.on_regex(("^(订阅|取消订阅)签到结果$"))
async def dna_sign_result(bot: Bot, ev: Event):
    if ev.bot_id != "onebot":
        logger.debug(f"非onebot禁止订阅签到结果 【{ev.bot_id}】")
        return

    if "取消" in ev.raw_text:
        option = "关闭"
    else:
        option = "开启"

    if option == "关闭":
        await gs_subscribe.delete_subscribe("single", BoardcastTypeEnum.SIGN_RESULT, ev)
    else:
        await gs_subscribe.add_subscribe("single", BoardcastTypeEnum.SIGN_RESULT, ev)

    await bot.send(f"[DNAUID] [订阅签到结果] 已{option}订阅!")


@scheduler.scheduled_job("cron", hour=0, minute=5)
async def clear_dna_sign_record():
    """清除2天前的签到记录"""
    await DNASign.clear_sign_record(get_two_days_ago_date())
    logger.info("[DNAUID] [清除签到记录] 已清除2天前的签到记录!")
