import asyncio

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from . import dob_pack, dob_loader
from ..dna_config.dna_config import DNAConfig

sv_dob = SV("dna数据包")


@sv_dob.on_fullmatch(("更新数据包", "更新DOB数据包", "dna更新数据包"), block=True)
async def update_dob_pack(bot: Bot, ev: Event) -> None:
    await bot.send("开始拉取 DOB 数据包（dna-builder 数据源），请稍候…")
    try:
        changed, message = await dob_pack.sync_async()
    except dob_pack.DobPackError as error:
        await bot.send(f"数据包更新失败：{error!r}")
        return
    if changed:
        await asyncio.to_thread(dob_loader.reload)
    await bot.send(message)


@sv_dob.on_fullmatch(("数据包状态", "DOB数据状态", "数据源状态"))
async def dob_pack_status(bot: Bot, ev: Event) -> None:
    if not dob_loader.is_loaded():
        await bot.send("DOB 数据未加载（data/DNAUID/resource/dob/dob_data.json 缺失），\n请先发送「dna更新数据包」")
        return
    meta = dob_pack.read_local_meta()
    built_at = (meta.get("packBuiltAt") if meta else None) or "未知"
    await bot.send(
        f"DOB 数据包：v{dob_loader.version()}\n"
        f"打包时间：{built_at[:19].replace('T', ' ')}\n"
        f"角色 {dob_loader.char_count()} / 魔之楔 {dob_loader.mod_count()} / 武器 {dob_loader.weapon_count()}"
    )


@sv_dob.on_fullmatch(("重载数据包", "重载DOB数据"))
async def reload_dob_pack(bot: Bot, ev: Event) -> None:
    await asyncio.to_thread(dob_loader.reload)
    if not dob_loader.is_loaded():
        await bot.send("重载失败：dob_data.json 缺失或损坏，请发送「dna更新数据包」")
        return
    await bot.send(f"DOB 数据已重载：v{dob_loader.version()}（魔之楔 {dob_loader.mod_count()} 条）")


# 定时检查数据包更新（间隔可配置；手动与自动更新共用 dob_pack 内部锁串行执行）
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
        changed, message = await dob_pack.sync_async()
        if changed:
            logger.info(f"[DNA DOB] {message}（定时检查）")
    except dob_pack.DobPackError as error:
        logger.warning(f"[DNA DOB] 定时检查失败（不影响使用）: {error!r}")
