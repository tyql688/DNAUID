import json
import random
from pathlib import Path
from typing import Final, List

DEFAULT_TEMPLATES: Final[List[str]] = [
    "互评",
    "支持楼主",
    "说得很有道理",
    "学到了",
    "赞同",
]
_TEMPLATE_FILE: Final[Path] = Path(__file__).with_name("reply-templates.json")


def _load_templates(path: Path = _TEMPLATE_FILE) -> List[str]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f).get("replies") or DEFAULT_TEMPLATES
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return DEFAULT_TEMPLATES


_REPLY_TEMPLATES: Final[List[str]] = _load_templates()


def get_random_reply() -> str:
    """返回一条随机模板回复。"""
    return random.choice(_REPLY_TEMPLATES)
