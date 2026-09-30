import re
import asyncio
from pathlib import Path

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.msgs.notify import dna_not_found
from ..utils.name_convert import alias_to_char_name
from ..dna_config.dna_config import DNAConfig

GUIDE_PATH = Path(__file__).parent / "texture2d"


async def get_guide(bot: Bot, ev: Event, char_name: str) -> None:
    real_char_name = alias_to_char_name(char_name)
    if not real_char_name:
        await dna_not_found(bot, ev, f"角色别名【{char_name}】")
        return

    char_name = real_char_name

    logger.debug(f"[二重螺旋] 开始获取{char_name}攻略")

    config: list[str] = DNAConfig.get_config("Guide").data
    guide_name = "暗主" if char_name in {"男主-暗", "女主-暗"} else char_name
    pattern = re.compile(re.escape(guide_name), re.IGNORECASE)
    if "all" in config:
        guide_paths = await asyncio.to_thread(lambda: list(GUIDE_PATH.iterdir()))
    else:
        guide_paths = [GUIDE_PATH / name for name in config]

    imgs_result: list[str] = []
    for guide_path in guide_paths:
        imgs_result.extend(await get_guide_pic(guide_path, pattern, guide_path.name))

    if len(imgs_result) == 0:
        await dna_not_found(bot, ev, f"角色【{char_name}】攻略")
        return

    await send_guide(config, imgs_result, bot)


def _match_guide_files(guide_path: Path, pattern: re.Pattern[str]) -> list[Path] | None:
    if not guide_path.is_dir():
        return None
    return [file for file in guide_path.iterdir() if pattern.search(file.name)]


async def get_guide_pic(guide_path: Path, pattern: re.Pattern[str], guide_author: str) -> list[str]:
    files = await asyncio.to_thread(_match_guide_files, guide_path, pattern)
    if files is None:
        logger.warning(f"[二重螺旋] 攻略路径错误 {guide_path}")
        return []

    imgs: list[str] = []
    for file in files:
        try:
            imgs.append(await convert_img(file))
        except Exception as e:
            logger.warning(f"[二重螺旋] 攻略图片读取失败 {file}: {e!r}")

    if imgs:
        imgs.insert(0, f"攻略作者：{guide_author}")
    return imgs


async def send_guide(config: list[str], imgs: list[str], bot: Bot) -> None:
    if "all" in config:
        await bot.send(imgs)
    elif len(imgs) == 2:
        await bot.send(imgs[1])
    else:
        await bot.send(imgs)
