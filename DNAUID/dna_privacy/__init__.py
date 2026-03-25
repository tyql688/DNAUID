from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .privacy import (
    cancel_peek_all,
    enable_peek_all,
    disable_peek_all,
    enable_peek_admin,
    enable_uid_hidden,
    disable_peek_admin,
    disable_uid_hidden,
    enable_peek_personal,
    cancel_uid_hidden_all,
    disable_peek_personal,
    enable_uid_hidden_all,
    disable_uid_hidden_all,
    enable_uid_hidden_admin,
    disable_uid_hidden_admin,
)

# 个人隐私控制 (pm=6 普通用户)
sv_dna_privacy = SV("DNA隐私控制", pm=6)
# 群管理员隐私控制 (pm=3 群管理员)
sv_dna_privacy_admin = SV("DNA群隐私控制", pm=3)


# region 偷窥权限控制命令


@sv_dna_privacy.on_fullmatch(("开偷窥", "关闭偷窥防护"))
async def _enable_peek_personal(bot: Bot, ev: Event):
    await enable_peek_personal(bot, ev)


@sv_dna_privacy.on_fullmatch(("防偷窥", "开启偷窥防护"))
async def _disable_peek_personal(bot: Bot, ev: Event):
    await disable_peek_personal(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("指定开偷窥")
async def _enable_peek_admin(bot: Bot, ev: Event):
    await enable_peek_admin(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("指定防偷窥")
async def _disable_peek_admin(bot: Bot, ev: Event):
    await disable_peek_admin(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("全体开偷窥")
async def _enable_peek_all(bot: Bot, ev: Event):
    await enable_peek_all(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("全体防偷窥")
async def _disable_peek_all(bot: Bot, ev: Event):
    await disable_peek_all(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("取消全体偷窥")
async def _cancel_peek_all(bot: Bot, ev: Event):
    await cancel_peek_all(bot, ev)


# endregion

# region UID隐藏控制命令


@sv_dna_privacy.on_fullmatch(("隐藏UID", "隐藏uid"))
async def _enable_uid_hidden(bot: Bot, ev: Event):
    await enable_uid_hidden(bot, ev)


@sv_dna_privacy.on_fullmatch(("显示UID", "显示uid"))
async def _disable_uid_hidden(bot: Bot, ev: Event):
    await disable_uid_hidden(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("指定隐藏UID")
async def _enable_uid_hidden_admin(bot: Bot, ev: Event):
    await enable_uid_hidden_admin(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("指定显示UID")
async def _disable_uid_hidden_admin(bot: Bot, ev: Event):
    await disable_uid_hidden_admin(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("全体隐藏UID")
async def _enable_uid_hidden_all(bot: Bot, ev: Event):
    await enable_uid_hidden_all(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("全体显示UID")
async def _disable_uid_hidden_all(bot: Bot, ev: Event):
    await disable_uid_hidden_all(bot, ev)


@sv_dna_privacy_admin.on_fullmatch("取消全体UID隐藏")
async def _cancel_uid_hidden_all(bot: Bot, ev: Event):
    await cancel_uid_hidden_all(bot, ev)


# endregion
