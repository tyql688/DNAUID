from typing import Optional
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils import dna_api
from ..utils.image import (
    COLOR_WHITE,
    COLOR_SALMON,
    COLOR_GOLDENROD,
    COLOR_FIRE_BRICK,
    COLOR_ORANGE_RED,
    get_div,
    add_footer,
    get_dna_bg,
    get_mod_img,
    get_attr_img,
    get_grade_img,
    get_paint_img,
    get_skill_img,
    get_weapon_img,
    get_smooth_drawer,
    get_avatar_title_img,
)
from ..utils.utils import get_uid_by_config, should_use_other_id
from ..utils.api.model import (
    WeaponDetail,
    RoleInsForTool,
    DNARoleDetailRes,
    DNARoleForToolRes,
    DNAWeaponDetailRes,
)
from ..utils.msgs.notify import (
    dna_not_found,
    dna_uid_invalid,
    dna_not_unlocked,
    dna_token_invalid,
)
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..utils.database.models import DNABind
from ..utils.fonts.dna_fonts import (
    dna_font_18,
    dna_font_24,
    dna_font_26,
    dna_font_30,
)

TEXT_PATH = Path(__file__).parent / "texture2d"
prop_info_bar1 = Image.open(TEXT_PATH / "prop_info_bar1.png")
prop_info_bar2 = Image.open(TEXT_PATH / "prop_info_bar2.png")
global_skill_bg = Image.open(TEXT_PATH / "skill_bg.png")
grade_lock_img = Image.open(TEXT_PATH / "grade_0.png")
grade_unlock_img = Image.open(TEXT_PATH / "grade_1.png")

attr_list = [
    ("atk", "攻击", "icon1.png"),
    ("maxHp", "生命", "icon10.png"),
    ("maxES", "护盾", "icon11.png"),
    ("defense", "防御", "icon9.png"),
    ("maxSp", "最大神志", "icon8.png"),
    ("skillIntensity", "技能威力", "icon7.png"),
    ("skillRange", "技能范围", "icon6.png"),
    ("skillSustain", "技能耐久", "icon5.png"),
    ("skillEfficiency", "技能效益", "icon4.png"),
    ("strongValue", "昂扬", "icon3.png"),
    ("enmityValue", "背水", "icon2.png"),
]

weapon_attr_list = [
    ("type", "武器类型", "icon16.png"),
    ("atk", "攻击", "icon17.png"),
    ("crd", "暴击率", "icon13.png"),
    ("cri", "暴击伤害", "icon12.png"),
    ("speed", "攻击速度", "icon14.png"),
    ("trigger", "触发率", "icon15.png"),
]


async def draw_role_card(bot: Bot, ev: Event, char_name: str):
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

    real_char_name = alias_to_char_name(char_name)
    if not real_char_name:
        await dna_not_found(bot, ev, f"角色别名【{char_name}】")
        return

    char_id = char_name_to_char_id(real_char_name)
    if not char_id:
        await dna_not_found(bot, ev, f"角色【{char_name}】的CharId")
        return
    char_name = real_char_name

    default_role = await dna_api.get_default_role_for_tool(dna_user.cookie, dna_user.dev_code)
    if not default_role.is_success:
        await dna_not_found(bot, ev, "角色列表信息")
        return

    default_role = DNARoleForToolRes.model_validate(default_role.data)
    role_show = default_role.roleInfo.roleShow

    role_char_simple: Optional[RoleInsForTool] = next(
        (i for i in role_show.roleChars if str(i.charId) == char_id), None
    )
    if not role_char_simple:
        await dna_not_found(bot, ev, f"展柜角色【{char_name}】")
        return

    if not role_char_simple.unLocked or not role_char_simple.charEid:
        await dna_not_unlocked(bot, ev, f"当前展柜角色【{char_name}】")
        return

    role_detail = await dna_api.get_role_detail(dna_user.cookie, char_id, role_char_simple.charEid, dna_user.dev_code)
    if not role_detail.is_success:
        await dna_not_found(bot, ev, f"角色【{char_name}】详情")
        return

    role_detail = DNARoleDetailRes.model_validate(role_detail.data)
    role_detail = role_detail.charDetail

    con_weapon_detail: Optional[WeaponDetail] = None
    if role_detail.conWeaponId and role_detail.conWeaponEid:
        con_weapon = await dna_api.get_weapon_detail(
            dna_user.cookie, role_detail.conWeaponId, role_detail.conWeaponEid, dna_user.dev_code
        )
        if con_weapon.is_success:
            con_weapon = DNAWeaponDetailRes.model_validate(con_weapon.data)
            con_weapon_detail = con_weapon.weaponDetail

    # 提前获取头像与分割线，用于计算总高度
    div_img = get_div()
    avatar_title = await get_avatar_title_img(
        ev,
        role_show.roleId,
        role_show.roleName,
        user_level=role_show.level,
        other_info=[(i.paramKey, i.paramValue) for i in role_show.params if i.paramKey in ("总活跃天数", "游戏时长")],
        avatar_user_id=avatar_user_id,
    )
    avatar_title = avatar_title.resize((1000, 1000 * avatar_title.height // avatar_title.width))
    con_weapon_h = 450 if con_weapon_detail else 0
    total_h = 850 + div_img.height + global_skill_bg.height + con_weapon_h + div_img.height + avatar_title.height + 600
    card = get_dna_bg(1000, total_h, "bg2")

    # paint
    paint_img = await get_paint_img(char_id, role_detail.paint)
    paint_img = paint_img.resize((int(1320 * 0.8), int(1320 * 0.8)))
    card.alpha_composite(paint_img, (-280, -100))

    # 个人信息
    info_bg = Image.new("RGBA", (400, 200), (0, 0, 0, 0))
    info_bg_draw = ImageDraw.Draw(info_bg)
    # 名字
    point = Image.open(TEXT_PATH / "point.png")
    info_bg.alpha_composite(point, (10, 10))
    info_bg_draw.text((50, 25), char_name, COLOR_WHITE, dna_font_30, "lm")
    # 属性
    attr_img = await get_attr_img(char_id, role_detail.elementIcon)
    attr_img = attr_img.resize((attr_img.width // 2, attr_img.height // 2))
    info_bg.alpha_composite(attr_img, (10, 40))
    # 命座
    grade_img = get_grade_img(role_detail.gradeLevel)
    ellipse = Image.new("RGBA", (34, 35))
    get_smooth_drawer().rounded_rectangle((0, 0, 34, 35), fill=COLOR_FIRE_BRICK, radius=7, target=ellipse)
    ellipse.alpha_composite(grade_img, (0, 5))
    info_bg.alpha_composite(ellipse, (50, 60))
    # 等级
    ellipse = Image.new("RGBA", (80, 35))
    ellipse_draw = ImageDraw.Draw(ellipse)
    get_smooth_drawer().rounded_rectangle((0, 0, 80, 35), fill=COLOR_FIRE_BRICK, radius=7, target=ellipse)
    ellipse_draw.text((40, 17), f"Lv.{role_detail.level}", COLOR_WHITE, dna_font_26, "mm")
    info_bg.alpha_composite(ellipse, (100, 60))

    card.alpha_composite(info_bg, (550, 80))

    # 命座解锁
    grade_unlock_bg = Image.new("RGBA", (1000, 130), (0, 0, 0, 0))
    for i in range(1, 7):
        grade_bg = grade_lock_img.copy() if i > role_detail.gradeLevel else grade_unlock_img.copy()
        grade_img = get_grade_img(i)
        grade_img = grade_img.resize((int(grade_img.width * 1.8), int(grade_img.height * 1.8)))
        grade_bg.alpha_composite(grade_img, (33, 37))
        grade_unlock_bg.alpha_composite(grade_bg, (100 + (i - 1) * 150, 0))

    grade_unlock_bg = grade_unlock_bg.resize((int(1000 * 0.5), int(130 * 0.5)))
    card.alpha_composite(grade_unlock_bg, (0, 750))

    # 属性
    attr_bg = Image.new("RGBA", (400, 583), (0, 0, 0, 128))
    for index, attrs in enumerate(attr_list):
        prop_info = prop_info_bar1.copy() if index % 2 == 0 else prop_info_bar2.copy()
        prop_info_draw = ImageDraw.Draw(prop_info)
        attr_value = f"{getattr(role_detail.attribute, attrs[0]) or ''}"

        icon = Image.open(TEXT_PATH / f"icons/{attrs[2]}")
        # icon
        prop_info.alpha_composite(icon, (0, 0))
        # 属性名
        prop_info_draw.text(
            (53, 25),
            attrs[1],
            COLOR_WHITE,
            font=dna_font_26,
            anchor="lm",
        )
        # 属性值
        prop_info_draw.text(
            (370, 25),
            (attr_value if "%" in attr_value or not attr_value.isdigit() else f"{int(attr_value):,}"),
            COLOR_WHITE,
            font=dna_font_26,
            anchor="rm",
        )
        attr_bg.alpha_composite(prop_info, (0, index * 53))

    card.alpha_composite(attr_bg, (550, 200))

    h_index = 850
    card.alpha_composite(div_img, (0, h_index))
    h_index += div_img.height

    # 技能
    for index, skill in enumerate(role_detail.skills[:3]):
        skill_bg = global_skill_bg.copy()
        skill_bg_draw = ImageDraw.Draw(skill_bg)

        skill_img = await get_skill_img(char_id, skill.skillName, skill.icon)
        skill_img = skill_img.resize((100, 100))
        skill_bg.alpha_composite(skill_img, (20, 30))

        # 技能名字
        if len(skill.skillName) <= 5:
            skill_bg_draw.text((120, 55), skill.skillName, COLOR_GOLDENROD, dna_font_24, "lm")
        else:
            skill_bg_draw.text(
                (120, 55),
                skill.skillName,
                COLOR_GOLDENROD,
                dna_font_18,
                "lm",
            )

        get_smooth_drawer().rounded_rectangle(
            (120, 80, 200, 110),
            10,
            COLOR_SALMON,
            target=skill_bg,
        )

        skill_bg_draw.text((160, 94), f"Lv.{skill.level}", COLOR_WHITE, dna_font_26, "mm")

        card.alpha_composite(skill_bg, (50 + index * 300, h_index))
    h_index += global_skill_bg.height

    if con_weapon_detail:
        con_weapon_mod_bg = Image.new("RGBA", (1000, 500), (0, 0, 0, 0))
        con_weapon_mod_bg_draw = ImageDraw.Draw(con_weapon_mod_bg)
        # 横向排列4个mod 俩左 俩右
        sortmods = [
            con_weapon_detail.modes[0],
            con_weapon_detail.modes[2],
            con_weapon_detail.modes[3],
            con_weapon_detail.modes[1],
        ]
        for index, mod in enumerate(sortmods):
            quality = mod.quality or 1
            left = True if index <= 1 else False
            mod_bg = Image.open(TEXT_PATH / f"mod/mod_{'left' if left else 'right'}_{quality}.png")
            mod_bg_draw = ImageDraw.Draw(mod_bg)

            if mod.id != -1 and mod.name:
                mod_img = await get_mod_img(mod.id, mod.icon)
                mod_img = mod_img.resize((180, 180))
                mod_bg.alpha_composite(mod_img, (35, 15))
                # 名字
                size = (115, 180) if left else (140, 180)
                mod_bg_draw.text(size, mod.name, COLOR_WHITE, dna_font_26, "mm")

            if mod.id != -1 and mod.level:
                size = (54, 30, 106, 60) if left else (134, 30, 186, 60)
                get_smooth_drawer().rounded_rectangle(
                    size,
                    10,
                    COLOR_ORANGE_RED,
                    target=mod_bg,
                )
                size = (80, 44) if left else (160, 44)
                mod_bg_draw.text(size, f"+{mod.level}", COLOR_WHITE, dna_font_26, "mm")
                # mod_bg_draw.text(size, f"+{10}", COLOR_WHITE, dna_font_26, "mm")

            # 横向排列4个mod
            con_weapon_mod_bg.alpha_composite(mod_bg, (40 + index * 220, 0))

        # 武器背景
        weapon_bg = Image.open(TEXT_PATH / "weapon_bg.png")
        # 贴武器
        weapon_img = await get_weapon_img(con_weapon_detail.id, con_weapon_detail.icon)
        weapon_img = weapon_img.resize((180, 180))
        weapon_bg.alpha_composite(weapon_img, (-10, -10))

        # 贴武器等级
        ellipse = Image.new("RGBA", (80, 35))
        ellipse_draw = ImageDraw.Draw(ellipse)
        get_smooth_drawer().rounded_rectangle((0, 0, 80, 35), fill=COLOR_FIRE_BRICK, radius=7, target=ellipse)
        ellipse_draw.text((40, 17), f"Lv.{con_weapon_detail.level}", COLOR_WHITE, dna_font_26, "mm")
        weapon_bg.alpha_composite(ellipse, (150, 100))

        weapon_bg = weapon_bg.resize((int(weapon_bg.width * 0.8), int(weapon_bg.height * 0.8)))

        con_weapon_mod_bg.alpha_composite(weapon_bg, (70, 250))
        # 贴武器名字
        con_weapon_mod_bg_draw.text((70, 385), con_weapon_detail.name, COLOR_WHITE, dna_font_26, "lm")
        # 武器属性
        weapon_attr = Image.open(TEXT_PATH / "weapon_attr.png")
        weapon_attr_draw = ImageDraw.Draw(weapon_attr)

        # 先左再右，先上再下，3行2列
        for index, attrs in enumerate(weapon_attr_list):
            if index == 0:
                attr_value = f"{con_weapon_detail.elementName}"
            else:
                value = getattr(con_weapon_detail.attribute, attrs[0])
                if isinstance(value, float):
                    value = f"{value:.0%}"
                else:
                    value = f"{value}"
                attr_value = value

            icon = Image.open(TEXT_PATH / f"icons/{attrs[2]}")
            # icon
            weapon_attr.alpha_composite(icon, (index % 2 * 320, index // 2 * 53))
            # 属性名
            weapon_attr_draw.text(
                (53 + (index % 2) * 320, 25 + (index // 2) * 53),
                attrs[1],
                COLOR_WHITE,
                font=dna_font_26,
                anchor="lm",
            )
            # 属性值
            weapon_attr_draw.text(
                (310 + (index % 2) * 318, 25 + (index // 2) * 53),
                (attr_value if "%" in attr_value or not attr_value.isdigit() else f"{int(attr_value):,}"),
                COLOR_WHITE,
                font=dna_font_26,
                anchor="rm",
            )
            con_weapon_mod_bg.alpha_composite(weapon_attr, (290, 250))

        card.alpha_composite(con_weapon_mod_bg, (0, h_index))
        h_index += 450

    card.alpha_composite(div_img, (0, h_index))
    h_index += div_img.height

    # mod
    all_mod_bg = Image.new("RGBA", (1000, 500), (0, 0, 0, 0))
    # 左4
    left_list = [role_detail.modes[0], role_detail.modes[2], role_detail.modes[4], role_detail.modes[6]]
    for index, mod in enumerate(left_list):
        quality = mod.quality or 1
        mod_bg = Image.open(TEXT_PATH / f"mod/mod_left_{quality}.png")
        mod_bg_draw = ImageDraw.Draw(mod_bg)

        if mod.id != -1 and mod.name:
            mod_img = await get_mod_img(mod.id, mod.icon)
            mod_img = mod_img.resize((180, 180))
            mod_bg.alpha_composite(mod_img, (35, 15))
            mod_bg_draw.text((115, 180), mod.name, COLOR_WHITE, dna_font_26, "mm")

        if mod.id != -1 and mod.level:
            get_smooth_drawer().rounded_rectangle(
                (54, 30, 106, 60),
                10,
                COLOR_ORANGE_RED,
                target=mod_bg,
            )

            mod_bg_draw.text((80, 44), f"+{mod.level}", COLOR_WHITE, dna_font_26, "mm")

        # 2行2列，先左右，再上下
        all_mod_bg.alpha_composite(mod_bg, (30 + (index % 2) * 180, (index // 2) * 250))

    # 右4
    right_list = [role_detail.modes[1], role_detail.modes[3], role_detail.modes[7], role_detail.modes[5]]
    for index, mod in enumerate(right_list):
        quality = mod.quality or 1
        mod_bg = Image.open(TEXT_PATH / f"mod/mod_right_{quality}.png")
        mod_bg_draw = ImageDraw.Draw(mod_bg)

        if mod.id != -1 and mod.name:
            mod_img = await get_mod_img(mod.id, mod.icon)
            mod_img = mod_img.resize((180, 180))
            mod_bg.alpha_composite(mod_img, (35, 15))
            mod_bg_draw.text((140, 180), mod.name, COLOR_WHITE, dna_font_26, "mm")

        if mod.id != -1 and mod.level:
            get_smooth_drawer().rounded_rectangle(
                (134, 30, 186, 60),
                10,
                COLOR_ORANGE_RED,
                target=mod_bg,
            )

            mod_bg_draw.text((160, 44), f"+{mod.level}", COLOR_WHITE, dna_font_26, "mm")

        # 2行2列，先左右，再上下
        all_mod_bg.alpha_composite(mod_bg, (530 + (index % 2) * 180, (index // 2) * 250))

    # 中1
    center_list = role_detail.modes[-1]
    quality = center_list.quality or 1
    mod_bg = Image.open(TEXT_PATH / f"mod/mod_center_{quality}.png")
    mod_bg_draw = ImageDraw.Draw(mod_bg)
    if center_list.id != -1 and center_list.name:
        mod_img = await get_mod_img(center_list.id, center_list.icon)
        mod_img = mod_img.resize((150, 150))
        mod_bg.alpha_composite(mod_img, (5, 5))
        mod_bg_draw.text((80, 170), center_list.name, COLOR_WHITE, dna_font_26, "mm")

    if center_list.id != -1 and center_list.level:
        get_smooth_drawer().rounded_rectangle(
            (110, 110, 150, 140),
            10,
            COLOR_ORANGE_RED,
            target=mod_bg,
        )
        mod_bg_draw.text((130, 124), f"+{center_list.level}", COLOR_WHITE, dna_font_26, "mm")

    all_mod_bg.alpha_composite(mod_bg, (415, 100))

    card.alpha_composite(all_mod_bg, (0, h_index))
    h_index += 500

    # 头像等（已在前面生成并用于计算总高度）
    card.alpha_composite(avatar_title, (0, h_index))

    card = add_footer(card, 600)
    card = await convert_img(card)
    await bot.send(card)
