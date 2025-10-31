import asyncio

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import SV

from ..utils.resource.download_all_resource import download_all_resource

sv_download_config = SV("资源下载", pm=1)


@sv_download_config.on_fullmatch(("下载全部资源"))
async def send_download_resource_msg(bot: Bot, ev: Event):
    await bot.send("[二重螺旋] 正在开始下载~可能需要较久的时间!")
    await download_all_resource()
    await bot.send("[二重螺旋] 下载完成！")


async def startup():
    logger.info("[二重螺旋] 资源下载任务已在后台启动")
    asyncio.create_task(download_all_resource())
