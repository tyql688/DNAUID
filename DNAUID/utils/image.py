import os
import random
from pathlib import Path
from typing import Optional, Tuple, Union

from PIL import Image, ImageOps

from gsuid_core.logger import logger
from gsuid_core.utils.download_resource.download_file import download
from gsuid_core.utils.image.image_tools import crop_center_img

from .resource.RESOURCE_PATH import (
    AVATAR_PATH,
    CUSTOM_PAINT_PATH,
    PAINT_PATH,
    SKILL_PATH,
    WEAPON_PATH,
)

ICON = Path(__file__).parent.parent.parent / "ICON.png"
TEXT_PATH = Path(__file__).parent / "texture2d"


# Gold & Earth Tones
COLOR_LIGHT_GOLDENROD = (250, 250, 210)  # 浅金黄色
COLOR_PALE_GOLDENROD = (238, 232, 170)  # 淡金黄色的
COLOR_KHAKI = (240, 230, 140)  # 黄褐色
COLOR_GOLDENROD = (218, 165, 32)  # 金毛
COLOR_GOLD = (255, 215, 0)  # 金
COLOR_ORANGE = (255, 165, 0)  # 橙子
COLOR_DARK_ORANGE = (255, 140, 0)  # 深橙色
COLOR_PERU = (205, 133, 63)  # 秘鲁
COLOR_CHOCOLATE = (210, 105, 30)  # 巧克力
COLOR_SADDLE_BROWN = (139, 69, 19)  # 马鞍棕色
COLOR_SIENNA = (160, 82, 45)  # 赭色

# Basic Colors
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (128, 128, 128)
COLOR_LIGHT_GRAY = (230, 230, 230)
COLOR_RED = (255, 0, 0)
COLOR_GREEN = (76, 175, 80)
COLOR_BLUE = (30, 40, 60)
COLOR_PURPLE = (138, 43, 226)


def get_dna_bg(w: int, h: int, bg: str = "bg") -> Image.Image:
    img = Image.open(TEXT_PATH / f"{bg}.jpg").convert("RGBA")
    return crop_center_img(img, w, h)


async def download_pic_from_url(
    path: Path,
    pic_url: str,
    size: Optional[Tuple[int, int]] = None,
    name: Optional[str] = None,
) -> Image.Image:
    path.mkdir(parents=True, exist_ok=True)

    if name is None:
        name = pic_url.split("/")[-1]
    _path = path / name
    if not _path.exists():
        await download(pic_url, path, name, tag="[DNA]")

    img = Image.open(_path)
    if size:
        img = img.resize(size)

    return img.convert("RGBA")


async def get_skill_img(
    char_id: Union[str, int], skill_name: str, pic_url: Optional[str] = None
) -> Image.Image:
    char_skill_dir = SKILL_PATH / str(char_id)
    char_skill_dir.mkdir(parents=True, exist_ok=True)

    skill_name = skill_name.strip()
    name = f"skill_{skill_name}.png"
    skill_path = char_skill_dir / name
    if not skill_path.exists():
        if pic_url:
            await download(pic_url, char_skill_dir, name, tag="[DNA]")

    return Image.open(skill_path).convert("RGBA")


async def get_avatar_img(
    char_id: Union[str, int], pic_url: Optional[str] = None
) -> Image.Image:
    char_avatar_dir = AVATAR_PATH
    char_avatar_dir.mkdir(parents=True, exist_ok=True)

    name = f"avatar_{char_id}.png"
    avatar_path = char_avatar_dir / name
    if not avatar_path.exists():
        if pic_url:
            await download(pic_url, char_avatar_dir, name, tag="[DNA]")

    return Image.open(avatar_path).convert("RGBA")


async def get_weapon_img(
    weapon_id: Union[str, int], pic_url: Optional[str] = None
) -> Image.Image:
    weapon_dir = WEAPON_PATH
    weapon_dir.mkdir(parents=True, exist_ok=True)

    name = f"weapon_{weapon_id}.png"
    weapon_path = weapon_dir / name
    if not weapon_path.exists():
        if pic_url:
            await download(pic_url, weapon_dir, name, tag="[DNA]")

    return Image.open(weapon_path).convert("RGBA")


async def get_paint_img(
    char_id: Union[str, int], pic_url: Optional[str] = None
) -> Image.Image:
    paint_dir = PAINT_PATH
    paint_dir.mkdir(parents=True, exist_ok=True)

    name = f"paint_{char_id}.png"
    paint_path = paint_dir / name
    if not paint_path.exists():
        if pic_url:
            await download(pic_url, paint_dir, name, tag="[DNA]")

    return Image.open(paint_path).convert("RGBA")


async def get_custom_paint_img(
    char_id: Union[str, int], pic_url: Optional[str] = None, custom: bool = False
) -> tuple[bool, Image.Image]:
    """
    获取char_id自定义立绘图片

    Args:
        char_id: 角色ID
        pic_url: 图片URL
        custom: 是否使用自定义立绘

    Returns:
        tuple[bool, Image.Image]: 是否使用自定义立绘, 立绘图片
    """
    if custom:
        custom_dir = CUSTOM_PAINT_PATH / str(char_id)
        if custom_dir.exists() and len(os.listdir(custom_dir)) > 0:
            path = random.choice(os.listdir(custom_dir))
            if path:
                return True, Image.open(f"{custom_dir}/{path}").convert("RGBA")

    return False, await get_paint_img(char_id, pic_url)


def add_footer(
    img: Image.Image,
    w: int = 0,
    offset_y: int = 0,
    is_invert: bool = False,
):
    footer = Image.open(TEXT_PATH / "footer.png")
    if is_invert:
        r, g, b, a = footer.split()
        rgb_image = Image.merge("RGB", (r, g, b))
        rgb_image = ImageOps.invert(rgb_image.convert("RGB"))
        r2, g2, b2 = rgb_image.split()
        footer = Image.merge("RGBA", (r2, g2, b2, a))

    if w != 0:
        footer = footer.resize(
            (w, int(footer.size[1] * w / footer.size[0])),
        )

    x, y = (
        int((img.size[0] - footer.size[0]) / 2),
        img.size[1] - footer.size[1] - 20 + offset_y,
    )

    img.paste(footer, (x, y), footer)
    return img


def compress_to_webp(
    image_path: Path, quality: int = 80, delete_original: bool = True
) -> tuple[bool, Path]:
    try:
        from PIL import Image

        if not image_path.exists():
            logger.warning(f"图片不存在: {image_path}")
            return False, image_path

        if image_path.suffix.lower() == ".webp":
            logger.info(f"图片已经是webp格式: {image_path}")
            return False, image_path

        webp_path = image_path.with_suffix(".webp")
        img = Image.open(image_path)
        orig_size = image_path.stat().st_size

        img.save(
            webp_path,
            "WEBP",
            quality=quality,
            method=6,
            optimize=True,
        )
        webp_size = webp_path.stat().st_size

        if webp_size >= orig_size:
            webp_path.unlink(missing_ok=True)
            logger.info(f"图片 {image_path.name} WebP 压缩后文件更大，保留原文件")
            return False, image_path

        compression_ratio = (1 - webp_size / orig_size) * 100 if orig_size > 0 else 0
        logger.info(
            f"图片 {image_path.name} 压缩为webp格式 (质量: {quality}), "
            f"压缩率: {compression_ratio:.2f}%, "
            f"大小: {orig_size / 1024:.1f}KB -> {webp_size / 1024:.1f}KB"
        )

        if delete_original:
            image_path.unlink()
            logger.info(f"原图片已删除: {image_path}")

        return True, webp_path

    except Exception as e:
        logger.error(f"压缩图片为webp格式失败: {e}")
        return False, image_path
