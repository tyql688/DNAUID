from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.models import Event

from .service import BuildCard
from ..utils.image import (
    COLOR_BLACK,
    COLOR_WHITE,
    COLOR_PALE_GOLDENROD,
    get_element_img,
    get_smooth_drawer,
    get_avatar_title_img,
)
from ..utils.dob.pack import source_line
from ..utils.dob.panel import compute_panel
from ..dna_detail.role_card import render_role_card
from ..utils.fonts.dna_fonts import dna_font_24, dna_font_30

TEXT_PATH = Path(__file__).parent.parent / "dna_detail" / "texture2d"
DIM = (205, 205, 212)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _info_box(card: BuildCard) -> Image.Image:
    """构筑标题 + 属性图标 + 角色·等级（构筑没有溯源数据，不画溯源徽章）。"""
    role = card.build.role
    box = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(box)
    with Image.open(TEXT_PATH / "point.png") as point:
        box.alpha_composite(point.convert("RGBA"), (10, 10))
    title = card.title
    while title and draw.textlength(title + "…", font=dna_font_30) > 330:
        title = title[:-1]
    draw.text((50, 30), title if title == card.title else title + "…", COLOR_WHITE, dna_font_30, "lm")
    element = get_element_img(role.elementName)
    box.alpha_composite(element.resize((element.width // 2, element.height // 2)), (10, 62))
    draw.text((50, 92), f"{role.charName} · Lv.{role.level}", DIM, dna_font_24, "lm")
    return box


async def _author_title(card: BuildCard, ev: Event) -> Image.Image:
    """头像条：作者头像与名字，UID 徽章位换成构筑 ID。"""
    title = await get_avatar_title_img(
        ev,
        card.bdid,
        _clip(card.author, 12),
        user_level=card.build.role.level,
        other_info=[
            (_clip(card.target_fn, 12), card.target_value),
            ("点赞", str(card.likes)),
            ("浏览", str(card.views)),
        ],
        avatar_user_id=card.author_qq if card.author_qq.isdigit() else None,
        uid_hidden=True,
    )
    get_smooth_drawer().rounded_rectangle((320, 140, 650, 180), 15, COLOR_PALE_GOLDENROD, target=title)
    ImageDraw.Draw(title).text((330, 160), f"BD {card.bdid}", COLOR_BLACK, dna_font_30, "lm")
    return title


async def draw_build_card(card: BuildCard, ev: Event) -> Image.Image:
    image, _ = await render_role_card(
        card.build,
        compute_panel(card.build),
        info_box=_info_box(card),
        avatar_title=await _author_title(card, ev),
        footer_line=f"{source_line()} | BD:{card.bdid}",
        grade_level=None,
    )
    return image
