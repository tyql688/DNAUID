from __future__ import annotations

import uuid
import base64
import secrets
from enum import StrEnum
from typing import TYPE_CHECKING
from binascii import Error as BinasciiError
from dataclasses import dataclass

from pydantic import ValidationError

from .model import DNATokenPayload

if TYPE_CHECKING:
    from ..database.models import DNAUser


class LoginChannel(StrEnum):
    APP = "app"
    WEB = "web"


class DNACapability(StrEnum):
    ROLE_CARD = "role_card"
    ACCOUNT_QUERY = "account_query"
    ACCOUNT_ACTION = "account_action"
    DAMAGE_CALCULATION = "damage_calculation"


_CAPABILITY_CHANNELS = {
    DNACapability.ROLE_CARD: (LoginChannel.APP, LoginChannel.WEB),
    DNACapability.ACCOUNT_QUERY: (LoginChannel.APP,),
    DNACapability.ACCOUNT_ACTION: (LoginChannel.APP,),
    DNACapability.DAMAGE_CALCULATION: (LoginChannel.WEB,),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class LoginCredentials:
    channel: LoginChannel
    token: str
    dev_code: str
    d_num: str = ""
    refresh_token: str = ""

    def __post_init__(self) -> None:
        token = self.token.strip()
        dev_code = self.dev_code.strip()
        if token == "":
            raise ValueError("token 不能为空")
        if dev_code == "":
            raise ValueError("devCode 不能为空")
        object.__setattr__(self, "token", token)
        object.__setattr__(self, "dev_code", dev_code)


def get_channel_credentials(
    dna_user: DNAUser,
    channel: LoginChannel,
) -> LoginCredentials | None:
    if channel is LoginChannel.APP:
        if dna_user.cookie == "" or dna_user.dev_code == "" or dna_user.status == "无效":
            return None
        return LoginCredentials(
            channel=channel,
            token=dna_user.cookie,
            dev_code=dna_user.dev_code,
            d_num=dna_user.d_num,
            refresh_token=dna_user.refresh_token,
        )

    if dna_user.web_token == "" or dna_user.web_dev_code == "" or dna_user.web_status == "无效":
        return None
    return LoginCredentials(
        channel=channel,
        token=dna_user.web_token,
        dev_code=dna_user.web_dev_code,
        d_num=dna_user.web_d_num,
        refresh_token=dna_user.web_refresh_token,
    )


def get_capability_credentials(
    dna_user: DNAUser,
    capability: DNACapability,
) -> LoginCredentials | None:
    for channel in _CAPABILITY_CHANNELS[capability]:
        credentials = get_channel_credentials(dna_user, channel)
        if credentials is not None:
            return credentials
    return None


def create_device_code(channel: LoginChannel) -> str:
    if channel is LoginChannel.APP:
        return str(uuid.uuid4()).upper()
    return secrets.token_hex(32)


def get_token_user_id(token: str) -> str | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None

    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        token_payload = DNATokenPayload.model_validate_json(
            base64.urlsafe_b64decode(payload),
        )
    except (BinasciiError, ValidationError, ValueError):
        return None
    return str(token_payload.userId)
