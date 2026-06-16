from __future__ import annotations

from pathlib import Path

from cachetools import LRUCache

from .resource.RESOURCE_PATH import CUSTOM_PAINT_PATH

_ORIGINAL_IMAGE_CACHE: LRUCache[str, Path] = LRUCache(maxsize=256)


def cache_original_image(message_ids: list[str] | None, image_path: Path | None) -> None:
    if message_ids is None or image_path is None:
        return

    for message_id in message_ids:
        _ORIGINAL_IMAGE_CACHE[message_id] = image_path


def get_original_image_path(message_id: str | None) -> Path | None:
    if message_id is None:
        return None

    image_path = _ORIGINAL_IMAGE_CACHE.get(message_id)
    if image_path is not None and image_path.exists():
        return image_path

    return None


def delete_original_image(message_id: str | None) -> Path | None:
    if message_id is None:
        return None

    image_path = _ORIGINAL_IMAGE_CACHE.pop(message_id, None)
    if image_path is None:
        return None

    drop_original_image_cache(image_path)

    if not image_path.exists():
        return None

    image_path.unlink()
    panel_dir = image_path.parent
    if panel_dir.parent == CUSTOM_PAINT_PATH and not any(panel_dir.iterdir()):
        panel_dir.rmdir()
    return image_path


def drop_original_image_cache(image_path: Path) -> None:
    for message_id, cached_path in list(_ORIGINAL_IMAGE_CACHE.items()):
        if cached_path == image_path:
            _ORIGINAL_IMAGE_CACHE.pop(message_id, None)
