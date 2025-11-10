from enum import Enum
from typing import Literal


class BoardcastTypeEnum(str, Enum):
    """订阅类型"""

    SIGN_RESULT = "订阅二重螺旋签到结果"
    SIGN_DNA = "订阅二重螺旋签到"


BoardcastType = Literal[
    BoardcastTypeEnum.SIGN_RESULT,
    BoardcastTypeEnum.SIGN_DNA,
]
