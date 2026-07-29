from __future__ import annotations

import asyncio
from pathlib import Path

import async_timeout
from pydantic import Field, BaseModel
from starlette.responses import HTMLResponse

from gsuid_core.bot import Bot
from gsuid_core.config import core_config
from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.segment import MessageSegment
from gsuid_core.web_app import app
from gsuid_core.utils.cookie_manager.qrlogin import get_qrcode_base64

from ..utils import TimedCache, dna_api, get_public_ip
from .transport import TransportError, build_transport
from .login_helps import (
    get_token,
    is_validate_code,
    is_valid_chinese_phone_number,
)
from .login_service import DNALoginService
from ..utils.api.auth import (
    LoginChannel,
    LoginCredentials,
    create_device_code,
)
from ..utils.msgs.notify import (
    send_dna_notify,
    dna_login_timeout,
    dna_code_login_fail,
)
from ..dna_config.dna_config import DNAConfig
from ..utils.resource.RESOURCE_PATH import DNA_TEMPLATES

cache = TimedCache(timeout=600, maxsize=10)


class LoginSubmission(BaseModel):
    channel: LoginChannel = Field(description="登录来源")
    mobile: str = Field(description="登录手机号")
    code: str = Field(description="短信验证码")
    dev_code: str | None = Field(default=None, description="登录设备码")


class LoginSession(BaseModel):
    auth: str = Field(description="登录会话标识")
    user_id: str = Field(description="机器人用户标识")
    web_dev_code: str | None = Field(default=None, description="Web 设备码")
    web_mobile: str | None = Field(default=None, description="已成功发码的手机号")
    submission: LoginSubmission | None = Field(default=None, description="待处理的登录提交")


class LoginSubmitParams(BaseModel):
    auth: str = Field(description="登录会话标识")
    mobile: str = Field(description="登录手机号")
    code: str = Field(description="短信验证码")


class WebSmsCodeParams(BaseModel):
    auth: str = Field(description="登录会话标识")
    mobile: str = Field(description="接收验证码的手机号")
    v_json: str = Field(alias="vJson", description="CAPTCHA 验证结果")


async def page_login(bot: Bot, ev: Event) -> None:
    transport_name = DNAConfig.get_config("DNALoginTransport").data.strip()
    if transport_name in {"", "local"}:
        await page_login_local(bot, ev, await get_dna_login_url())
        return

    base_url = DNAConfig.get_config("DNALoginUrl").data.strip()
    if base_url == "":
        logger.warning(f"[DNA登录] 接入方式为 {transport_name} 但 DNALoginUrl 未配置")
        await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")
        return
    await page_login_other(bot, ev, base_url)


async def token_login(bot: Bot, ev: Event, token: str) -> None:
    login_service = DNALoginService(bot, ev)
    login_result = await login_service.dna_login_by_token(token=token.strip())
    await send_dna_notify(bot, ev, login_result)


async def get_cookie(bot: Bot, ev: Event) -> str:
    login_service = DNALoginService(bot, ev)
    return await login_service.get_cookie()


async def get_dna_login_url() -> str:
    url = DNAConfig.get_config("DNALoginUrl").data.strip()
    if url != "":
        if url.startswith("http"):
            return url
        return f"https://{url}"

    host = core_config.get_config("HOST")
    port = core_config.get_config("PORT")
    if host == "localhost" or host == "127.0.0.1":
        public_host = "localhost"
    else:
        public_host = await get_public_ip(host)
    return f"http://{public_host}:{port}"


async def send_login(bot: Bot, ev: Event, url: str) -> None:
    at_sender = bool(ev.group_id)
    if DNAConfig.get_config("DNAQRLogin").data:
        path = Path(__file__).parent / f"{ev.user_id}.gif"
        qr_items: list[Message] = [
            MessageSegment.text(f"[二重螺旋] 您的id为【{ev.user_id}】\n"),
            MessageSegment.text("请扫描下方二维码获取登录地址，并复制地址到浏览器打开\n"),
            MessageSegment.image(await get_qrcode_base64(url, path, ev.bot_id)),
        ]

        if DNAConfig.get_config("DNALoginForward").data:
            if not ev.group_id and ev.bot_id == "onebot":
                await bot.send(qr_items)
            else:
                await bot.send(MessageSegment.node(qr_items))
        else:
            await bot.send(qr_items, at_sender=at_sender)

        if path.exists():
            path.unlink()
        return

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
            await bot.send("\n".join(lines))
        else:
            await bot.send(MessageSegment.node(lines))
    else:
        await bot.send("\n".join(lines), at_sender=at_sender)


async def page_login_other(bot: Bot, ev: Event, url: str) -> None:
    auth_token = get_token(ev.user_id)
    transport = build_transport(url)
    try:
        page_url = await transport.start(
            auth=auth_token,
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            group_id=ev.group_id,
        )
    except TransportError as error:
        logger.warning(f"[DNA登录] 外置 start 失败 user_id={ev.user_id}: {error}")
        await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")
        return

    await send_login(bot, ev, page_url)
    if cache.get(auth_token):
        return
    cache.set(auth_token, True)
    try:
        result = await transport.listen(auth_token)
    except TransportError as error:
        logger.warning(f"[DNA登录] 外置 listen 失败 user_id={ev.user_id}: {error}")
        await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")
        return
    finally:
        cache.delete(auth_token)

    if result is None or result.status == "expired":
        await dna_login_timeout(bot, ev)
        return
    if result.status != "success":
        message = result.msg
        if message == "":
            message = "登录失败"
        await send_dna_notify(bot, ev, message)
        return
    token = result.token.strip()
    dev_code = result.dev_code.strip()
    if token == "" or dev_code == "":
        logger.warning(f"[DNA登录] 外置返回成功但凭据为空 user_id={ev.user_id}")
        await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")
        return

    credentials = LoginCredentials(
        channel=result.channel,
        token=token,
        dev_code=dev_code,
        refresh_token=result.refresh_token,
        d_num=result.d_num,
    )
    login_service = DNALoginService(bot, ev)
    login_result = await login_service.login_with_credentials(credentials)
    await send_dna_notify(bot, ev, login_result)


async def page_login_local(bot: Bot, ev: Event, url: str) -> None:
    login_auth = get_token(ev.user_id)
    active_session = cache.get(login_auth)
    if isinstance(active_session, LoginSession):
        await send_login(bot, ev, f"{url}/dna/i/{login_auth}")
        return

    session = LoginSession(auth=login_auth, user_id=ev.user_id)
    cache.set(login_auth, session)
    await send_login(bot, ev, f"{url}/dna/i/{login_auth}")
    try:
        async with async_timeout.timeout(600):
            while True:
                current_session = cache.get(login_auth)
                if current_session is None:
                    await dna_login_timeout(bot, ev)
                    return
                if not isinstance(current_session, LoginSession):
                    raise TypeError("登录会话类型错误")
                if current_session.submission is not None:
                    cache.delete(login_auth)
                    submission = current_session.submission
                    await code_login(
                        bot,
                        ev,
                        f"{submission.mobile},{submission.code}",
                        is_page=True,
                        channel=submission.channel,
                        dev_code=submission.dev_code,
                    )
                    return
                await asyncio.sleep(3)
    except asyncio.TimeoutError:
        cache.delete(login_auth)
        await dna_login_timeout(bot, ev)
    except TypeError as error:
        cache.delete(login_auth)
        logger.error(f"[DNA登录] user_id={ev.user_id}: {error}")
        await send_dna_notify(bot, ev, "登录服务请求失败! 请稍后再试")


async def code_login(
    bot: Bot,
    ev: Event,
    text: str,
    *,
    is_page: bool = False,
    channel: LoginChannel = LoginChannel.APP,
    dev_code: str | None = None,
) -> None:
    try:
        phone_number, code = text.split(",")
        if not is_valid_chinese_phone_number(phone_number):
            raise ValueError("无效手机号")
        if not is_validate_code(code):
            raise ValueError("无效验证码")
    except ValueError:
        if is_page:
            await send_dna_notify(bot, ev, "无效手机号或验证码")
        else:
            await dna_code_login_fail(bot, ev)
        return

    login_service = DNALoginService(bot, ev)
    login_result = await login_service.login(
        channel=channel,
        mobile=phone_number,
        code=code,
        dev_code=dev_code,
    )
    await send_dna_notify(bot, ev, login_result)


async def _render_login_page(
    auth: str,
    template_name: str,
    login_mode: LoginChannel,
) -> HTMLResponse:
    login_session = cache.get(auth)
    if not isinstance(login_session, LoginSession):
        template = DNA_TEMPLATES.get_template("404.html.j2")
        return HTMLResponse(template.render())

    server_url = await get_dna_login_url()
    template = DNA_TEMPLATES.get_template(template_name)
    return HTMLResponse(
        template.render(
            server_url=server_url,
            auth=auth,
            userId=login_session.user_id,
            login_mode=login_mode.value,
            app_login_url=f"{server_url}/dna/i/{auth}",
            web_login_url=f"{server_url}/dna/web/{auth}",
        )
    )


@app.get("/dna/i/{auth}")
async def dna_login_index(auth: str) -> HTMLResponse:
    return await _render_login_page(
        auth,
        "index.html.j2",
        LoginChannel.APP,
    )


@app.get("/dna/web/{auth}")
async def dna_web_login_index(auth: str) -> HTMLResponse:
    return await _render_login_page(
        auth,
        "web_login.html.j2",
        LoginChannel.WEB,
    )


async def _submit_login(
    data: LoginSubmitParams,
    channel: LoginChannel,
) -> dict[str, bool | str]:
    login_session = cache.get(data.auth)
    if not isinstance(login_session, LoginSession):
        return {"success": False, "msg": "登录超时"}
    if not is_valid_chinese_phone_number(data.mobile):
        return {"success": False, "msg": "无效手机号或验证码"}
    if not is_validate_code(data.code):
        return {"success": False, "msg": "无效手机号或验证码"}

    dev_code: str | None = None
    if channel is LoginChannel.WEB:
        dev_code = login_session.web_dev_code
        if dev_code is None or login_session.web_mobile != data.mobile:
            return {
                "success": False,
                "msg": "请先为该手机号获取验证码",
            }

    submission = LoginSubmission(
        channel=channel,
        mobile=data.mobile,
        code=data.code,
        dev_code=dev_code,
    )
    cache.set(
        data.auth,
        login_session.model_copy(update={"submission": submission}),
    )
    return {"success": True}


@app.post("/dna/login")
async def dna_login(data: LoginSubmitParams) -> dict[str, bool | str]:
    return await _submit_login(data, LoginChannel.APP)


@app.post("/dna/web/login")
async def dna_web_login(data: LoginSubmitParams) -> dict[str, bool | str]:
    return await _submit_login(data, LoginChannel.WEB)


@app.post("/dna/web/getSmsCode")
async def dna_web_get_sms_code(
    data: WebSmsCodeParams,
) -> dict[str, bool | str]:
    login_session = cache.get(data.auth)
    if not isinstance(login_session, LoginSession):
        return {"success": False, "msg": "登录超时"}
    if not is_valid_chinese_phone_number(data.mobile):
        return {"success": False, "msg": "无效手机号"}

    dev_code = login_session.web_dev_code
    if dev_code is None:
        dev_code = create_device_code(LoginChannel.WEB)
        login_session = login_session.model_copy(update={"web_dev_code": dev_code})
        cache.set(data.auth, login_session)

    result = await dna_api.get_web_sms_code(
        data.mobile,
        data.v_json,
        dev_code,
    )
    if result.is_success:
        current_session = cache.get(data.auth)
        if not isinstance(current_session, LoginSession):
            return {"success": False, "msg": "登录超时"}
        cache.set(
            data.auth,
            current_session.model_copy(update={"web_mobile": data.mobile}),
        )
        return {"success": True, "msg": "验证码已发送"}
    return {"success": False, "msg": result.throw_msg()}
