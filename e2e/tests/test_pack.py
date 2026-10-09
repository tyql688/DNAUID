from __future__ import annotations

import sys
import types
import shutil
import asyncio
import logging
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "e2e" / "fixtures" / "settlement"
PACK_ZIP = FIX / "1.6.208.6" / "package.zip"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _stub_module(name: str, **attrs: object) -> None:
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module


# CI 只装插件依赖、没有宿主：补最小桩；mock 宿主已装时沿用宿主的
_stub_module("gsuid_core", __path__=[])
_stub_module("gsuid_core.logger", logger=logging.getLogger("dnauid-pack"))
_stub_module("gsuid_core.sv", Plugins=lambda **_kwargs: None)
_stub_module("DNAUID.utils.resource.RESOURCE_PATH", DOB_PATH=FIX)

from dna_builder_sdk import DataPackStore  # noqa: E402

from DNAUID.utils.dob import pack  # noqa: E402


class _FakeStore(DataPackStore):
    """远端换成固定的版本列表，下载换成拷贝测试包，其余走 SDK 原逻辑。"""

    def __init__(self, cache_dir: Path, remote: list[str]) -> None:
        super().__init__(cache_dir=str(cache_dir))
        self.remote = remote
        self.downloads: list[str] = []

    def remote_versions(self) -> list[dict[str, str]]:
        return [{"version": version} for version in self.remote]

    def _fetch_to_file(self, url: str, dest: str, progress: object = None) -> None:
        self.downloads.append(url.rsplit("/", 1)[-1])
        shutil.copyfile(PACK_ZIP, dest)


def _use_store(monkeypatch: pytest.MonkeyPatch, cache: Path, remote: list[str]) -> _FakeStore:
    store = _FakeStore(cache, remote)
    monkeypatch.setattr(pack, "_store", store)
    monkeypatch.setattr(pack, "_tables", None)
    return store


def _install(cache: Path, version: str, data: bytes) -> None:
    (cache / version).mkdir(parents=True)
    (cache / version / "package.zip").write_bytes(data)


def test_broken_local_pack_is_redownloaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = PACK_ZIP.read_bytes()
    _install(tmp_path, "1.6.208.5", data)
    # 下载中断留下的半截包
    _install(tmp_path, "1.6.208.6", data[: len(data) // 2])
    store = _use_store(monkeypatch, tmp_path, ["1.6.208.6", "1.6.208.5"])

    assert asyncio.run(pack.ensure_data_ready()) is None
    assert store.downloads == ["1.6.208.6.zip"]
    assert store.installed_versions() == ["1.6.208.6"]
    changed, _ = pack._sync()
    assert not changed
    assert store.downloads == ["1.6.208.6.zip"]


def test_versions_compare_numerically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for version in ("1.6.208.9", "1.6.208.10"):
        _install(tmp_path, version, PACK_ZIP.read_bytes())
    store = _use_store(monkeypatch, tmp_path, ["1.6.208.9", "1.6.208.10"])

    assert pack._load_local()
    assert store.active_version == "1.6.208.10"
    changed, _ = pack._sync()
    assert not changed
    assert store.downloads == []


def test_empty_remote_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_store(monkeypatch, tmp_path, [])

    assert asyncio.run(pack.ensure_data_ready()) == "DOB 数据包初始化失败：数据包版本列表为空"
