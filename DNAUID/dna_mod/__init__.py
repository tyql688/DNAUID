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
        # sync_async 内部已负责重载查询层，这里不再重复 reload
        _, message = await dob_pack.sync_async()
    except dob_pack.DobPackError as error:
        await bot.send(f"数据包更新失败：{error!r}")
        return
    await bot.send(message)


async def ensure_data_ready() -> str | None:
    """确保 DOB 数据可用（面板等入口在计算前调用）

    ``on_core_start`` 是后台钩子，里面的等待挡不住命令 —— 面板入口必须自己复用
    同一初始化入口（``dob_pack.sync_async`` 内部持锁串行，重复调用不会并发下载）。
    返回 None 表示可用，否则返回给用户看的失败提示。
    """
    if dob_loader.is_loaded():
        return None
    # 先试本地读盘：旧目录迁移、或进程启动早于落盘时，读一次就好，不必联网
    await asyncio.to_thread(dob_loader.reload)
    if dob_loader.is_loaded():
        return None
    if not DNAConfig.get_config("DobAutoUpdate").data:
        return "DOB 数据包未就绪，请先发送「dna更新数据包」"
    try:
        await dob_pack.sync_async()
    except dob_pack.DobPackError as error:
        return f"DOB 数据包初始化失败：{error!r}"
    if not dob_loader.is_loaded():
        return "DOB 数据包初始化失败：dob_data.json 缺失或内容不完整"
    return None


@sv_dob.on_fullmatch(("数据包状态", "DOB数据状态", "数据源状态"))
async def dob_pack_status(bot: Bot, ev: Event) -> None:
    if not dob_loader.is_loaded():
        await bot.send("DOB 数据未加载（data/DNAUID/resource/dob/dob_data.json 缺失），\n请先发送「dna更新数据包」")
        return
    built_at = dob_loader.built_at() or "未知"
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
