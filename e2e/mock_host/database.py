"""插件数据库初始化：真实建表 + 执行迁移语句。"""

from __future__ import annotations

from typing import Any
from pathlib import Path


def db_path() -> Path:
    from .stubs import get_res_path  # noqa: PLC0415

    return get_res_path() / "GsData.db"


async def init_plugin_db(reset: bool = False) -> dict[str, Any]:
    """初始化真实 sqlite 数据库（插件模型已在 import 时注册）。

    Args:
        reset: 为 True 时删除旧库重建（测试隔离用）。
    """
    from sqlmodel import SQLModel  # noqa: PLC0415
    from sqlalchemy import text, create_engine  # noqa: PLC0415
    from sqlalchemy.exc import OperationalError  # noqa: PLC0415

    from gsuid_core.utils.database.startup import exec_list  # noqa: PLC0415
    from gsuid_core.utils.database.base_models import init_database  # type: ignore[import-not-found]  # noqa: PLC0415

    path = db_path()
    if reset and path.exists():
        path.unlink()

    await init_database()

    engine = create_engine(f"sqlite:///{path}")
    tables_before = len(SQLModel.metadata.tables)
    SQLModel.metadata.create_all(engine)
    migrated, skipped = 0, 0
    with engine.begin() as conn:
        for stmt in list(exec_list):
            try:
                conn.execute(text(stmt))
                migrated += 1
            except OperationalError:
                skipped += 1  # 列已存在等情况直接跳过
    engine.dispose()
    return {
        "db": str(path),
        "tables": sorted(SQLModel.metadata.tables.keys()),
        "table_count": len(SQLModel.metadata.tables),
        "tables_before": tables_before,
        "migrated": migrated,
        "skipped": skipped,
    }
