# 根据 code 查找类型（role/weapon/mzx）和名称的映射表
from typing import Literal

from pydantic import BaseModel, Field

_data = {
    "role": [
        {"code": "MH_60102", "name": "扼守/无尽", "on": 0},
        {"code": "MH_60202", "name": "拆解", "on": 0},
        {"code": "MH_60302", "name": "勘探/无尽", "on": 0},
        {"code": "MH_60402", "name": "追缉", "on": 0},
        {"code": "MH_60502", "name": "探险/无尽", "on": 0},
        {"code": "MH_60602", "name": "调停", "on": 0},
        {"code": "MH_60702", "name": "避险", "on": 0},
        {"code": "MH_60802", "name": "迁移", "on": 0},
        {"code": "MH_60902", "name": "驱逐", "on": 0},
        {"code": "MH_61002", "name": "护送", "on": 0},
        {"code": "MH_61102", "name": "驱离", "on": 0},
    ],
    "weapon": [
        {"code": "MH_62102", "name": "扼守/无尽", "on": 0},
        {"code": "MH_62202", "name": "拆解", "on": 0},
        {"code": "MH_62302", "name": "勘探/无尽", "on": 0},
        {"code": "MH_62402", "name": "追缉", "on": 0},
        {"code": "MH_62502", "name": "探险/无尽", "on": 0},
        {"code": "MH_62602", "name": "调停", "on": 0},
        {"code": "MH_60702", "name": "避险", "on": 0},
        {"code": "MH_62802", "name": "迁移", "on": 0},
        {"code": "MH_62902", "name": "驱逐", "on": 0},
        {"code": "MH_63002", "name": "护送", "on": 0},
        {"code": "MH_63102", "name": "驱离", "on": 0},
    ],
    "mzx": [
        {"code": "MH_64102", "name": "扼守/无尽", "on": 0},
        {"code": "MH_64202", "name": "拆解", "on": 0},
        {"code": "MH_64302", "name": "勘探/无尽", "on": 0},
        {"code": "MH_64402", "name": "追缉", "on": 0},
        {"code": "MH_64502", "name": "探险/无尽", "on": 0},
        {"code": "MH_64602", "name": "调停", "on": 0},
        {"code": "MH_64702", "name": "避险", "on": 0},
        {"code": "MH_64802", "name": "迁移", "on": 0},
        {"code": "MH_64902", "name": "驱逐", "on": 0},
        {"code": "MH_65002", "name": "护送", "on": 0},
        {"code": "MH_65102", "name": "驱离", "on": 0},
    ],
}


class MHInfo(BaseModel):
    """代码信息模型，用于 CODE_MAP 返回值"""

    type: Literal["role", "weapon", "mzx"] = Field(description="类型")
    name: str = Field(description="名称")


CODE_MAP: dict[str, MHInfo] = {
    **{item["code"]: MHInfo(type="role", name=item["name"]) for item in _data["role"]},
    **{
        item["code"]: MHInfo(type="weapon", name=item["name"])
        for item in _data["weapon"]
    },
    **{item["code"]: MHInfo(type="mzx", name=item["name"]) for item in _data["mzx"]},
}

MH_LIST = list(
    set(
        item["name"].split("/")[0]
        for item in _data["role"] + _data["weapon"] + _data["mzx"]
    )
)


def get_mh_info(code: str) -> MHInfo | None:
    return CODE_MAP.get(code)


def get_mh_name(code: str) -> str | None:
    info = get_mh_info(code)
    return info.name if info else None


def get_mh_type(code: str) -> Literal["role", "weapon", "mzx"] | None:
    info = get_mh_info(code)
    return info.type if info else None


def get_mh_type_name(mh_type: Literal["role", "weapon", "mzx"]) -> str:
    return {
        "role": "角色",
        "weapon": "武器",
        "mzx": "魔之楔",
    }[mh_type]


def get_mh_list() -> list[str]:
    return MH_LIST
