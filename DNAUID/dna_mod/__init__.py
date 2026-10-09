import asyncio

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..dna_sdk import SdkPackError, counts, tables as _sdk_tables, version, sync_async, is_data_ready, reload_tables
from ..dna_config.dna_config import DNAConfig

sv_dob = SV("dna数据包")


@sv_dob.on_fullmatch(("更新数据包", "更新DOB数据包", "dna更新数据包"), block=True)
async def update_dob_pack(bot: Bot, ev: Event) -> None:
    await bot.send("开始拉取 DOB 数据包（dna-builder 数据源），请稍候…")
    try:
        # sync_async 内部已负责重载表，这里不再重复 reload
        _, message = await sync_async()
    except SdkPackError as error:
        await bot.send(f"数据包更新失败：{error}")
        return
    await bot.send(message)


@sv_dob.on_fullmatch(("数据包状态", "DOB数据状态", "数据源状态"))
async def dob_pack_status(bot: Bot, ev: Event) -> None:
    if not is_data_ready():
        await bot.send("DOB 数据未加载（data/DNAUID/resource/dob/ 下无数据包），\n请先发送「dna更新数据包」")
        return
    try:
        built = await asyncio.to_thread(_sdk_tables.built_at)
        stat = counts()
    except SdkPackError as error:
        await bot.send(f"DOB 数据状态读取失败：{error}")
        return
    await bot.send(
        f"DOB 数据包：v{version()}\n"
        f"打包时间：{(built or '未知')[:19].replace('T', ' ')}\n"
        f"角色 {stat['chars']} / 魔之楔 {stat['mods']} / 武器 {stat['weapons']}"
    )


@sv_dob.on_fullmatch(("重载数据包", "重载DOB数据"))
async def reload_dob_pack(bot: Bot, ev: Event) -> None:
    try:
        await asyncio.to_thread(reload_tables)
    except SdkPackError as error:
        await bot.send(f"重载失败：{error}，请发送「dna更新数据包」")
        return
    if not is_data_ready():
        await bot.send("重载失败：数据包缺失或损坏，请发送「dna更新数据包」")
        return
    stat = counts()
    await bot.send(f"DOB 数据已重载：v{version()}（魔之楔 {stat['mods']} 条）")


# 定时检查数据包更新（间隔可配置；手动与自动更新共用 sync 内部锁串行执行）
@scheduler.scheduled_job(
    "interval",
    minutes=max(10, int(DNAConfig.get_config("DobUpdateInterval").data or 60)),
    id="dna_dob_auto_update",
    replace_existing=True,
)
async def _dob_auto_update() -> None:
    # 开关关闭时不自动更新（与启动检查保持一致）
    if not DNAConfig.get_config("DobAutoUpdate").data:
        return
    try:
        changed, message = await sync_async()
        if changed:
            logger.info(f"[DNA DOB] {message}（定时检查）")
    except SdkPackError as error:
        logger.warning(f"[DNA DOB] 定时检查失败（不影响使用）: {error!r}")
