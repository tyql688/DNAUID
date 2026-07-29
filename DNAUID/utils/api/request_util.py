import copy
from enum import IntEnum
from typing import Union, Generic, TypeVar, Optional

from pydantic import Field, BaseModel, ConfigDict, computed_field

CONTENT_TYPE = "application/x-www-form-urlencoded; charset=utf-8"

ios_base_header = {
    "version": "1.2.0",
    "source": "ios",
    "Content-Type": CONTENT_TYPE,
    "User-Agent": "DoubleHelix/3 CFNetwork/3860.300.31 Darwin/25.3.0",
}

android_base_header = {
    "version": "1.3.2",
    "source": "android",
    "Content-Type": CONTENT_TYPE,
    "User-Agent": "okhttp/3.10.0",
}


h5_base_header = {
    "version": "3.11.1",
    "source": "h5",
    "Content-Type": CONTENT_TYPE,
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}

WEB_LOGIN_BASE_HEADER = {
    "version": "3.11.1",
    "source": "h5",
    "Content-Type": "application/x-www-form-urlencoded;",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"
    ),
}

DAMAGE_BASE_HEADER = {
    "accept": "application/json",
    "content-type": "application/json;charset=UTF-8",
    "source": "h5",
    "version": "3.11.1",
    "origin": "https://dnabbs.yingxiong.com",
    "referer": "https://dnabbs.yingxiong.com/",
}


async def get_base_header(
    dev_code: Optional[str] = None,
    is_need_origin: bool = False,
    is_need_refer: bool = False,
    is_h5: bool = False,
    token: Optional[str] = None,
):
    """默认获取ios头"""
    header = copy.deepcopy(h5_base_header if is_h5 else android_base_header)
    if dev_code:
        header["devCode"] = dev_code
    if is_need_origin:
        header["origin"] = "https://dnabbs.yingxiong.com"
    if is_need_refer:
        header["refer"] = "https://dnabbs.yingxiong.com/"
    if token:
        header["token"] = token
    return header


def get_web_login_header(
    dev_code: str,
    token: str | None = None,
) -> dict[str, str]:
    header = copy.deepcopy(WEB_LOGIN_BASE_HEADER)
    header["devCode"] = dev_code
    header["Origin"] = "https://dnabbs.yingxiong.com"
    header["Referer"] = "https://dnabbs.yingxiong.com/"
    if token is not None:
        header["token"] = token
    return header


def get_damage_header(token: str) -> dict[str, str]:
    header = copy.deepcopy(DAMAGE_BASE_HEADER)
    header["token"] = token
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
