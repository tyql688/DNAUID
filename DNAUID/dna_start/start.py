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

    logger.success("[二重螺旋] 启动完成✅")
