from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO

from PIL import Image

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.image.image_tools import change_ev_image_to_bytes

from ..utils.image import save_webp_img
from ..utils.msgs.notify import dna_not_found, send_dna_notify
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..utils.resource.RESOURCE_PATH import CUSTOM_PAINT_PATH


async def upload_role_panel_img(bot: Bot, ev: Event, char_name: str) -> None:
    if not ev.image_list:
        _ = await send_dna_notify(bot, ev, "请随命令发送一张面板图")
        return

    real_char_name = alias_to_char_name(char_name)
    if real_char_name is None:
        _ = await dna_not_found(bot, ev, f"角色别名【{char_name}】")
        return

    char_id = char_name_to_char_id(real_char_name)
    if char_id is None:
        _ = await dna_not_found(bot, ev, f"角色【{char_name}】的CharId")
        return

    saved_count = 0
    failed_count = 0
    for image_source in ev.image_list:
        try:
            image_bytes = await change_ev_image_to_bytes(image_source)
            await asyncio.to_thread(_save_role_panel_img, char_id, image_bytes)
            saved_count += 1
        except (OSError, ValueError):
            failed_count += 1

    if saved_count == 0:
        _ = await send_dna_notify(bot, ev, "面板图保存失败")
        return

    msg = f"已上传{real_char_name}面板图{saved_count}张"
    if failed_count:
        msg += f"，失败{failed_count}张"
    _ = await send_dna_notify(bot, ev, msg)


def _save_role_panel_img(char_id: str, image_bytes: bytes) -> None:
    panel_dir = CUSTOM_PAINT_PATH / char_id
    panel_dir.mkdir(parents=True, exist_ok=True)
    panel_path = panel_dir / f"{hashlib.sha1(image_bytes).hexdigest()[:16]}.webp"

    with Image.open(BytesIO(image_bytes)) as image:
        save_webp_img(image, panel_path)
