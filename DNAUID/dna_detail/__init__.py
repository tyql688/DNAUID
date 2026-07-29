from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .draw_role_card import draw_role_card
from ..utils.original_image import get_original_image_path
from ..dna_config.dna_config import DNAConfig
from ..utils.constants.constants import PATTERN

dna_role_detail_card = SV("dna角色详情卡片")
dna_original_image = SV("dna角色原图")

ROLE_DETAIL_PATTERN = (
    rf"^(?P<char_name>{PATTERN})(?:面板|信息|详情|面包|🍞)"
    rf"(?:\s*[+＋]\s*(?P<weapon_name_1>{PATTERN}))?"
    rf"(?:\s*[+＋]\s*(?P<weapon_name_2>{PATTERN}))?$"
)


@dna_role_detail_card.on_regex(
    ROLE_DETAIL_PATTERN,
    block=True,
)
async def send_role_detail_card(bot: Bot, ev: Event):
    char_name = ev.regex_dict["char_name"]
    weapon_names = tuple(
        name
        for name in (
            ev.regex_dict.get("weapon_name_1"),
            ev.regex_dict.get("weapon_name_2"),
        )
        if name is not None
    )
    logger.info(
        f"[DNA Detail] 触发命令: raw_text={ev.raw_text}, char_name={char_name}, weapon_names={weapon_names}, at={ev.at}"
    )
    await draw_role_card(
        bot,
        ev,
        char_name,
        weapon_names=weapon_names,
    )


@dna_original_image.on_fullmatch("原图", block=True)
async def send_role_original_image(bot: Bot, ev: Event):
    if not DNAConfig.get_config("RoleOriginalImage").data:
        logger.info("[DNA Detail] 角色原图功能已关闭")
        return

    if ev.reply is None:
        logger.warning(f"[DNA Detail] 未引用角色面板图: ev.reply={ev.reply}")
        return

    image_path = get_original_image_path(ev.reply)
    if image_path is None:
        logger.warning(f"[DNA Detail] 未找到对应原图: ev.reply={ev.reply}")
        return

    await bot.send(MessageSegment.image(image_path))
