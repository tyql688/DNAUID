from enum import StrEnum
from typing import Literal


class BoardcastTypeEnum(StrEnum):
    """订阅类型"""

    SIGN_RESULT = "订阅二重螺旋签到结果"
    SIGN_DNA = "订阅二重螺旋签到"
    MH_SUBSCRIBE = "订阅二重螺旋密函"
    MH_PIC_SUBSCRIBE = "订阅二重螺旋图片密函"
    MH_TEXT_SUBSCRIBE = "订阅二重螺旋文本密函"


BoardcastType = Literal[
    BoardcastTypeEnum.SIGN_RESULT,
    BoardcastTypeEnum.SIGN_DNA,
    BoardcastTypeEnum.MH_SUBSCRIBE,
    BoardcastTypeEnum.MH_PIC_SUBSCRIBE,
    BoardcastTypeEnum.MH_TEXT_SUBSCRIBE,
]
