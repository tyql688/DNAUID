from __future__ import annotations

import io
import sys
import json
import types
import asyncio
import logging
import zipfile
from typing import TypedDict
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
from dna_builder_sdk.data_pack import DATA_PACK_FORMAT_MAJOR  # noqa: E402

from DNAUID.utils.dob import pack  # noqa: E402


class _RemoteVersion(TypedDict):
    version: str
    major: int


def _pack_bytes(version: str, major: int = 2) -> bytes:
    manifest = {"version": version, "major": major, "builtAt": "2026-10-22T00:00:00Z", "modules": {}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(PACK_ZIP) as source, zipfile.ZipFile(buffer, "w") as target:
        for entry in source.infolist():
            content = json.dumps(manifest).encode() if entry.filename == "manifest.json" else source.read(entry)
            target.writestr(entry, content)
    return buffer.getvalue()


class _FakeStore(DataPackStore):
    """远端列表与文件用本地样本，兼容检查、激活和加载走真实 SDK。"""

    def __init__(self, cache_dir: Path, remote: list[_RemoteVersion]) -> None:
        super().__init__(cache_dir=str(cache_dir))
        self.remote = remote
        self.packages = {entry["version"]: _pack_bytes(entry["version"], entry["major"]) for entry in remote}
        self.downloads: list[str] = []

    def _fetch_remote_versions(self) -> list[_RemoteVersion]:
        return self.remote

    def _fetch_to_file(self, url: str, dest: str, progress: object = None) -> None:
        filename = url.rsplit("/", 1)[-1]
        self.downloads.append(filename)
        Path(dest).write_bytes(self.packages[filename.removesuffix(".zip")])


def _use_store(monkeypatch: pytest.MonkeyPatch, cache: Path, remote: list[_RemoteVersion]) -> _FakeStore:
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
    store = _use_store(
        monkeypatch, tmp_path, [{"version": version, "major": 2} for version in ("1.6.208.6", "1.6.208.5")]
    )

    assert asyncio.run(pack.ensure_data_ready()) is None
    assert store.downloads == ["1.6.208.6.zip"]
    assert store.installed_versions() == ["1.6.208.6"]
    changed, _ = pack._sync()
    assert not changed
    assert store.downloads == ["1.6.208.6.zip"]


def test_versions_compare_numerically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for version in ("1.6.208.9", "1.6.208.10"):
        _install(tmp_path, version, _pack_bytes(version))
    store = _use_store(
        monkeypatch, tmp_path, [{"version": version, "major": 2} for version in ("1.6.208.9", "1.6.208.10")]
    )

    assert pack._load_local()
    assert store.active_version == "1.6.208.10"
    changed, _ = pack._sync()
    assert not changed
    assert store.downloads == []


def test_local_unsupported_pack_uses_latest_compatible_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for version in ("1.6.208.9", "1.6.208.10"):
        _install(tmp_path, version, _pack_bytes(version))
    _install(tmp_path, "1.6.208.11", _pack_bytes("1.6.208.11", DATA_PACK_FORMAT_MAJOR + 1))
    store = _use_store(monkeypatch, tmp_path, [])

    assert asyncio.run(pack.ensure_data_ready()) is None
    assert store.active_version == "1.6.208.10"
    assert 1501 in pack.get_tables().char_by_id
    assert store.downloads == []


def test_sync_selects_latest_compatible_remote_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _use_store(
        monkeypatch,
        tmp_path,
        [
            {"version": "1.6.208.11", "major": DATA_PACK_FORMAT_MAJOR + 1},
            {"version": "1.6.208.9", "major": 2},
            {"version": "1.6.208.10", "major": 2},
        ],
    )

    changed, _ = asyncio.run(pack.sync())
    assert changed
    assert store.active_version == "1.6.208.10"
    assert store.downloads == ["1.6.208.10.zip"]
    assert 1501 in pack.get_tables().char_by_id


def test_incompatible_download_preserves_loaded_pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(tmp_path, "1.6.208.10", _pack_bytes("1.6.208.10"))
    store = _use_store(monkeypatch, tmp_path, [{"version": "1.6.208.11", "major": 2}])
    store.packages["1.6.208.11"] = _pack_bytes("1.6.208.11", DATA_PACK_FORMAT_MAJOR + 1)
    assert asyncio.run(pack.ensure_data_ready()) is None
    tables = pack.get_tables()

    with pytest.raises(pack.DobPackError, match="需要更新 SDK"):
        asyncio.run(pack.sync())

    assert store.active_version == "1.6.208.10"
    assert pack.get_tables() is tables
    assert "1.6.208.10" in pack.source_line()
    assert (tmp_path / "1.6.208.10" / "package.zip").is_file()


@pytest.mark.parametrize("remote", [[], [{"version": "1.6.208.11", "major": DATA_PACK_FORMAT_MAJOR + 1}]])
def test_no_compatible_remote_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: list[_RemoteVersion]
) -> None:
    store = _use_store(monkeypatch, tmp_path, remote)

    assert asyncio.run(pack.ensure_data_ready()) == "DOB 数据包初始化失败：远端没有兼容的数据包，请更新 DNAUID 后重试"
    assert store.downloads == []
