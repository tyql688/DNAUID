import asyncio
import uuid
from pathlib import Path
from typing import Optional, Union

import async_timeout
from pydantic import BaseModel
from starlette.responses import HTMLResponse

from gsuid_core.bot import Bot
from gsuid_core.config import core_config
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.cookie_manager.qrlogin import get_qrcode_base64
from gsuid_core.web_app import app

from ..dna_config.dna_config import DNAConfig
from ..utils import TimedCache, dna_api, get_public_ip
from ..utils.msgs.notify import (
    dna_code_login_fail,
    dna_login_success,
    dna_login_timeout,
    send_dna_notify,
)
from ..utils.resource.RESOURCE_PATH import DNA_TEMPLATES
from .login_helps import (
    get_token,
    is_valid_chinese_phone_number,
    is_validate_code,
)

cache = TimedCache(timeout=600, maxsize=10)


async def page_login(bot: Bot, ev: Event):
    """网页登录入口"""
    url, is_local = await get_dna_login_url()

    if is_local:
        return await page_login_local(bot, ev, url)
    else:
        raise Exception("二重螺旋暂不支持外置登录")


async def get_dna_login_url() -> tuple[str, bool]:
    """获取网页登录的url

    Returns:
        tuple[str, bool]: url,是否是本地登录
    """
    url = DNAConfig.get_config("DNALoginUrl").data
    if url:
        if not url.startswith("http"):
            url = f"https://{url}"
        return url, DNAConfig.get_config("DNALoginUrlSelf").data
    else:
        HOST = core_config.get_config("HOST")
        PORT = core_config.get_config("PORT")

        if HOST == "localhost" or HOST == "127.0.0.1":
            _host = "localhost"
        else:
            _host = await get_public_ip(HOST)

        return f"http://{_host}:{PORT}", True


async def send_login(bot: Bot, ev: Event, url: str):
    """发送登录信息"""
    at_sender = True if ev.group_id else False

    # 二维码登录
    if DNAConfig.get_config("DNAQRLogin").data:
        path = Path(__file__).parent / f"{ev.user_id}.gif"

        im = [
            f"[二重螺旋] 您的id为【{ev.user_id}】\n",
            "请扫描下方二维码获取登录地址，并复制地址到浏览器打开\n",
            MessageSegment.image(
                await get_qrcode_base64(url, path, ev.bot_id)
            ),
        ]

        if DNAConfig.get_config("DNALoginForward").data:
            if not ev.group_id and ev.bot_id == "onebot":
                # 私聊+onebot 不转发
                await bot.send(im)
            else:
                await bot.send(MessageSegment.node(im))
        else:
            await bot.send(im, at_sender=at_sender)

        if path.exists():
            path.unlink()
    else:
        # 登录
        if DNAConfig.get_config("DNATencentWord").data:
            url = f"https://docs.qq.com/scenario/link.html?url={url}"
        im = [
            f"[二重螺旋] 您的id为【{ev.user_id}】",
            "请复制地址到浏览器打开",
            f" {url}",
            "登录地址10分钟内有效",
        ]

        if DNAConfig.get_config("DNALoginForward").data:
            if not ev.group_id and ev.bot_id == "onebot":
                # 私聊+onebot 不转发
                await bot.send("\n".join(im))
            else:
                await bot.send(MessageSegment.node(im))
        else:
            await bot.send("\n".join(im), at_sender=at_sender)


class LoginParams(BaseModel):
    auth: str
    user_id: str
    mobile: Optional[Union[str, int]] = None
    code: Optional[Union[str, int]] = None


async def page_login_local(bot: Bot, ev: Event, url):
    login_auth = get_token(ev.user_id)
    await send_login(bot, ev, f"{url}/dna/i/{login_auth}")
    result = cache.get(login_auth)
    if isinstance(result, LoginParams):
        return

    # 手机登录
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
                if result.mobile and result.code:
                    cache.delete(login_auth)
                    text = f"{result.mobile},{result.code}"
                    break
                await asyncio.sleep(3)
    except asyncio.TimeoutError:
        return await dna_login_timeout(bot, ev)
    except Exception as e:
        logger.error(e)

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

    dev_code = str(uuid.uuid4()).upper()
    result = await dna_api.login(phone_number, code, dev_code)
    if not result.success:
        return await send_dna_notify(bot, ev, result.throw_msg())

    return await dna_login_success(bot, ev)


@app.get("/dna/i/{auth}")
async def dna_login_index(auth: str):
    login_params: Optional[LoginParams] = cache.get(auth)
    if not login_params or not isinstance(login_params, LoginParams):
        template = DNA_TEMPLATES.get_template("404.html")
        return HTMLResponse(template.render())
    else:
        url, _ = await get_dna_login_url()
        template = DNA_TEMPLATES.get_template("index.html")
        return HTMLResponse(
            template.render(
                server_url=url,
                auth=auth,
                userId=login_params.user_id,
            )
        )


@app.post("/dna/login")
async def dna_login(data: LoginParams):
    if not cache.get(data.auth):
        return {"success": False, "msg": "登录超时"}

    if data.mobile is None or data.code is None:
        return {"success": False, "msg": "手机号或验证码不能为空"}

    cache.set(data.auth, data)
    return {"success": True}
