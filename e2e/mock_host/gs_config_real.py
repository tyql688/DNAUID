"""mock 宿主的真实插件配置系统。

语义对齐上游 ``gsuid_core.utils.plugins_config.gs_config.StringConfig``：

- ``StringConfig(title, path, defaults)``，``defaults`` 为
  ``dict[str, GSC]``（GSC 家族走上游真实 ``models.py``，带 ``.data``）。
- ``get_config(key).data``：持久化覆盖值优先，否则默认值。
- ``set_config(key, value)``：写入 JSON 文件，插件的订阅/登录等写入链路真实生效。
- ``pic_gen_config`` / ``database_config``：core 侧配置的最小真实实现。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


class StringConfig:
    def __init__(self, title: str, path: str | Path, default: dict[str, Any]) -> None:
        self.title = title
        self.path = Path(path)
        self.default = default
        self._overrides: dict[str, Any] = self._read()

    # -- 持久化 ---------------------------------------------------------
    def _read(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (ValueError, OSError):
            pass
        return {}

    def _write(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._overrides, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # -- 读写 -----------------------------------------------------------
    def _merged_item(self, key: str) -> Any:
        if key not in self.default:
            raise KeyError(f"[{self.title}] 未知配置项：{key}")
        item = copy.deepcopy(self.default[key])
        if key in self._overrides:
            try:
                item.data = self._overrides[key]
            except (AttributeError, TypeError):
                pass
        return item

    def get_config(self, key: str) -> Any:
        return self._merged_item(key)

    def set_config(self, key: str, value: Any) -> None:
        if key not in self.default:
            raise KeyError(f"[{self.title}] 未知配置项：{key}")
        self._overrides[key] = value
        self._write()

    def get_all(self) -> dict[str, Any]:
        return {k: self._merged_item(k) for k in self.default}

    def config_path(self) -> str:
        return str(self.path)


def make_pic_gen_config(config_dir: Path) -> StringConfig:
    from gsuid_core.utils.plugins_config.models import GsIntConfig  # type: ignore[import-not-found]

    return StringConfig(
        "PicGen",
        config_dir / "pic_gen.json",
        {"PicQuality": GsIntConfig("图片质量", "帮助图等 JPEG 输出质量", 85, 100)},
    )


def make_database_config(config_dir: Path) -> StringConfig:
    from gsuid_core.utils.plugins_config.models import (  # type: ignore[import-not-found]
        GsBoolConfig,
        GsIntConfig,
        GsStrConfig,
    )

    return StringConfig(
        "DataBase",
        config_dir / "database.json",
        {
            "db_host": GsStrConfig("数据库地址", "数据库地址", "127.0.0.1"),
            "db_port": GsStrConfig("数据库端口", "数据库端口", ""),
            "db_user": GsStrConfig("数据库用户", "数据库用户", ""),
            "db_password": GsStrConfig("数据库密码", "数据库密码", ""),
            "db_name": GsStrConfig("数据库名", "数据库名", ""),
            "db_pool_size": GsIntConfig("连接池", "连接池", 5, 50),
            "db_echo": GsBoolConfig("回显 SQL", "回显 SQL", False),
            "db_pool_recycle": GsIntConfig("连接回收", "连接回收", 3600, 86400),
            "db_custom_url": GsStrConfig("自定义连接串", "自定义连接串", ""),
            "db_type": GsStrConfig("数据库类型", "sqlite/mysql/postgresql", "sqlite"),
            "db_driver": GsStrConfig("数据库驱动", "数据库驱动", ""),
        },
    )


def namespace_config(data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**data)
