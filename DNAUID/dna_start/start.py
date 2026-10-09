import asyncio

from gsuid_core.logger import logger
from gsuid_core.server import on_core_start

from ..dna_resource import startup
from ..utils.dob.pack import load_local, check_update

_background: set[asyncio.Task[None]] = set()


@on_core_start
async def all_start() -> None:
    logger.info("[二重螺旋] 启动中...")
    await startup()

    await load_local()
    # 更新检查放后台：下载可能很慢，别拖住其他插件的启动钩子
    task = asyncio.create_task(check_update("启动检查"))
    _background.add(task)
    task.add_done_callback(_background.discard)

    logger.success("[二重螺旋] 启动完成✅")
