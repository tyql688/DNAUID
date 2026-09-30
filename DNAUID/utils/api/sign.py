import uuid
import asyncio
from typing import Any

from .sign_130 import generate_headers_130

# 兜底列表，服务端动态下发时会被覆盖
SIGN_API_LIST = [
    "/user/sdkLogin",
    "/user/getSmsCode",
    "/role/defaultRoleForTool",
    "/media/av/cfg/getVideos",
    "/media/av/cfg/getAudios",
    "/media/av/cfg/getImages",
    "/encourage/signin/signin",
    "/user/refreshToken",
    "/user/signIn",
    "/user/refreshToken",
    "/role/defaultRole",
    "/role/list",
    "/role/getShortNoteInfo",
    "/forum/like",
    "/encourage/calendar/Activity/list",
]


def get_dev_code() -> str:
    return str(uuid.uuid4()).upper()


async def get_signed_headers_and_body(
    url: str,
    header: dict[str, str],
    data: dict[str, Any],
    rsa_public_key: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    # 等 WebSocket 握手（threading.Event）和 RSA 签名都会阻塞，放线程里跑
    return await asyncio.to_thread(_sign_headers_and_body, url, header, data, rsa_public_key)


def _sign_headers_and_body(
    url: str,
    header: dict[str, str],
    data: dict[str, Any],
    rsa_public_key: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    if not any(url.endswith(api) for api in SIGN_API_LIST):
        return header, data

    token = header.get("token", "")
    dev_code = header.get("devCode", "")
    from .ws_manager import get_ws_manager, get_ws_wait_time

    get_ws_manager().get_connection(token, dev_code, wait_ready=True, timeout=get_ws_wait_time())

    return generate_headers_130(header, data, rsa_public_key)
