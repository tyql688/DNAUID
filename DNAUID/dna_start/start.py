from gsuid_core.logger import logger
from gsuid_core.server import on_core_start

from ..dna_resource import startup


@on_core_start
async def all_start() -> None:
    logger.info("[二重螺旋] 启动中...")
    await startup()

    # DOB 数据包：首次没有数据时同步等待初始化；已有数据时后台检查更新（失败不影响启动）。
    # 两条路径内部都由 dob_pack.sync_async 重载查询层，这里不再重复 reload。
    from ..dna_mod import dob_pack
    from ..dna_config.dna_config import DNAConfig

    if DNAConfig.get_config("DobAutoUpdate").data:
        try:
            if dob_pack.is_data_ready():
                dob_pack.startup_auto_sync()
            else:
                await dob_pack.init_if_needed()
        except dob_pack.DobPackError as error:
            logger.warning(f"[二重螺旋] DOB 数据包初始化失败: {error!r}")

    logger.success("[二重螺旋] 启动完成✅")
