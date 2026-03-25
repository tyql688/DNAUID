from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.database.models import DNABind, DNAPrivacy, DNAGroupPrivacy


async def _check_group_force_privacy(group_id: str, bot_id: str) -> str | None:
    """检查群是否有强制隐私设置

    返回:
    - 错误消息: 如果有强制设置且无法修改
    - None: 可以正常修改
    """
    group_privacy = await DNAGroupPrivacy.get_group_privacy(group_id, bot_id)
    if group_privacy is not None and group_privacy.force_allow_peek is not None:
        if group_privacy.force_allow_peek:
            return "当前群已开启全体开偷窥，无法修改个人设置"
        else:
            return "当前群已开启全体防偷窥，无法修改个人设置"
    return None


async def _check_group_force_uid_hidden(group_id: str, bot_id: str) -> str | None:
    """检查群是否有强制UID隐藏设置

    返回:
    - 错误消息: 如果有强制设置且无法修改
    - None: 可以正常修改
    """
    group_privacy = await DNAGroupPrivacy.get_group_privacy(group_id, bot_id)
    if group_privacy is not None and group_privacy.force_uid_hidden is not None:
        if group_privacy.force_uid_hidden:
            return "当前群已开启全体隐藏UID，无法修改个人设置"
        else:
            return "当前群已开启全体显示UID，无法修改个人设置"
    return None


async def enable_peek_personal(bot: Bot, ev: Event) -> None:
    """个人开启偷窥权限 - 允许他人查看自己的游戏信息"""
    # 检查组是否有强制设置
    if ev.group_id:
        error_msg = await _check_group_force_privacy(ev.group_id, ev.bot_id)
        if error_msg:
            return await bot.send(error_msg)

    await DNAPrivacy.set_privacy_setting(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        allow_peek=True,
    )
    await bot.send("已开启偷窥权限，其他人现在可以查看你的游戏信息~")


async def disable_peek_personal(bot: Bot, ev: Event) -> None:
    """个人关闭偷窥权限 - 禁止他人查看自己的游戏信息"""
    # 检查组是否有强制设置
    if ev.group_id:
        error_msg = await _check_group_force_privacy(ev.group_id, ev.bot_id)
        if error_msg:
            return await bot.send(error_msg)

    await DNAPrivacy.set_privacy_setting(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        allow_peek=False,
    )
    await bot.send("已开启防偷窥，其他人将无法查看你的游戏信息~")


async def enable_peek_admin(bot: Bot, ev: Event) -> None:
    """群管理员开启被@玩家的偷窥权限"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    # 检查组是否有强制设置
    error_msg = await _check_group_force_privacy(ev.group_id, ev.bot_id)
    if error_msg:
        return await bot.send(error_msg)

    # 检查是否有@用户
    if not ev.at:
        return await bot.send("请@要开启偷窥权限的玩家")

    target_user_id = ev.at

    # 检查被@用户是否绑定了UID
    uid = await DNABind.get_uid_by_game(target_user_id, ev.bot_id)
    if not uid:
        return await bot.send("该用户未绑定UID")

    await DNAPrivacy.set_privacy_setting(
        user_id=target_user_id,
        bot_id=ev.bot_id,
        allow_peek=True,
    )
    await bot.send("已为用户开启偷窥权限~")


async def disable_peek_admin(bot: Bot, ev: Event) -> None:
    """群管理员关闭被@玩家的偷窥权限"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    # 检查组是否有强制设置
    error_msg = await _check_group_force_privacy(ev.group_id, ev.bot_id)
    if error_msg:
        return await bot.send(error_msg)

    # 检查是否有@用户
    if not ev.at:
        return await bot.send("请@要开启防偷窥的玩家")

    target_user_id = ev.at

    # 检查被@用户是否绑定了UID
    uid = await DNABind.get_uid_by_game(target_user_id, ev.bot_id)
    if not uid:
        return await bot.send("该用户未绑定UID")

    await DNAPrivacy.set_privacy_setting(
        user_id=target_user_id,
        bot_id=ev.bot_id,
        allow_peek=False,
    )
    await bot.send("已为用户开启防偷窥~")


async def enable_peek_all(bot: Bot, ev: Event) -> None:
    """群管理员开启群内所有玩家的偷窥权限（强制模式）"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    await DNAGroupPrivacy.set_group_force_privacy(
        group_id=ev.group_id,
        bot_id=ev.bot_id,
        force_allow_peek=True,
    )
    await bot.send("已开启全体开偷窥模式，群内所有玩家均可被查看游戏信息~")


async def disable_peek_all(bot: Bot, ev: Event) -> None:
    """群管理员关闭群内所有玩家的偷窥权限（强制模式）"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    await DNAGroupPrivacy.set_group_force_privacy(
        group_id=ev.group_id,
        bot_id=ev.bot_id,
        force_allow_peek=False,
    )
    await bot.send("已开启全体防偷窥模式，群内所有玩家均无法被他人查看游戏信息~")


async def cancel_peek_all(bot: Bot, ev: Event) -> None:
    """群管理员取消全体偷窥设置，恢复个人设置"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    await DNAGroupPrivacy.set_group_force_privacy(
        group_id=ev.group_id,
        bot_id=ev.bot_id,
        force_allow_peek=None,
    )
    await bot.send("已取消全体偷窥设置，恢复个人隐私设置~")


# ==================== UID隐藏控制命令 ====================


async def enable_uid_hidden(bot: Bot, ev: Event) -> None:
    """个人开启UID隐藏"""
    # 检查组是否有强制设置
    if ev.group_id:
        error_msg = await _check_group_force_uid_hidden(ev.group_id, ev.bot_id)
        if error_msg:
            return await bot.send(error_msg)

    await DNAPrivacy.set_privacy_setting(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        uid_hidden=True,
    )
    await bot.send("已开启UID隐藏，其他人将无法查看你的UID~")


async def disable_uid_hidden(bot: Bot, ev: Event) -> None:
    """个人关闭UID隐藏"""
    # 检查组是否有强制设置
    if ev.group_id:
        error_msg = await _check_group_force_uid_hidden(ev.group_id, ev.bot_id)
        if error_msg:
            return await bot.send(error_msg)

    await DNAPrivacy.set_privacy_setting(
        user_id=ev.user_id,
        bot_id=ev.bot_id,
        uid_hidden=False,
    )
    await bot.send("已关闭UID隐藏，其他人现在可以查看你的UID~")


async def enable_uid_hidden_admin(bot: Bot, ev: Event) -> None:
    """群管理员开启被@玩家的UID隐藏"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    # 检查组是否有强制设置
    error_msg = await _check_group_force_uid_hidden(ev.group_id, ev.bot_id)
    if error_msg:
        return await bot.send(error_msg)

    # 检查是否有@用户
    if not ev.at:
        return await bot.send("请@要开启UID隐藏的玩家")

    target_user_id = ev.at

    # 检查被@用户是否绑定了UID
    uid = await DNABind.get_uid_by_game(target_user_id, ev.bot_id)
    if not uid:
        return await bot.send("该用户未绑定UID")

    await DNAPrivacy.set_privacy_setting(
        user_id=target_user_id,
        bot_id=ev.bot_id,
        uid_hidden=True,
    )
    await bot.send("已为用户开启UID隐藏~")


async def disable_uid_hidden_admin(bot: Bot, ev: Event) -> None:
    """群管理员关闭被@玩家的UID隐藏"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    # 检查组是否有强制设置
    error_msg = await _check_group_force_uid_hidden(ev.group_id, ev.bot_id)
    if error_msg:
        return await bot.send(error_msg)

    # 检查是否有@用户
    if not ev.at:
        return await bot.send("请@要关闭UID隐藏的玩家")

    target_user_id = ev.at

    # 检查被@用户是否绑定了UID
    uid = await DNABind.get_uid_by_game(target_user_id, ev.bot_id)
    if not uid:
        return await bot.send("该用户未绑定UID")

    await DNAPrivacy.set_privacy_setting(
        user_id=target_user_id,
        bot_id=ev.bot_id,
        uid_hidden=False,
    )
    await bot.send("已为用户关闭UID隐藏~")


async def enable_uid_hidden_all(bot: Bot, ev: Event) -> None:
    """群管理员开启群内所有玩家的UID隐藏（强制模式）"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    await DNAGroupPrivacy.set_group_force_privacy(
        group_id=ev.group_id,
        bot_id=ev.bot_id,
        force_uid_hidden=True,
    )
    await bot.send("已开启全体隐藏UID模式，群内所有玩家的UID将被隐藏~")


async def disable_uid_hidden_all(bot: Bot, ev: Event) -> None:
    """群管理员关闭群内所有玩家的UID隐藏（强制模式）"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    await DNAGroupPrivacy.set_group_force_privacy(
        group_id=ev.group_id,
        bot_id=ev.bot_id,
        force_uid_hidden=False,
    )
    await bot.send("已开启全体显示UID模式，群内所有玩家的UID将被显示~")


async def cancel_uid_hidden_all(bot: Bot, ev: Event) -> None:
    """群管理员取消全体UID隐藏设置，恢复个人设置"""
    if not ev.group_id:
        return await bot.send("请在群聊中使用此命令")

    await DNAGroupPrivacy.set_group_force_privacy(
        group_id=ev.group_id,
        bot_id=ev.bot_id,
        force_uid_hidden=None,
    )
    await bot.send("已取消全体UID隐藏设置，恢复个人UID隐藏设置~")
