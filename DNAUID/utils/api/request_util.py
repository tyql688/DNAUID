import copy
from enum import IntEnum
from typing import Generic, Optional, TypeVar, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
)

CONTENT_TYPE = "application/x-www-form-urlencoded; charset=utf-8"

ios_base_header = {
    "version": "1.1.2",
    "source": "ios",
    "Content-Type": CONTENT_TYPE,
    "User-Agent": "DoubleHelix/4 CFNetwork/3860.100.1 Darwin/25.0.0",
}

h5_base_header = {
    "version": "3.11.0",
    "source": "h5",
    "Content-Type": CONTENT_TYPE,
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
}


async def get_base_header(
    dev_code: Optional[str] = None,
    is_need_origin: bool = False,
    is_need_refer: bool = False,
    is_h5: bool = False,
):
    """默认获取ios头"""
    header = copy.deepcopy(h5_base_header if is_h5 else ios_base_header)
    if dev_code:
        header["devCode"] = dev_code
    if is_need_origin:
        header["origin"] = "https://dnabbs.yingxiong.com"
    if is_need_refer:
        header["refer"] = "https://dnabbs.yingxiong.com/"
    return header


def is_h5(d: Union[str, dict]) -> bool:
    if isinstance(d, str):
        return d.lower() == "h5"
    if isinstance(d, dict):
        return d.get("source", "").lower() == "h5"
    return False


T = TypeVar("T")


class ThrowMsg(str):
    SYSTEM_BUSY = "系统繁忙，请稍后再试"


class RespCode(IntEnum):
    ERROR = -999

    OK_ZERO = 0
    OK_HTTP = 200
    BAD_REQUEST = 400
    SERVER_ERROR = 500


class DNAApiResp(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="ignore")

    code: int = Field(0, description="状态码")
    msg: str = Field("", description="消息")
    success: bool = Field(False, description="是否成功")
    data: Optional[T] = Field(None, description="数据")

    @computed_field
    @property
    def is_success(self) -> bool:
        return self.success and self.code in (
            RespCode.OK_ZERO,
            RespCode.OK_HTTP,
        )

    @classmethod
    def ok(
        cls,
        data: Optional[T] = None,
        msg: str = "请求成功",
        code: int = RespCode.OK_ZERO,
    ) -> "DNAApiResp[T]":
        return cls(code=code, msg=msg, data=data, success=True)

    @classmethod
    def err(cls, msg: str, code: int = RespCode.ERROR) -> "DNAApiResp[T]":
        return cls(code=code, msg=msg, data=None, success=False)

    def throw_msg(self) -> str:
        if isinstance(self.msg, str):
            return self.msg
        return ThrowMsg.SYSTEM_BUSY
