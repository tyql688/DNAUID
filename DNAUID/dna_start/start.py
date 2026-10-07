from gsuid_core.logger import logger
from gsuid_core.server import on_core_start

from ..dna_resource import startup


@on_core_start
async def all_start():
    logger.info("[二重螺旋] 启动中...")
    try:
        await startup()
    except Exception as e:
        logger.exception(e)

    # DOB 数据包自更新：检查 dna-builder 数据包新版本，有则后台下载转换（失败不影响启动）
    try:
        from ..dna_mod import dob_pack
        from ..dna_config.dna_config import DNAConfig

        if DNAConfig.get_config("DobAutoUpdate").data:
            dob_pack.startup_auto_sync()
    except Exception as e:
        logger.warning(f"[二重螺旋] DOB 数据包自更新任务挂载失败: {e!r}")

    logger.success("[二重螺旋] 启动完成✅")
