from gsuid_core.logger import logger
from gsuid_core.server import on_core_start

import asyncio

from ..dna_resource import startup


@on_core_start
async def all_start():
    logger.info("[二重螺旋] 启动中...")
    try:
        await startup()
    except Exception as e:
        logger.exception(e)

    # DOB 数据包：首次没有数据时同步等待初始化；已有数据时后台检查更新（失败不影响启动）
    try:
        from ..dna_config.dna_config import DNAConfig
        from ..dna_mod import dob_loader, dob_pack

        if DNAConfig.get_config("DobAutoUpdate").data:
            if dob_pack.is_data_ready():
                dob_pack.startup_auto_sync()
            else:
                await dob_pack.init_if_needed()
                await asyncio.to_thread(dob_loader.reload)
    except Exception as e:
        logger.warning(f"[二重螺旋] DOB 数据包初始化失败: {e!r}")

    logger.success("[二重螺旋] 启动完成✅")
