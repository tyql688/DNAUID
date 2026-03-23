import os
import random
from typing import Tuple, Union, Optional
from pathlib import Path

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.image_tools import (
    crop_center_img,
    get_event_avatar,
)
from gsuid_core.utils.download_resource.download_file import download

from .resource.RESOURCE_PATH import (
    MOD_PATH,
    ATTR_PATH,
    PAINT_PATH,
    SKILL_PATH,
    AVATAR_PATH,
    WEAPON_PATH,
    WEAPON_ATTR_PATH,
    CUSTOM_PAINT_PATH,
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

# Red & Pink Tones
COLOR_LIGHT_SALMON = (255, 160, 122)  # 浅鲑红 / Lightsalmon #FFA07A
COLOR_SALMON = (250, 128, 114)  # 三文鱼 / Salmon #FA8072
COLOR_DARK_SALMON = (233, 150, 122)  # 黑鲑 / Dark Salmon #E9967A
COLOR_LIGHT_CORAL = (240, 128, 128)  # 轻珊瑚 / Light Coral #F08080
COLOR_INDIAN_RED = (205, 92, 92)  # 印度红 / Indian Red #CD5C5C
COLOR_CRIMSON = (220, 20, 60)  # 赤红 / Crimson #DC143C
COLOR_FIRE_BRICK = (178, 34, 34)  # 耐火砖 / Fire Brick #B22222
COLOR_RED = (255, 0, 0)  # 红色 / Red #FF0000
COLOR_DARK_RED = (139, 0, 0)  # 深红 / Dark Red #8B0000
COLOR_MAROON = (128, 0, 0)  # 栗色 / Maroon #800000
COLOR_TOMATO = (255, 99, 71)  # 番茄 / Tomato #FF6347
COLOR_ORANGE_RED = (255, 69, 0)  # 橙红 / Orange Red #FF4500
COLOR_PALE_VIOLET_RED = (219, 112, 147)  # 泛紫红 / Pale Violet Red #DB7093

# Basic Colors
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (128, 128, 128)
COLOR_LIGHT_GRAY = (230, 230, 230)
COLOR_RED = (255, 0, 0)
COLOR_GREEN = (76, 175, 80)
COLOR_BLUE = (30, 40, 60)
COLOR_PURPLE = (138, 43, 226)


Color = Union[str, Tuple[int, int, int], Tuple[int, int, int, int]]

GRADE_0 = Image.open(TEXT_PATH / "number/0.png")
GRADE_1 = Image.open(TEXT_PATH / "number/1.png")
GRADE_2 = Image.open(TEXT_PATH / "number/2.png")
GRADE_3 = Image.open(TEXT_PATH / "number/3.png")
GRADE_4 = Image.open(TEXT_PATH / "number/4.png")
GRADE_5 = Image.open(TEXT_PATH / "number/5.png")
GRADE_6 = Image.open(TEXT_PATH / "number/6.png")
grades = [GRADE_0, GRADE_1, GRADE_2, GRADE_3, GRADE_4, GRADE_5, GRADE_6]


def get_ICON():
    return Image.open(ICON).convert("RGBA")


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


async def get_skill_img(char_id: Union[str, int], skill_name: str, pic_url: Optional[str] = None) -> Image.Image:
    char_skill_dir = SKILL_PATH / str(char_id)
    char_skill_dir.mkdir(parents=True, exist_ok=True)

    skill_name = skill_name.strip()
    name = f"skill_{skill_name}.png"
    skill_path = char_skill_dir / name
    if not skill_path.exists():
        if pic_url:
            await download(pic_url, char_skill_dir, name, tag="[DNA]")

    return Image.open(skill_path).convert("RGBA")


async def get_avatar_img(char_id: Union[str, int], pic_url: Optional[str] = None) -> Image.Image:
    char_avatar_dir = AVATAR_PATH
    char_avatar_dir.mkdir(parents=True, exist_ok=True)

    name = f"avatar_{char_id}.png"
    avatar_path = char_avatar_dir / name
    if not avatar_path.exists():
        if pic_url:
            await download(pic_url, char_avatar_dir, name, tag="[DNA]")

    return Image.open(avatar_path).convert("RGBA")


async def get_weapon_img(weapon_id: Union[str, int], pic_url: Optional[str] = None) -> Image.Image:
    weapon_dir = WEAPON_PATH
    weapon_dir.mkdir(parents=True, exist_ok=True)

    name = f"weapon_{weapon_id}.png"
    weapon_path = weapon_dir / name
    if not weapon_path.exists():
        if pic_url:
            await download(pic_url, weapon_dir, name, tag="[DNA]")

    return Image.open(weapon_path).convert("RGBA")


async def get_attr_img(attr_id: Optional[Union[str, int]] = None, pic_url: Optional[str] = None) -> Image.Image:
    if attr_id is None:
        if pic_url:
            attr_id = pic_url.split("/")[-1].split(".")[0]
        else:
            raise ValueError("attr_id 和 pic_url 不能同时为空")

    attr_dir = ATTR_PATH
    attr_dir.mkdir(parents=True, exist_ok=True)

    name = f"attr_{attr_id}.png"
    attr_path = attr_dir / name
    if not attr_path.exists():
        if pic_url:
            await download(pic_url, attr_dir, name, tag="[DNA]")

    return Image.open(attr_path).convert("RGBA")


async def get_weapon_attr_img(attr_id: Optional[Union[str, int]] = None, pic_url: Optional[str] = None) -> Image.Image:
    if attr_id is None:
        if pic_url:
            attr_id = pic_url.split("/")[-1].split(".")[0]
        else:
            raise ValueError("attr_id 和 pic_url 不能同时为空")

    attr_dir = WEAPON_ATTR_PATH
    attr_dir.mkdir(parents=True, exist_ok=True)

    name = f"attr_{attr_id}.png"
    attr_path = attr_dir / name
    if not attr_path.exists():
        if pic_url:
            await download(pic_url, attr_dir, name, tag="[DNA]")

    return Image.open(attr_path).convert("RGBA")


async def get_paint_img(char_id: Union[str, int], pic_url: Optional[str] = None) -> Image.Image:
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


async def get_mod_img(mod_id: Union[str, int], pic_url: Optional[str] = None) -> Image.Image:
    mod_dir = MOD_PATH
    mod_dir.mkdir(parents=True, exist_ok=True)

    name = f"mod_{mod_id}.png"
    mod_path = mod_dir / name
    if not mod_path.exists():
        if pic_url:
            await download(pic_url, mod_dir, name, tag="[DNA]")

    return Image.open(mod_path).convert("RGBA")


def get_grade_img(grade_level: int) -> Image.Image:
    return grades[grade_level]


async def get_avatar_title_img(
    ev: Event,
    uid: str,
    name: str,
    user_level: Optional[int] = None,
    other_info: Optional[list[tuple[str, str]]] = None,
    avatar_user_id: Optional[str] = None,
    uid_hidden: bool = False,
):
    from .fonts.dna_fonts import (
        dna_font_20,
        dna_font_24,
        dna_font_30,
        dna_font_40,
        dna_font_50,
    )

    img = Image.open(TEXT_PATH / "avatar_title_bg.png").convert("RGBA")
    draw = ImageDraw.Draw(img)
    draw.text(
        (320, 100),
        f"{name}",
        COLOR_WHITE,
        dna_font_50,
        "lm",
    )

    # 仅在 UID 未隐藏时显示 UID
    if not uid_hidden:
        get_smooth_drawer().rounded_rectangle(
            (320, 140, 320 + 330, 140 + 40),
            15,
            COLOR_PALE_GOLDENROD,
            target=img,
        )

        draw.text(
            (330, 160),
            f"UID {uid}",
            COLOR_BLACK,
            dna_font_30,
            "lm",
        )

    avater_size = 190

    avatar_temp = Image.new("RGBA", (avater_size, avater_size))

    # 如果 avatar_user_id 为 None，则使用发送者自己的头像
    original_at = ev.at
    if avatar_user_id:
        ev.at = avatar_user_id
    else:
        ev.at = None  # 清空 at，确保获取发送者自己的头像
    try:
        avatar = await get_event_avatar(ev, avatar_path=AVATAR_PATH)
    finally:
        ev.at = original_at  # 恢复原始值

    avatar = avatar.resize((avater_size - 60, avater_size - 60))

    avatar_temp.alpha_composite(avatar, (30, 30))

    avatar_frame = Image.open(TEXT_PATH / "avatar_frame.png").convert("RGBA")
    avatar_frame = avatar_frame.resize((avater_size, avater_size))
    avatar_temp.alpha_composite(avatar_frame, (0, 0))

    if user_level:
        avatar_title_level = Image.open(TEXT_PATH / "avatar_title_level.png").convert("RGBA")
        draw_avatar_title_level = ImageDraw.Draw(avatar_title_level)
        draw_avatar_title_level.text(
            (36, 35),
            f"{user_level}",
            COLOR_WHITE,
            dna_font_24,
            "mm",
        )
        avatar_temp.alpha_composite(avatar_title_level, (120, 120))

    img.alpha_composite(avatar_temp, (115, 20))

    if other_info and len(other_info) >= 2:
        avatar_title_base_info = Image.open(TEXT_PATH / "avatar_title_base_info.png").convert("RGBA")

        if len(other_info) >= 4:
            other_info = other_info[:4]
            next_x = 120
            start_x = 70
        elif len(other_info) == 3:
            next_x = 150
            start_x = 100
        elif len(other_info) == 2:
            next_x = 200
            start_x = 150

        draw_avatar_title_base_info = ImageDraw.Draw(avatar_title_base_info)
        for index, value in enumerate(other_info):
            k, v = value
            draw_avatar_title_base_info.text(
                (index * next_x + start_x, 23),
                v,
                COLOR_WHITE,
                dna_font_40,
                "mm",
            )
            draw_avatar_title_base_info.text(
                (index * next_x + start_x, 63),
                k,
                COLOR_WHITE,
                dna_font_20,
                "mm",
            )

        img.alpha_composite(avatar_title_base_info, (680, 90))

    return img


def get_footer():
    return Image.open(TEXT_PATH / "footer.png")


def get_div():
    return Image.open(TEXT_PATH / "div.png")


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


class SmoothDrawer:
    """通用抗锯齿绘制工具"""

    def __init__(self, scale: int = 4):
        self.scale = scale

    def rounded_rectangle(
        self,
        xy: Union[Tuple[int, int, int, int], Tuple[int, int]],
        radius: int,
        fill: Optional[Color] = None,
        outline: Optional[Color] = None,
        width: int = 0,
        target: Optional[Image.Image] = None,
    ):
        if len(xy) == 4:
            # 边界框坐标 (x0, y0, x1, y1)
            x0, y0, x1, y1 = xy
            w = abs(x1 - x0)
            h = abs(y1 - y0)
            # 如果提供了目标图片，使用边界框的实际坐标
            paste_x, paste_y = min(x0, x1), min(y0, y1)
        elif len(xy) == 2:
            # 尺寸 (width, height) - 向后兼容
            w, h = xy
            paste_x, paste_y = 0, 0
        else:
            raise ValueError(f"xy 参数必须是 2 或 4 个元素的元组，当前为 {len(xy)} 个元素")

        if h <= 0 or w <= 0:
            return

        large = Image.new("RGBA", (w * self.scale, h * self.scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(large)

        # 绘制
        draw.rounded_rectangle(
            (0, 0, w * self.scale, h * self.scale),
            radius=radius * self.scale,
            fill=fill,
            outline=outline,
            width=width * self.scale,
        )

        result = large.resize((w, h))

        if target is not None:
            target.alpha_composite(result, (paste_x, paste_y))
            return

        return


def get_smooth_drawer(scale: int = 4) -> SmoothDrawer:
    return SmoothDrawer(scale=scale)


def compress_to_webp(image_path: Path, quality: int = 80, delete_original: bool = True) -> tuple[bool, Path]:
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
