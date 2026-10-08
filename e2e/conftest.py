"""pytest bootstrap：仓库根目录入 path，并安装 gsuid_core mock 存根。"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from e2e.mock_host import install  # noqa: E402

install()
