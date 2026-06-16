from __future__ import annotations

import shutil
import asyncio
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.image.image_tools import change_ev_image_to_bytes

from ..utils.image import save_webp_img, compress_to_webp
from ..utils.msgs.notify import dna_not_found, send_dna_notify
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..utils.original_image import (
    delete_original_image,
    drop_original_image_cache,
)
from ..utils.master_char_const import get_master_char_panel_dir
from ..utils.resource.RESOURCE_PATH import CUSTOM_PAINT_PATH

_IMAGE_SUFFIXES = frozenset(Image.registered_extensions())


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
            await asyncio.to_thread(save_role_panel_img, char_id, image_bytes)
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


async def delete_original_role_panel_img(bot: Bot, ev: Event) -> None:
    if ev.reply is None:
        _ = await send_dna_notify(bot, ev, "请引用角色面板图")
        return

    image_path = await asyncio.to_thread(delete_original_image, ev.reply)
    if image_path is None:
        _ = await send_dna_notify(bot, ev, "未找到对应原图")
        return

    _ = await send_dna_notify(bot, ev, f"已删除原图：{image_path.name}")


async def delete_role_panel_img_by_id(bot: Bot, ev: Event, char_name: str, image_id: str) -> None:
    real_char_name = alias_to_char_name(char_name)
    if real_char_name is None:
        _ = await dna_not_found(bot, ev, f"角色别名【{char_name}】")
        return

    char_id = char_name_to_char_id(real_char_name)
    if char_id is None:
        _ = await dna_not_found(bot, ev, f"角色【{char_name}】的CharId")
        return

    image_path = await asyncio.to_thread(delete_role_panel_img, char_id, image_id)
    if image_path is None:
        _ = await send_dna_notify(bot, ev, f"未找到{real_char_name}面板图：{image_id}")
        return

    _ = await send_dna_notify(bot, ev, f"已删除{real_char_name}面板图：{image_path.stem}")


async def delete_all_role_panel_imgs(bot: Bot, ev: Event, char_name: str) -> None:
    real_char_name = alias_to_char_name(char_name)
    if real_char_name is None:
        _ = await dna_not_found(bot, ev, f"角色别名【{char_name}】")
        return

    char_id = char_name_to_char_id(real_char_name)
    if char_id is None:
        _ = await dna_not_found(bot, ev, f"角色【{char_name}】的CharId")
        return

    deleted_count = await asyncio.to_thread(delete_role_panel_dir, char_id)
    if deleted_count is None:
        _ = await send_dna_notify(bot, ev, f"暂无{real_char_name}面板图")
        return

    _ = await send_dna_notify(bot, ev, f"已删除{real_char_name}全部面板图：{deleted_count}张")


async def list_role_panel_imgs(bot: Bot, ev: Event, char_name: str) -> None:
    real_char_name = alias_to_char_name(char_name)
    if real_char_name is None:
        _ = await dna_not_found(bot, ev, f"角色别名【{char_name}】")
        return

    char_id = char_name_to_char_id(real_char_name)
    if char_id is None:
        _ = await dna_not_found(bot, ev, f"角色【{char_name}】的CharId")
        return

    panel_paths = await asyncio.to_thread(get_role_panel_paths, char_id)
    if not panel_paths:
        _ = await send_dna_notify(bot, ev, f"暂无{real_char_name}面板图")
        return

    messages = [MessageSegment.text(f"{real_char_name}面板图列表：共{len(panel_paths)}张\n")]
    for image_path in panel_paths:
        messages.append(MessageSegment.text(f"\nID：{image_path.stem}\n"))
        messages.append(MessageSegment.image(image_path))
    await bot.send(messages)


async def compress_role_panel_imgs(bot: Bot, ev: Event) -> None:
    panel_paths = await asyncio.to_thread(get_all_role_panel_paths)
    if not panel_paths:
        _ = await send_dna_notify(bot, ev, "暂无角色面板图")
        return

    results = await asyncio.gather(*(asyncio.to_thread(compress_role_panel_img, path) for path in panel_paths))
    compressed_count = sum(1 for is_compressed, _ in results if is_compressed)
    _ = await send_dna_notify(
        bot,
        ev,
        f"面板图压缩完成：共{len(panel_paths)}张，压缩{compressed_count}张，跳过{len(panel_paths) - compressed_count}张",
    )


def save_role_panel_img(char_id: str, image_bytes: bytes) -> None:
    panel_dir = CUSTOM_PAINT_PATH / get_master_char_panel_dir(char_id)
    panel_dir.mkdir(parents=True, exist_ok=True)
    panel_path = panel_dir / f"{hashlib.sha1(image_bytes).hexdigest()[:16]}.webp"

    with Image.open(BytesIO(image_bytes)) as image:
        save_webp_img(image, panel_path)


def get_role_panel_paths(char_id: str | int) -> list[Path]:
    panel_dir = CUSTOM_PAINT_PATH / get_master_char_panel_dir(char_id)
    if not panel_dir.is_dir():
        return []

    return sorted(path for path in panel_dir.iterdir() if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES)


def get_all_role_panel_paths() -> list[Path]:
    if not CUSTOM_PAINT_PATH.is_dir():
        return []

    panel_paths = []
    for panel_dir in sorted(CUSTOM_PAINT_PATH.iterdir()):
        if panel_dir.is_dir():
            panel_paths.extend(get_role_panel_paths(panel_dir.name))
    return panel_paths


def compress_role_panel_img(image_path: Path) -> tuple[bool, Path]:
    is_compressed, result_path = compress_to_webp(image_path)
    if is_compressed:
        drop_original_image_cache(image_path)
    return is_compressed, result_path


def delete_role_panel_img(char_id: str | int, image_id: str) -> Path | None:
    for image_path in get_role_panel_paths(char_id):
        if image_path.stem != image_id and image_path.name != image_id:
            continue

        drop_original_image_cache(image_path)
        image_path.unlink()
        panel_dir = image_path.parent
        if not any(panel_dir.iterdir()):
            panel_dir.rmdir()
        return image_path

    return None


def delete_role_panel_dir(char_id: str | int) -> int | None:
    panel_dir = CUSTOM_PAINT_PATH / get_master_char_panel_dir(char_id)
    if not panel_dir.is_dir():
        return None

    panel_paths = get_role_panel_paths(char_id)
    for image_path in panel_paths:
        drop_original_image_cache(image_path)
    shutil.rmtree(panel_dir)
    return len(panel_paths)
