from __future__ import annotations

from typing import Literal

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.database.models import DNABind, DNAPrivacy, DNAGroupPrivacy

PrivacyField = Literal["allow_peek", "uid_hidden"]

# 群已强制开启 / 强制关闭该项时，个人设置被锁定的提示
_FORCE_LOCKED_MSG: dict[PrivacyField, tuple[str, str]] = {
    "allow_peek": ("当前群已开启全体允许被查看，无法修改个人设置", "当前群已开启全体防偷窥，无法修改个人设置"),
    "uid_hidden": ("当前群已开启全体隐藏UID，无法修改个人设置", "当前群已开启全体显示UID，无法修改个人设置"),
}


async def _group_force_locked(group_id: str, bot_id: str, field: PrivacyField) -> str | None:
    group_privacy = await DNAGroupPrivacy.get_group_privacy(group_id, bot_id)
    if group_privacy is None:
        return None
    force = group_privacy.force_allow_peek if field == "allow_peek" else group_privacy.force_uid_hidden
    if force is None:
        return None
    enabled_msg, disabled_msg = _FORCE_LOCKED_MSG[field]
    return enabled_msg if force else disabled_msg


async def _save_privacy(user_id: str, bot_id: str, field: PrivacyField, value: bool) -> None:
    if field == "allow_peek":
        await DNAPrivacy.set_privacy_setting(user_id=user_id, bot_id=bot_id, allow_peek=value)
    else:
        await DNAPrivacy.set_privacy_setting(user_id=user_id, bot_id=bot_id, uid_hidden=value)


async def set_personal_privacy(bot: Bot, ev: Event, field: PrivacyField, value: bool, done_msg: str) -> None:
    if ev.group_id:
        locked = await _group_force_locked(ev.group_id, ev.bot_id, field)
        if locked:
            await bot.send(locked)
            return
    await _save_privacy(ev.user_id, ev.bot_id, field, value)
    await bot.send(done_msg)


async def set_member_privacy(
    bot: Bot,
    ev: Event,
    field: PrivacyField,
    value: bool,
    *,
    need_at_msg: str,
    done_msg: str,
) -> None:
    if not ev.group_id:
        await bot.send("请在群聊中使用此命令")
        return
    locked = await _group_force_locked(ev.group_id, ev.bot_id, field)
    if locked:
        await bot.send(locked)
        return
    if not ev.at:
        await bot.send(need_at_msg)
        return
    if not await DNABind.get_uid_by_game(ev.at, ev.bot_id):
        await bot.send("该用户未绑定UID")
        return
    await _save_privacy(ev.at, ev.bot_id, field, value)
    await bot.send(done_msg)


async def set_group_force(bot: Bot, ev: Event, field: PrivacyField, value: bool | None, done_msg: str) -> None:
    if not ev.group_id:
        await bot.send("请在群聊中使用此命令")
        return
    force_field = "force_allow_peek" if field == "allow_peek" else "force_uid_hidden"
    await DNAGroupPrivacy.set_group_force_privacy(ev.group_id, ev.bot_id, force_field, value)
    await bot.send(done_msg)
