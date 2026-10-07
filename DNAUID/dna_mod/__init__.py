import asyncio

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from . import dob_pack, dob_loader

sv_dob = SV("dna数据包")


@sv_dob.on_fullmatch(("更新数据包", "更新DOB数据包", "dna更新数据包"), block=True)
async def update_dob_pack(bot: Bot, ev: Event):
    await bot.send("开始拉取 DOB 数据包（dna-builder 数据源），请稍候…")
    try:
        changed, message = await dob_pack.sync_async()
    except Exception as error:  # noqa: BLE001
        return await bot.send(f"数据包更新失败：{error!r}")
    if changed:
        await asyncio.to_thread(dob_loader.reload)
    await bot.send(message)


@sv_dob.on_fullmatch(("数据包状态", "DOB数据状态", "数据源状态"))
async def dob_pack_status(bot: Bot, ev: Event):
    if not dob_loader.is_loaded():
        return await bot.send("DOB 数据未加载（dna_mod/data/dob_data.json 缺失），\n请先发送「dna更新数据包」")
    meta = dob_pack.read_local_meta() or {}
    await bot.send(
        f"DOB 数据包：v{dob_loader.version()}\n"
        f"打包时间：{(meta.get('packBuiltAt') or '未知')[:19].replace('T', ' ')}\n"
        f"角色 {dob_loader.char_count()} / 魔之楔 {dob_loader.mod_count()} / 武器 {dob_loader.weapon_count()}"
    )


@sv_dob.on_fullmatch(("重载数据包", "重载DOB数据"))
async def reload_dob_pack(bot: Bot, ev: Event):
    await asyncio.to_thread(dob_loader.reload)
    if not dob_loader.is_loaded():
        return await bot.send("重载失败：dob_data.json 缺失或损坏，请发送「dna更新数据包」")
    await bot.send(f"DOB 数据已重载：v{dob_loader.version()}（魔之楔 {dob_loader.mod_count()} 条）")
