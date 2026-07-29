from __future__ import annotations

import asyncio
from pathlib import Path

import async_timeout
from pydantic import BaseModel
from starlette.responses import HTMLResponse

from gsuid_core.bot import Bot
from gsuid_core.config import core_config
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment
from gsuid_core.web_app import app
from gsuid_core.utils.cookie_manager.qrlogin import get_qrcode_base64

from ..utils import TimedCache, get_public_ip
from .transport import TransportError, build_transport
from .login_helps import (
    get_token,
    is_validate_code,
    is_valid_chinese_phone_number,
)
from .login_service import DNALoginService
from ..utils.msgs.notify import (
    send_dna_notify,
    dna_login_timeout,
    dna_code_login_fail,
)
from ..dna_config.dna_config import DNAConfig
from ..utils.resource.RESOURCE_PATH import DNA_TEMPLATES

cache = TimedCache(timeout=600, maxsize=10)


async def page_login(bot: Bot, ev: Event):
    """网页登录入口：DNALoginTransport 决定 Core 内嵌登录还是走外置 dna-login 服务。"""
    transport_name = DNAConfig.get_config("DNALoginTransport").data.strip()
    if transport_name in {"", "local"}:
        return await page_login_local(bot, ev, await get_dna_login_url())

    base_url = DNAConfig.get_config("DNALoginUrl").data.strip()
    if not base_url:
        logger.warning(f"[DNA登录] 接入方式为 {transport_name} 但 DNALoginUrl 未配置")
        return await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")
    return await page_login_other(bot, ev, base_url)


async def token_login(bot: Bot, ev: Event, token: str):
    """token登录入口"""
    token = token.strip()
    login_service = DNALoginService(bot, ev)
    login_result = await login_service.dna_login_by_token(
        token=token,
    )
    await send_dna_notify(bot, ev, login_result)


async def get_cookie(bot: Bot, ev: Event):
    login_service = DNALoginService(bot, ev)
    return await login_service.get_cookie()


async def get_dna_login_url() -> str:
    """local 模式登录页对外地址：配了 DNALoginUrl 用它，否则用 Core HOST/PORT 并探测公网 IP。"""
    url = DNAConfig.get_config("DNALoginUrl").data.strip()
    if url:
        return url if url.startswith("http") else f"https://{url}"

    HOST = core_config.get_config("HOST")
    PORT = core_config.get_config("PORT")
    if HOST == "localhost" or HOST == "127.0.0.1":
        _host = "localhost"
    else:
        _host = await get_public_ip(HOST)
    return f"http://{_host}:{PORT}"


async def send_login(bot: Bot, ev: Event, url: str):
    """发送登录信息"""
    at_sender = True if ev.group_id else False

    # 二维码登录
    if DNAConfig.get_config("DNAQRLogin").data:
        path = Path(__file__).parent / f"{ev.user_id}.gif"

        qr_items: list[Message] = [
            MessageSegment.text(f"[二重螺旋] 您的id为【{ev.user_id}】\n"),
            MessageSegment.text("请扫描下方二维码获取登录地址，并复制地址到浏览器打开\n"),
            MessageSegment.image(await get_qrcode_base64(url, path, ev.bot_id)),
        ]

        if DNAConfig.get_config("DNALoginForward").data:
            if not ev.group_id and ev.bot_id == "onebot":
                # 私聊+onebot 不转发
                await bot.send(qr_items)
            else:
                await bot.send(MessageSegment.node(qr_items))
        else:
            await bot.send(qr_items, at_sender=at_sender)

        if path.exists():
            path.unlink()
    else:
        # 登录
        if DNAConfig.get_config("DNATencentWord").data:
            url = f"https://docs.qq.com/scenario/link.html?url={url}"
        lines = [
            f"[二重螺旋] 您的id为【{ev.user_id}】",
            "请复制地址到浏览器打开",
            f" {url}",
            "登录地址10分钟内有效",
        ]

        if DNAConfig.get_config("DNALoginForward").data:
            if not ev.group_id and ev.bot_id == "onebot":
                # 私聊+onebot 不转发
                await bot.send("\n".join(lines))
            else:
                await bot.send(MessageSegment.node(lines))
        else:
            await bot.send("\n".join(lines), at_sender=at_sender)


class LoginParams(BaseModel):
    auth: str
    user_id: str
    mobile: str | None = None
    code: str | None = None


class LoginSubmitParams(BaseModel):
    auth: str
    mobile: str
    code: str


async def page_login_other(bot: Bot, ev: Event, url: str):
    """外置 dna-login 服务登录：start 建会话 → 发链接 → transport 监听终态 → 凭据换角色。"""
    auth_token = get_token(ev.user_id)
    transport = build_transport(url)

    try:
        page_url = await transport.start(
            auth=auth_token,
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            group_id=ev.group_id,
        )
    except TransportError as err:
        logger.warning(f"[DNA登录] 外置 start 失败 user_id={ev.user_id}: {err}")
        return await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")

    await send_login(bot, ev, page_url)

    # 已有进行中的 listen：仅重发链接，不另开监听，否则多个 listen 会竞争同一会话
    if cache.get(auth_token):
        return
    cache.set(auth_token, True)
    try:
        result = await transport.listen(auth_token)
    except TransportError as err:
        logger.warning(f"[DNA登录] 外置 listen 失败 user_id={ev.user_id}: {err}")
        return await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")
    finally:
        cache.delete(auth_token)

    if result is None or result.status == "expired":
        return await dna_login_timeout(bot, ev)
    if result.status != "success":
        return await send_dna_notify(bot, ev, result.msg or "登录失败")
    if not result.token or not result.dev_code:
        logger.warning(f"[DNA登录] 外置返回成功但凭据为空 user_id={ev.user_id}")
        return await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")

    login_service = DNALoginService(bot, ev)
    login_result = await login_service.dna_login_by_token(
        token=result.token,
        dev_code=result.dev_code,
        refresh_token=result.refresh_token,
        d_num=result.d_num,
    )
    await send_dna_notify(bot, ev, login_result)


async def page_login_local(bot: Bot, ev: Event, url):
    login_auth = get_token(ev.user_id)
    await send_login(bot, ev, f"{url}/dna/i/{login_auth}")
    result = cache.get(login_auth)
    if isinstance(result, LoginParams):
        return

    # 手机登录
    text = ""
    login_params = LoginParams(auth=login_auth, user_id=ev.user_id)
    cache.set(login_auth, login_params)
    try:
        async with async_timeout.timeout(600):
            while True:
                result = cache.get(login_auth)
                if result is None:
                    return await dna_login_timeout(bot, ev)
                if not isinstance(result, LoginParams):
                    raise Exception("登录参数错误")
                if result.mobile is not None and result.code is not None:
                    cache.delete(login_auth)
                    text = f"{result.mobile},{result.code}"
                    break
                await asyncio.sleep(3)
    except asyncio.TimeoutError:
        return await dna_login_timeout(bot, ev)
    except Exception as e:
        logger.error(e)
        return await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")

    return await code_login(bot, ev, text, True)


async def code_login(bot: Bot, ev: Event, text: str, isPage=False):
    # 手机+验证码
    try:
        phone_number, code = text.split(",")
        if not is_valid_chinese_phone_number(phone_number):
            raise ValueError("无效手机号")
        if not is_validate_code(code):
            raise ValueError("无效验证码")
    except ValueError as _:
        if not isPage:
            return await dna_code_login_fail(bot, ev)
        else:
            return await send_dna_notify(bot, ev, "无效手机号或验证码")

    login_service = DNALoginService(bot, ev)
    login_result = await login_service.dna_login(mobile=phone_number, code=code)
    await send_dna_notify(bot, ev, login_result)


@app.get("/dna/i/{auth}")
async def dna_login_index(auth: str):
    login_params = cache.get(auth)
    if not isinstance(login_params, LoginParams):
        template = DNA_TEMPLATES.get_template("404.html")
        return HTMLResponse(template.render())

    url = await get_dna_login_url()
    template = DNA_TEMPLATES.get_template("index.html")
    return HTMLResponse(
        template.render(
            server_url=url,
            auth=auth,
            userId=login_params.user_id,
        )
    )


@app.post("/dna/login")
async def dna_login(data: LoginSubmitParams):
    login_params = cache.get(data.auth)
    if not isinstance(login_params, LoginParams):
        return {"success": False, "msg": "登录超时"}

    if not is_valid_chinese_phone_number(data.mobile) or not is_validate_code(data.code):
        return {"success": False, "msg": "无效手机号或验证码"}

    cache.set(
        data.auth,
        login_params.model_copy(
            update={
                "mobile": data.mobile,
                "code": data.code,
            }
        ),
    )
    return {"success": True}
