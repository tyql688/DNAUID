"""``_real/`` 必须与外层 gsuid_core 一致，否则 e2e 测的不是当前 core。"""

import pytest

from e2e.mock_host.real_gsuid import REAL_DIR
from e2e.mock_host.sync_real_gsuid import CORE_PKG, inside_core, synced_files

pytestmark = pytest.mark.skipif(not inside_core(), reason="插件不在 gsuid_core/plugins/ 下，无从比对")


def test_real_copies_match_core():
    drifted = [rel for rel in synced_files() if (REAL_DIR / rel).read_bytes() != (CORE_PKG / rel).read_bytes()]
    assert not drifted, f"_real/ 与本地 core 不一致：{drifted}；运行 python e2e/mock_host/sync_real_gsuid.py 同步"
