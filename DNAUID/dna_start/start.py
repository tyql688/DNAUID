from gsuid_core.logger import logger
from gsuid_core.server import on_core_start

from ..dna_resource import startup


@on_core_start
async def all_start() -> None:
    logger.info("[二重螺旋] 启动中...")
    await startup()

    # DOB 数据包：首次没有数据时同步等待初始化；已有数据时后台检查更新（失败不影响启动）。
    from ..dna_sdk import SdkPackError, is_data_ready, init_if_needed, startup_auto_sync
    from ..dna_config.dna_config import DNAConfig

    if DNAConfig.get_config("DobAutoUpdate").data:
        try:
            if is_data_ready():
                startup_auto_sync()
            else:
                await init_if_needed()
        except SdkPackError as error:
            logger.warning(f"[二重螺旋] DOB 数据包初始化失败: {error!r}")

    logger.success("[二重螺旋] 启动完成✅")
