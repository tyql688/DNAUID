from __future__ import annotations

import shutil
import asyncio
import zipfile
from pathlib import Path

from dna_builder_sdk import DataPackStore
from dna_builder_sdk.errors import DobApiError
from dna_builder_sdk.calc.gamedata import GameDataTables

from gsuid_core.logger import logger

from ..resource.RESOURCE_PATH import DOB_PATH


class DobPackError(RuntimeError):
    """数据包外部错误（网络 / 落盘 / 包格式），调用方只需 catch 这一种。"""


_store = DataPackStore(cache_dir=str(DOB_PATH))
_tables: GameDataTables | None = None
# 加载与下载都在这把锁下串行、放线程池跑；其余地方只读已加载的表引用
_lock = asyncio.Lock()
# 下载中断会留下半截 zip，读包时报 BadZipFile
_PACK_ERRORS = (DobApiError, zipfile.BadZipFile)


def get_tables() -> GameDataTables:
    """已加载的数据表；入口处须先 await ensure_data_ready()。"""
    if _tables is None:
        raise DobPackError("DOB 数据包尚未加载")
    return _tables


def describe() -> str | None:
    """已加载数据包的版本、打包时间与条目数，未加载返回 None。"""
    manifest = _store.manifest
    if _tables is None or manifest is None:
        return None
    built = manifest["builtAt"][:16].replace("T", " ")
    counts = f"角色 {len(_tables.chars)} / 魔之楔 {len(_tables.mods)} / 武器 {len(_tables.weapons)}"
    return f"v{manifest['version']}（{built} 打包，{counts}）"


def source_line() -> str:
    """出图页脚的数据来源行。"""
    manifest = _store.manifest
    if manifest is None:
        return "Data Source: DNA Builder (DOB)"
    return f"Data Source: DNA Builder (DOB) | Pack Version: {manifest['version']}"


def _version_key(pack_version: str) -> tuple[int, ...]:
    # SDK 按字符串排序，1.6.208.10 会排到 1.6.208.9 前面
    return tuple(int(part) for part in pack_version.split(".") if part.isdigit())


def _load(pack_version: str) -> None:
    global _tables
    try:
        _store.activate(pack_version)
        _tables = _store.load_tables()
    except _PACK_ERRORS as error:
        raise DobPackError(f"DOB 数据包加载失败：{error}") from error


def _load_local() -> bool:
    """加载本地最新的数据包（不联网），本地没有或已损坏返回 False，交给 _sync 重新下载。"""
    if _tables is not None:
        return True
    installed = _store.installed_versions()
    if not installed:
        return False
    try:
        _load(max(installed, key=_version_key))
    except DobPackError as error:
        logger.warning(f"[DNA DOB] 本地数据包不可用，等待重新下载: {error!r}")
        return False
    return True


def _sync() -> tuple[bool, str]:
    try:
        remote = _store.remote_versions()
    except DobApiError as error:
        raise DobPackError(f"数据包版本列表拉取失败：{error}") from error
    if not remote:
        raise DobPackError("数据包版本列表为空")
    latest = max((entry["version"] for entry in remote), key=_version_key)
    # 按实际加载的版本判断：本地同版本的包损坏时会重新下载覆盖
    if _tables is not None and _store.active_version == latest:
        return False, f"DOB 数据包已是最新（v{latest}）"
    try:
        _store.download(latest)
    except _PACK_ERRORS as error:
        raise DobPackError(f"数据包下载失败：{error}") from error
    _load(latest)
    for old in _store.installed_versions():
        if old != latest:
            shutil.rmtree(Path(_store.cache_dir) / old)
    return True, f"DOB 数据包已更新到 {describe()}"


async def sync() -> tuple[bool, str]:
    """检查并下载最新数据包，返回 (是否更新, 提示)。"""
    async with _lock:
        return await asyncio.to_thread(_sync)


async def load_local() -> None:
    """加载本地已有的数据包（不联网）。"""
    async with _lock:
        await asyncio.to_thread(_load_local)


async def check_update(trigger: str) -> None:
    """后台检查更新：失败只记日志，不影响已有数据的使用。"""
    try:
        changed, message = await sync()
    except DobPackError as error:
        logger.warning(f"[DNA DOB] {trigger}失败（不影响使用）: {error!r}")
        return
    if changed:
        logger.info(f"[DNA DOB] {message}（{trigger}）")


async def ensure_data_ready() -> str | None:
    """计算前调用：本地有包直接加载，没有就下载；可用返回 None，否则返回给用户的提示。"""
    if _tables is not None:
        return None
    async with _lock:
        try:
            if not await asyncio.to_thread(_load_local):
                await asyncio.to_thread(_sync)
        except DobPackError as error:
            return f"DOB 数据包初始化失败：{error}"
    return None
