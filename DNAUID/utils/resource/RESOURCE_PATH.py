import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from gsuid_core.data_store import get_res_path

MAIN_PATH = get_res_path() / "DNAUID"
sys.path.append(str(MAIN_PATH))

# 配置文件
CONFIG_PATH = MAIN_PATH / "config.json"
SIGN_CONFIG_PATH = MAIN_PATH / "sign_config.json"

# 其他的素材
OTHER_PATH = MAIN_PATH / "other"
SIGN_PATH = OTHER_PATH / "sign"
ANN_CARD_PATH = OTHER_PATH / "ann_card"


def init_dir():
    for i in [
        MAIN_PATH,
        SIGN_PATH,
        ANN_CARD_PATH,
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
