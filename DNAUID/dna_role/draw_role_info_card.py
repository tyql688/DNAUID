import math
from typing import List, Literal, Optional
from pathlib import Path

from PIL import Image, ImageDraw
from pydantic import BaseModel

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils import dna_api
from ..utils.image import (
    COLOR_WHITE,
    COLOR_FIRE_BRICK,
    COLOR_PALE_GOLDENROD,
    add_footer,
    get_dna_bg,
    get_attr_img,
    get_grade_img,
    get_avatar_img,
    get_weapon_img,
    get_smooth_drawer,
    get_weapon_attr_img,
    get_avatar_title_img,
)
from ..utils.utils import get_uid_by_config, should_use_other_id
from ..utils.api.model import DNARoleForToolRes
from ..utils.msgs.notify import (
    dna_not_found,
    dna_uid_invalid,
    dna_token_invalid,
)
from ..utils.database.models import DNABind
from ..utils.fonts.dna_fonts import (
    dna_font_20,
    dna_font_25,
    dna_font_40,
    dna_font_50,
)

TEXT_PATH = Path(__file__).parent / "texture2d"
global_item_fg = Image.open(TEXT_PATH / "item_fg.png")
global_item_mask = Image.open(TEXT_PATH / "item_mask.png")
global_role_bg = Image.open(TEXT_PATH / "bg/bg1.png")
global_lang_weapon_bg = Image.open(TEXT_PATH / "bg/bg4.png")
global_close_weapon_bg = Image.open(TEXT_PATH / "bg/bg5.png")
hang_num = 5


def is_show_role_info_card():
    from ..dna_config.dna_config import DNAConfig

    return DNAConfig.get_config("RoleInfoCard").data


class ItemTemp(BaseModel):
    type: Literal["role", "weapon"]
    id: int
    name: str
    level: int
    element_icon: str
    icon: str
    grade_level: Optional[int] = None
    unlocked: bool = False


async def draw_role_info_card(bot: Bot, ev: Event):
    user_id = get_uid_by_config(ev)
    # 根据配置决定是否使用被AT用户的头像
    avatar_user_id = ev.at if should_use_other_id(ev) else None
    uid = await DNABind.get_uid_by_game(user_id, ev.bot_id)
    if not uid:
        await dna_uid_invalid(bot, ev)
        return

    dna_user = await dna_api.get_dna_user(uid, user_id, ev.bot_id)
    if not dna_user:
        await dna_token_invalid(bot, ev)
        return

    default_role = await dna_api.get_default_role_for_tool(dna_user.cookie, dna_user.dev_code)
    if not default_role.is_success:
        await dna_not_found(bot, ev, "角色列表信息")
        return

    default_role = DNARoleForToolRes.model_validate(default_role.data)
    role_show = default_role.roleInfo.roleShow
    # 解锁角色数量
    role_unlocked_count = len([i for i in role_show.roleChars if i.unLocked])
    # 解锁远程武器数量
    lang_weapon_unlocked_count = len([i for i in role_show.langRangeWeapons if i.unLocked])
    # 解锁近战武器数量
    close_weapon_unlocked_count = len([i for i in role_show.closeWeapons if i.unLocked])

    # 成就展示
    achievement_info = [
        ("角色数量", str(role_unlocked_count)),
        ("近战武器", str(close_weapon_unlocked_count)),
        ("远程武器", str(lang_weapon_unlocked_count)),
    ]
    achievement_info.extend(
        [(i.paramKey, i.paramValue) for i in role_show.params if i.paramKey in ("装饰数量", "魔灵数量")]
    )
    achievement_info.extend([("总成就数", str(role_show.roleAchv.total))])

    show_none = is_show_role_info_card()

    role_len = len(role_show.roleChars) if show_none else role_unlocked_count
    lang_len = len(role_show.langRangeWeapons) if show_none else lang_weapon_unlocked_count
    close_len = len(role_show.closeWeapons) if show_none else close_weapon_unlocked_count
    h = 650 + 100 + 50  # title+info+footer
    if role_len > 0:
        h += 320 * math.ceil(role_len / hang_num) + 70  # bar+role
    if lang_len > 0:
        h += 320 * math.ceil(lang_len / hang_num) + 70  # bar+weapon
    if close_len > 0:
        h += 320 * math.ceil(close_len / hang_num) + 70  # bar+weapon
    card = get_dna_bg(1200, h, "bg1")

    start_y = 0
    title_mask = Image.open(TEXT_PATH / "title_mask.png")
    title_bg = Image.open(TEXT_PATH / "title_bg.jpg")
    title_bg = title_bg.resize((title_mask.width, title_mask.height))
    card.paste(title_bg, (0, 0), title_mask)
    start_y += 650

    # title
    avatar_title = await get_avatar_title_img(
        ev,
        role_show.roleId,
        role_show.roleName,
        user_level=role_show.level,
        other_info=[(i.paramKey, i.paramValue) for i in role_show.params if i.paramKey in ("总活跃天数", "游戏时长")],
        avatar_user_id=avatar_user_id,
    )
    card.alpha_composite(avatar_title, (-50, 400))

    # info
    info_bar = Image.open(TEXT_PATH / "info_bar.png")
    info_bar_draw = ImageDraw.Draw(info_bar)

    for index, info in enumerate(achievement_info):
        # 数量
        info_bar_draw.text((65 + index * 215, 20), info[1], COLOR_WHITE, dna_font_50, "mm")
        # 描述
        info_bar_draw.text((65 + index * 215, 63), info[0], COLOR_PALE_GOLDENROD, dna_font_25, "mm")

    card.alpha_composite(info_bar, (100, start_y))
    start_y += 100

    # div bg
    div_bg = Image.open(TEXT_PATH / "div_bg.png")
    div_bg_draw = ImageDraw.Draw(div_bg)
    div_bg_draw.text((600, 33), "角色信息", COLOR_WHITE, dna_font_40, "mm")
    card.alpha_composite(div_bg, (0, start_y))
    start_y += 70

    start_y = await _draw_item(
        card,
        start_y,
        [
            ItemTemp(
                type="role",
                id=role.charId,
                name=role.name,
                level=role.level,
                element_icon=role.elementIcon,
                icon=role.icon,
                grade_level=role.gradeLevel,
                unlocked=role.unLocked,
            )
            for role in role_show.roleChars
        ],
        global_role_bg,
        show_none,
    )

    # div bg
    div_bg = Image.open(TEXT_PATH / "div_bg.png")
    div_bg_draw = ImageDraw.Draw(div_bg)
    div_bg_draw.text((600, 33), "近战武器", COLOR_WHITE, dna_font_40, "mm")
    card.alpha_composite(div_bg, (0, start_y))
    start_y += 70

    start_y = await _draw_item(
        card,
        start_y,
        [
            ItemTemp(
                type="weapon",
                id=weapon.weaponId,
                name=weapon.name,
                level=weapon.level,
                element_icon=weapon.elementIcon,
                icon=weapon.icon,
                grade_level=weapon.skillLevel,
                unlocked=weapon.unLocked,
            )
            for weapon in role_show.closeWeapons
        ],
        global_close_weapon_bg,
        show_none,
    )

    # div bg
    div_bg = Image.open(TEXT_PATH / "div_bg.png")
    div_bg_draw = ImageDraw.Draw(div_bg)
    div_bg_draw.text((600, 33), "远程武器", COLOR_WHITE, dna_font_40, "mm")
    card.alpha_composite(div_bg, (0, start_y))
    start_y += 70

    start_y = await _draw_item(
        card,
        start_y,
        [
            ItemTemp(
                type="weapon",
                id=weapon.weaponId,
                name=weapon.name,
                level=weapon.level,
                element_icon=weapon.elementIcon,
                icon=weapon.icon,
                grade_level=weapon.skillLevel,
                unlocked=weapon.unLocked,
            )
            for weapon in role_show.langRangeWeapons
        ],
        global_lang_weapon_bg,
        show_none,
    )

    card = add_footer(card, 600)
    card = await convert_img(card)
    await bot.send(card)


async def _draw_item(card: Image.Image, start_y: int, items: List[ItemTemp], item_bg: Image.Image, show_none: bool):
    items = items if show_none else [i for i in items if i.unlocked]
    for index, item in enumerate(items):
        temp_bg = Image.new("RGBA", (210, 300))
        temp_bg2 = Image.new("RGBA", (210, 300))

        item_mask = global_item_mask.copy()
        mine_bg = item_bg.copy()
        if item.type == "role":
            item_img = await get_avatar_img(item.id, item.icon)
        else:
            item_img = await get_weapon_img(item.id, item.icon)

        temp_bg.alpha_composite(item_img, (-20, 0))
        temp_bg2.paste(temp_bg, (0, 0), item_mask)
        mine_bg.alpha_composite(temp_bg2, (0, 0))

        fg = global_item_fg.copy()
        fg_draw = ImageDraw.Draw(fg)

        # name
        fg_draw.text((100, 275), item.name, COLOR_WHITE, dna_font_20, "mm")
        # level
        if item.level > 0:
            fg_draw.text((128, 215), f"Lv.{item.level}", COLOR_WHITE, dna_font_20, "mm")
        else:
            fg_draw.text((128, 215), "未解锁", COLOR_WHITE, dna_font_20, "mm")
        # element
        if item.type == "role":
            attr_img = await get_attr_img(pic_url=item.element_icon)
            attr_img = attr_img.resize((attr_img.width // 2, attr_img.height // 2))
            fg.alpha_composite(attr_img, (0, 20))
        else:
            attr_img = await get_weapon_attr_img(pic_url=item.element_icon)
            attr_img = attr_img.resize((attr_img.width // 2, attr_img.height // 2))
            fg.alpha_composite(attr_img, (-3, 23))

        # 画命座
        if item.grade_level is not None:
            # 当前命座
            grade_img = get_grade_img(item.grade_level)
            ellipse = Image.new("RGBA", (34, 35))
            get_smooth_drawer().rounded_rectangle((0, 0, 34, 35), fill=COLOR_FIRE_BRICK, radius=7, target=ellipse)
            ellipse.alpha_composite(grade_img, (0, 5))
            fg.alpha_composite(ellipse, (145, 35))

        if not item.unlocked:
            # 置灰
            mine_bg = mine_bg.convert("RGBA").point(lambda x: x * 0.5)
            fg = fg.convert("RGBA").point(lambda x: x * 0.5)
        # 一行5个 先左再右
        card.alpha_composite(mine_bg, (50 + index % 5 * 230, start_y + index // 5 * 320))
        card.alpha_composite(fg, (50 + index % 5 * 230, start_y + index // 5 * 320))

    total_lines = math.ceil(len(items) / hang_num)
    return start_y + 320 * total_lines
