from __future__ import annotations

MASTER_CHAR_FEMALE_LIGHT_ID = "1601"
MASTER_CHAR_MALE_LIGHT_ID = "160101"
MASTER_CHAR_FEMALE_DARK_ID = "1201"
MASTER_CHAR_MALE_DARK_ID = "120101"

MASTER_CHAR_FEMALE_IDS = frozenset((MASTER_CHAR_FEMALE_LIGHT_ID, MASTER_CHAR_FEMALE_DARK_ID))
MASTER_CHAR_MALE_IDS = frozenset((MASTER_CHAR_MALE_LIGHT_ID, MASTER_CHAR_MALE_DARK_ID))
MASTER_CHAR_LIGHT_IDS = frozenset((MASTER_CHAR_FEMALE_LIGHT_ID, MASTER_CHAR_MALE_LIGHT_ID))
MASTER_CHAR_DARK_IDS = frozenset((MASTER_CHAR_FEMALE_DARK_ID, MASTER_CHAR_MALE_DARK_ID))
MASTER_CHAR_IDS = frozenset(
    (
        MASTER_CHAR_FEMALE_LIGHT_ID,
        MASTER_CHAR_MALE_LIGHT_ID,
        MASTER_CHAR_FEMALE_DARK_ID,
        MASTER_CHAR_MALE_DARK_ID,
    )
)

MASTER_CHAR_NAME_BY_ID = {
    MASTER_CHAR_MALE_LIGHT_ID: "男主-光",
    MASTER_CHAR_FEMALE_LIGHT_ID: "女主-光",
    MASTER_CHAR_FEMALE_DARK_ID: "女主-暗",
    MASTER_CHAR_MALE_DARK_ID: "男主-暗",
}
MASTER_CHAR_ID_BY_NAME = {name: char_id for char_id, name in MASTER_CHAR_NAME_BY_ID.items()}

MASTER_CHAR_PANEL_DIR = "master_char"
MASTER_CHAR_ALIAS_TO_NAME = {
    "主角": "女主-光",
    "男主": "男主-光",
    "女主": "女主-光",
    "男主光": "男主-光",
    "女主光": "女主-光",
    "男主暗": "男主-暗",
    "女主暗": "女主-暗",
    "主角男": "男主-光",
    "主角女": "女主-光",
    "主角（男）": "男主-光",
    "主角（女）": "女主-光",
    **{name: name for name in MASTER_CHAR_ID_BY_NAME},
}


def is_master_char_id(char_id: str | int) -> bool:
    return str(char_id) in MASTER_CHAR_IDS


def get_master_char_panel_dir(char_id: str | int) -> str:
    if is_master_char_id(char_id):
        return MASTER_CHAR_PANEL_DIR
    return str(char_id)
