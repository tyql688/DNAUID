# DNAUID e2e Mock 宿主

在**没有真实 `gsuid_core` 宿主**的情况下，端到端验证插件的完整回复链路。
mock 只替换“宿主边界”（SV 注册、Bot 发送、Event、DB 引擎位），业务代码
（全部 24 个插件模块）、配置系统、数据库、上游绘图函数**全部跑真实的**。

```text
用户输入 → 前缀剥离 → SV 路由（真语义）→ 处理器执行（真代码）
        → Bot 回显（文本/图片/@/转发） + 工具调用 trace
```

## 目录结构

```text
e2e/
├── README.md                  本文档
├── requirements-e2e.txt       pytest + 全真实链路所需的第三方依赖
├── pytest.ini / conftest.py   pytest 配置与 mock 安装
├── smoke.py                   无 pytest 时的冒烟 runner（仅标准库）
├── run_web.py                 Web 服务启动入口
├── mock_host/
│   ├── stubs.py               伪造 gsuid_core 包（SV/Bot/Event/订阅/配置/DB 位）
│   ├── gs_config_real.py      真实插件配置系统（defaults + JSON 持久化）
│   ├── database.py            真实 sqlite 建表 + 迁移
│   ├── dispatcher.py          前缀剥离 + 路由分发 + trace（真宿主语义）
│   ├── bot.py / event.py      MockBot / MockEvent
│   ├── segments.py            消息段序列化（文本/图片/at/转发/base64://）
│   ├── loader.py              加载真实插件模块 + DB 初始化
│   ├── real_gsuid.py          白名单 import hook（装载上游真实源码）
│   ├── sync_real_gsuid.py     同步上游源码脚本（pin 固定 commit）
│   ├── help_image.py          本地降级渲染器（真实链路缺失时才用）
│   ├── audit.py               静态依赖覆盖审计
│   ├── sweep.py               全指令动态横扫
│   └── _real/                 上游 gsuid_core 真实源码（见 PINNED.txt）
├── web/
│   ├── server.py              HTTP 服务（标准库）+ /dna/* 反代到登录页
│   └── static/index.html      聊天界面（单文件）
└── tests/                     pytest 用例（含审计/横扫/真实回复）
```

## 环境准备

```bash
uv sync --group e2e
```

依赖组定义在 `pyproject.toml` 的 `[dependency-groups] e2e`（与
`e2e/requirements-e2e.txt` 保持同步，改一处记着改另一处）。

mock 宿主与 Web 服务本身仅需标准库；依赖是为“真实导入全部插件模块”
准备的（缺失时相关测试自动 skip）。

```bash
uv run --group e2e pytest e2e/tests/ -v   # 全量（含约1分钟的横扫）
uv run --group e2e e2e/smoke.py               # 无 pytest 时的最小冒烟
```

## 用法 A：直接打后端 API（Agent / 自动化测试）

启动服务（默认 `127.0.0.1:8765`）：

```bash
uv run --group e2e e2e/run_web.py --port 8765 --watch
```

`--watch` 用原生文件事件监听 `DNAUID/` 与 `e2e/` 下的 `*.py`，改动自动重启服务
（开发用；不加则单次运行）。改代码不用重启终端，刷网页/重打 API 即可。

### 聊天（核心）

```bash
curl -X POST http://127.0.0.1:8765/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"dna帮助","user_id":"10001","group_id":null,"images":[]}'
```

- `text`：用户原文（必须带插件前缀，见下）。
- `user_id` / `group_id`：身份，`group_id` 留空为私聊（很多指令区分群/私）。
- `images`：dataURL 数组，进 `ev.image_list`（gif/webp 会被宿主归一化为 PNG）。
- 返回：`replies`（Bot 回显：`text/image/at/node/reply` 段，图片为 dataURL）、
  `trace`（命中的 `SV.处理器`、耗时、ok/失败原因）、`matched`（路由信息）、
  `total`（历史下标，前端去重用）。

```bash
# 自定义消息前缀（默认 dna/DNA/jjj/JJJ，来自插件声明）
curl -X POST http://127.0.0.1:8765/api/config \
  -H 'Content-Type: application/json' -d '{"prefixes":["#","!"]}'

# 宿主状态：前缀 / 插件 / 路由数 / 加载报告 / 历史
curl http://127.0.0.1:8765/api/state

# 指令表（按 SV 分组：kind + triggers，供自动化遍历）
curl http://127.0.0.1:8765/api/commands

# 历史增量（后台推送靠它冒泡；since 为绝对下标）
curl 'http://127.0.0.1:8765/api/history?since=0'

# 清空（含 mock DB 不清；DB 文件见“数据位置”）
curl -X POST http://127.0.0.1:8765/api/reset

# 运行插件 on_core_start 钩子（结果进 trace）
curl -X POST http://127.0.0.1:8765/api/startup
```

### Python 进程内调用（单测/脚本）

```python
import asyncio, sys

sys.path.insert(0, ".")
from e2e.mock_host import install, load_plugin, reset_state, MockHost
from e2e.mock_host.loader import init_runtime


async def main():
    install()
    reset_state()
    load_plugin()
    await init_runtime()  # 真实 sqlite 建表
    host = MockHost()  # handler_timeout / first_reply_grace 可配
    r = await host.chat("dna绑定1234567890123", user_id="u1")
    print(r.matched, r.replies, r.trace)


asyncio.run(main())
```

长耗时处理器（登录等待扫码轮询 600s）不会卡住：首包回复后宽限
`first_reply_grace`（默认 3s），仍未结束转后台，`host.background` 可查，
后续消息在下一轮 `chat` / 历史轮询中带出。

### 覆盖率工具（推荐进 CI）

```bash
# 静态：插件所有 gsuid_core 引用逐个验证（缺字段/缺方法即报错）
uv run --group e2e e2e/mock_host/audit.py

# 动态：路由表每个触发器真实分发（群聊/二次调用变体 + 图片空白检测）
uv run --group e2e e2e/mock_host/sweep.py
```

两者都已锁进 pytest（`test_audit.py` / `test_sweep.py`）。

## 用法 B：打开网页（人类手动测试）

浏览器打开 http://127.0.0.1:8765/ ：

- **发消息**：输入框 Enter 发送，Shift+Enter 换行；`自动补前缀` 勾上可省略前缀。
- **指令 tab**：侧边栏“指令”页是全量指令表，可搜索，点“填入”进输入框。
- **图片**：＋按钮上传（进 `ev.image_list`）；所有图片可点击放大——滚轮以光标为中心缩放、双指缩放、拖动（至少保留 1px）、×/空白/Esc 关闭。
- **工具调用**：每次分发命中的处理器、耗时、成功/失败明细，可折叠查看；失败会带出真实异常。
- **登录**：`dna登录` 回真实登录地址（`localhost:端口/dna/i/...`，页内可点），
  网页提交后完成推送会自动冒泡（3 秒轮询），不用再发一句话刷新。
- **宽屏折叠侧边栏**：☰ 切换（偏好记住）；窄屏自动变抽屉。
- **首次使用流程**：`dna绑定<13位UID>` → `dna登录`（网页完成）→
  `dna恢复别名`（构建 id2name，之后面板/上传类指令才认得角色）。

## mock 与真实的边界

| 插件依赖 | mock 做法 |
|---|---|
| SV 路由/装饰器 | 真语义复刻：trie 类优先、同级 priority、注册顺序、block 截断、事件深拷贝、pm 门控 |
| Bot.send | 真实捕获：文本/图片/at/转发/`base64://` 原样序列化，本地路径图读文件转 dataURL |
| Event | 复刻全部消费字段（含 `WS_BOT_ID`/`sender`/`bot_self_id`） |
| StringConfig | **真实实现**：defaults + JSON 持久化 + get/set |
| Bind/User + with_session | **上游真实 `base_models`** + sqlite 落盘 |
| get_new_help/convert_img/图片工具/download | **上游真实源码**（`_real/`，pin 固定 commit） |
| get_qrcode_base64 | **上游真实源码**，编码真实 URL |
| gs_subscribe | 内存实现，条目同构（含过滤/update/send 投递到 outbox） |
| gss.active_bot | 注册 MockBot，`target_send` 落收件箱（推送可见） |
| web_app 登录页 | 真实 FastAPI 对象挂载插件路由，uvicorn 运行，聊天服务反代 `/dna/*` |
| scheduler | 注册收集（不推进时间轮） |
| 游戏服务端网络 | 直通真实服务器（需真实凭证/登录态） |

上游源码更新：改 `sync_real_gsuid.py` 的 `PINNED_COMMIT` 后重跑该脚本。
20MB 上游字体未入库，缺失时回退插件自带 `dna_fonts.ttf`（版式代码仍是真实的）。

## 数据位置与常见问题

- mock 数据根目录：系统临时目录下 `mock_host_res/`（DB `GsData.db`、配置 JSON、图片缓存都在此；删掉即恢复出厂）。
- `角色【X】的CharId未找到` → 先发 `dna恢复别名`（生产环境同样需要这一步）。
- `不能同时携带两把近战武器` → 插件拿展柜真数据校验的，改游戏内配装或带武器查（`dna法露茜面板+祈请净火`）。
- `未找到有效的密函数据` → 先看 trace 是异常还是业务回复；公开数据无需登录，偶发多为游戏接口抖动，重试即可。
- 登录页打不开 → 确认服务启动无报错（uvicorn 端口为聊天端口自动分配），`get_dna_login_url` 依赖 core 的 HOST/PORT（默认 `127.0.0.1:8765`）。
