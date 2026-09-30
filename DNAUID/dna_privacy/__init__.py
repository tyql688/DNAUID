from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .privacy import set_group_force, set_member_privacy, set_personal_privacy

# 个人隐私控制 (pm=6 普通用户)
sv_dna_privacy = SV("DNA隐私控制", pm=6)
# 群管理员隐私控制 (pm=3 群管理员)
sv_dna_privacy_admin = SV("DNA群隐私控制", pm=3)


@sv_dna_privacy.on_fullmatch(("开偷窥", "关闭偷窥防护"))
async def _enable_peek_personal(bot: Bot, ev: Event) -> None:
    await set_personal_privacy(bot, ev, "allow_peek", True, "已允许他人查看你的游戏信息~")


@sv_dna_privacy.on_fullmatch(("防偷窥", "开启偷窥防护"))
async def _disable_peek_personal(bot: Bot, ev: Event) -> None:
    await set_personal_privacy(bot, ev, "allow_peek", False, "已禁止他人查看你的游戏信息~")


@sv_dna_privacy_admin.on_fullmatch("指定开偷窥")
async def _enable_peek_admin(bot: Bot, ev: Event) -> None:
    await set_member_privacy(
        bot,
        ev,
        "allow_peek",
        True,
        need_at_msg="请@要允许被查看的玩家",
        done_msg="已允许该用户被他人查看游戏信息~",
    )


@sv_dna_privacy_admin.on_fullmatch("指定防偷窥")
async def _disable_peek_admin(bot: Bot, ev: Event) -> None:
    await set_member_privacy(
        bot,
        ev,
        "allow_peek",
        False,
        need_at_msg="请@要禁止被查看的玩家",
        done_msg="已禁止该用户被他人查看游戏信息~",
    )


@sv_dna_privacy_admin.on_fullmatch("全体开偷窥")
async def _enable_peek_all(bot: Bot, ev: Event) -> None:
    await set_group_force(bot, ev, "allow_peek", True, "已开启全体允许查看模式，群内所有玩家均可被查看游戏信息~")


@sv_dna_privacy_admin.on_fullmatch("全体防偷窥")
async def _disable_peek_all(bot: Bot, ev: Event) -> None:
    await set_group_force(bot, ev, "allow_peek", False, "已开启全体禁止查看模式，群内所有玩家均无法被他人查看游戏信息~")


@sv_dna_privacy_admin.on_fullmatch("取消全体偷窥")
async def _cancel_peek_all(bot: Bot, ev: Event) -> None:
    await set_group_force(bot, ev, "allow_peek", None, "已取消全体查看权限设置，恢复个人设置~")


@sv_dna_privacy.on_fullmatch(("隐藏UID", "隐藏uid"))
async def _enable_uid_hidden(bot: Bot, ev: Event) -> None:
    await set_personal_privacy(bot, ev, "uid_hidden", True, "已隐藏你的UID，其他人将无法查看~")


@sv_dna_privacy.on_fullmatch(("显示UID", "显示uid"))
async def _disable_uid_hidden(bot: Bot, ev: Event) -> None:
    await set_personal_privacy(bot, ev, "uid_hidden", False, "已显示你的UID，其他人现在可以查看~")


@sv_dna_privacy_admin.on_fullmatch("指定隐藏UID")
async def _enable_uid_hidden_admin(bot: Bot, ev: Event) -> None:
    await set_member_privacy(
        bot, ev, "uid_hidden", True, need_at_msg="请@要隐藏UID的玩家", done_msg="已为该用户隐藏UID~"
    )


@sv_dna_privacy_admin.on_fullmatch("指定显示UID")
async def _disable_uid_hidden_admin(bot: Bot, ev: Event) -> None:
    await set_member_privacy(
        bot, ev, "uid_hidden", False, need_at_msg="请@要显示UID的玩家", done_msg="已为该用户显示UID~"
    )


@sv_dna_privacy_admin.on_fullmatch("全体隐藏UID")
async def _enable_uid_hidden_all(bot: Bot, ev: Event) -> None:
    await set_group_force(bot, ev, "uid_hidden", True, "已开启全体隐藏UID模式，群内所有玩家的UID将被隐藏~")


@sv_dna_privacy_admin.on_fullmatch("全体显示UID")
async def _disable_uid_hidden_all(bot: Bot, ev: Event) -> None:
    await set_group_force(bot, ev, "uid_hidden", False, "已开启全体显示UID模式，群内所有玩家的UID将被显示~")


@sv_dna_privacy_admin.on_fullmatch("取消全体UID隐藏")
async def _cancel_uid_hidden_all(bot: Bot, ev: Event) -> None:
    await set_group_force(bot, ev, "uid_hidden", None, "已取消全体UID显示设置，恢复个人设置~")
