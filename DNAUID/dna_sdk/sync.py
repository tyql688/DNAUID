"""同步层：数据包检查/下载/激活/重载（异步入口，供启动钩子与 bot 命令调用）。

语义沿用旧 dob_pack：本地有包直接用；版本落后则下载替换；全程持锁串行；
外部错误收敛成 SdkPackError 一种。数据目录沿用旧 dob 目录。
"""

from __future__ import annotations

import asyncio

from . import tables
from .tables import SdkPackError, get_tables

__all__ = [
    "SdkPackError",
    "is_data_ready",
    "sync",
    "sync_async",
    "init_if_needed",
    "startup_auto_sync",
    "ensure_data_ready",
]


def is_data_ready() -> bool:
    """本地是否有可用数据包（不联网）。"""
    if not tables.is_ready():
        return False
    try:
        get_tables()
    except SdkPackError:
        return False
    return True


def sync(force: bool = False) -> tuple[bool, str]:
    """检查并同步最新数据包（同步阻塞，调用方应放线程里）。返回 (是否变化, 提示)。"""
    from dna_builder_sdk.errors import DobApiError

    store = tables.datapack_store()
    try:
        remote = store.remote_versions()
    except DobApiError as error:
        raise SdkPackError(f"数据包版本列表拉取失败：{error}") from error
    if not remote:
        return False, "数据包版本列表为空"
    latest = remote[0].get("version") if isinstance(remote[0], dict) else None
    if not latest:
        return False, "数据包版本列表为空"
    local = tables.version()
    if not force and local == latest:
        return False, f"DOB 数据包已是最新（v{local}）"
    try:
        manifest = store.download(latest)
    except DobApiError as error:
        raise SdkPackError(f"数据包下载失败：{error}") from error
    tables.reload_tables()
    counts = tables.counts()
    return True, (
        f"DOB 数据包已更新到 v{manifest.get('version', latest)}"
        f"（角色 {counts['chars']} / 魔之楔 {counts['mods']} / 武器 {counts['weapons']}）"
    )


_update_lock = asyncio.Lock()


async def sync_async(force: bool = False) -> tuple[bool, str]:
    """同步数据包（异步入口）：检查 → 下载 → 重载表，全程持锁串行。"""
    async with _update_lock:
        return await asyncio.to_thread(sync, force)


async def init_if_needed() -> None:
    """首次没有数据时同步等待初始化；有数据时由调用方决定是否后台检查。"""
    if not is_data_ready():
        await sync_async()


def startup_auto_sync() -> None:
    """启动时后台检查更新（周期复查由调度器按配置间隔承担）。"""
    from gsuid_core.logger import logger

    async def _run() -> None:
        try:
            changed, message = await sync_async()
            if changed:
                logger.info(f"[DNA DOB] {message}（启动检查）")
        except SdkPackError as error:
            logger.warning(f"[DNA DOB] 启动检查失败（不影响使用）: {error!r}")

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        from gsuid_core.logger import logger as _logger

        _logger.warning("[DNA DOB] 无运行中的事件循环，跳过启动检查")


async def ensure_data_ready(allow_download: bool = True) -> str | None:
    """确保 DOB 数据可用（面板等入口在计算前调用）。返回 None 表示可用，否则为用户提示。"""
    try:
        get_tables()
        return None
    except SdkPackError:
        pass
    if not allow_download:
        return "DOB 数据包未就绪，请先发送「dna更新数据包」"
    try:
        await sync_async()
    except SdkPackError as error:
        return f"DOB 数据包初始化失败：{error}"
    try:
        get_tables()
    except SdkPackError:
        return "DOB 数据包初始化失败：数据包缺失或内容不完整"
    return None
