import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from gsuid_core.data_store import get_res_path

MAIN_PATH = get_res_path() / "DNAUID"
sys.path.append(str(MAIN_PATH))

# 配置文件
CONFIG_PATH = MAIN_PATH / "config.json"
SIGN_CONFIG_PATH = MAIN_PATH / "sign_config.json"

# 用户数据保存文件
PLAYER_PATH = MAIN_PATH / "players"

# 游戏素材
RESOURCE_PATH = MAIN_PATH / "resource"
AVATAR_PATH = RESOURCE_PATH / "avatar"  # 头像
WEAPON_PATH = RESOURCE_PATH / "weapon"  # 武器
PAINT_PATH = RESOURCE_PATH / "paint"  # 立绘
DOB_PATH = RESOURCE_PATH / "dob"  # DOB 数据包转换产物（dna-builder 数据源）
DOB_DATA_PATH = DOB_PATH / "dob_data.json"
SKILL_PATH = RESOURCE_PATH / "skill"  # 技能
ATTR_PATH = RESOURCE_PATH / "attr"  # 属性
MOD_PATH = RESOURCE_PATH / "mod"  # mod
WEAPON_ATTR_PATH = RESOURCE_PATH / "weapon_attr"  # 武器属性
WEEKLY_ITEM_PATH = RESOURCE_PATH / "weekly_item"  # 周报资源图标
ID2NAME_PATH = RESOURCE_PATH / "id2name.json"  # id2name.json
# 别名
ALIAS_PATH = RESOURCE_PATH / "alias"
CHAR_ALIAS_PATH = ALIAS_PATH / "char_alias.json"  # char_alias.json
WEAPON_ALIAS_PATH = ALIAS_PATH / "weapon_alias.json"  # weapon_alias.json

# 自定义背景图
CUSTOM_PATH = MAIN_PATH / "custom"
CUSTOM_PAINT_PATH = CUSTOM_PATH / "custom_paint"  # 自定义立绘

# 其他的素材
OTHER_PATH = MAIN_PATH / "other"
SIGN_PATH = OTHER_PATH / "sign"
ANN_CARD_PATH = OTHER_PATH / "ann_card"
CALENDAR_PATH = OTHER_PATH / "calendar"


def init_dir() -> None:
    for i in [
        MAIN_PATH,
        SIGN_PATH,
        ANN_CARD_PATH,
        PLAYER_PATH,
        RESOURCE_PATH,
        AVATAR_PATH,
        WEAPON_PATH,
        PAINT_PATH,
        SKILL_PATH,
        ATTR_PATH,
        MOD_PATH,
        WEEKLY_ITEM_PATH,
        CUSTOM_PATH,
        CUSTOM_PAINT_PATH,
        ALIAS_PATH,
    ]:
        i.mkdir(parents=True, exist_ok=True)


init_dir()


# 设置 Jinja2 环境
TEMP_PATH = Path(__file__).parents[1].parent / "templates"
DNA_TEMPLATES = Environment(
    loader=FileSystemLoader(
        [
            str(TEMP_PATH),
        ]
    )
)
