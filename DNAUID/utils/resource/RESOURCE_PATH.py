import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from gsuid_core.data_store import get_res_path

MAIN_PATH = get_res_path() / "DNAUID"
sys.path.append(str(MAIN_PATH))

# 配置文件
CONFIG_PATH = MAIN_PATH / "config.json"


def init_dir():
    for i in [
        MAIN_PATH,
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
