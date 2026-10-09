"""MockHost：消息前缀剥离 → SV 路由匹配 → 处理器执行 → 回显收集。"""

from __future__ import annotations

import re
import copy
import time
import asyncio
from typing import Any
from dataclasses import field, dataclass

from .bot import MockBot
from .event import make_event
from .stubs import HANDLERS, get_active_prefixes


@dataclass
class DispatchResult:
    replies: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    matched: list[dict[str, Any]] = field(default_factory=list)
    prefix: str = ""
    body: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "replies": self.replies,
            "trace": self.trace,
            "matched": self.matched,
            "prefix": self.prefix,
            "body": self.body,
        }


def strip_prefix(raw: str, prefixes: list[str]) -> tuple[str, str] | None:
    """剥离插件前缀，返回 ``(prefix, body)``；无命中返回 None。"""
    text = raw.strip()
    for prefix in sorted(prefixes, key=len, reverse=True):
        if prefix and text.startswith(prefix):
            return prefix, text[len(prefix) :].lstrip()
    return None


# 与上游 trigger_index / handler 排序语义对齐：trie 类（command/prefix/fullmatch）
# 先于兜底桶（regex/keyword），同级再按 priority，最后按注册顺序。
_TYPE_RANK = {"command": 0, "prefix": 0, "fullmatch": 0, "suffix": 1, "keyword": 2, "regex": 2, "message": 3, "meta": 3}


def _match_handler(raw: str, body: str, handler: dict[str, Any]) -> dict[str, Any] | None:
    kind = handler["kind"]
    for trigger in handler["triggers"]:
        if kind == "fullmatch":
            if body.strip() == str(trigger):
                return {"command": str(trigger), "text": "", "trigger": str(trigger)}
        elif kind == "prefix":
            # 真宿主：触发词本身不算命中，后面必须还有正文
            if body.startswith(str(trigger)) and len(body) > len(str(trigger)):
                rest = body[len(str(trigger)) :].strip()
                return {"command": body, "text": rest, "trigger": str(trigger)}
        elif kind == "command":
            name = str(trigger)
            if body == name or body.startswith(name):
                rest = body[len(name) :].lstrip()
                return {"command": name, "text": rest, "trigger": name}
        elif kind == "regex":
            # 真宿主用 findall/search 判定（非 match），分组同样按 search 取
            m = re.search(str(trigger), body)
            if m:
                # 真宿主：groupdict 原样保留 None（插件靠 is not None 过滤未参与分组）
                groups = dict(m.groupdict() or {})
                parts = [g if g is not None else "" for g in m.groups()]
                split_parts = [p if p is not None else "" for p in re.split(str(trigger), raw)]
                return {
                    "command": "|".join(parts),
                    "text": "|".join(split_parts),
                    "trigger": str(trigger),
                    "regex_dict": groups,
                    "regex_group": m.groups(),
                }
        elif kind == "keyword":
            if str(trigger) in raw:
                return {"command": body, "text": body, "trigger": str(trigger)}
    return None


class MockHost:
    """有状态的 mock 宿主：维护历史、Bot、trace。"""

    def __init__(
        self,
        bot: MockBot | None = None,
        handler_timeout: float = 30.0,
        first_reply_grace: float = 3.0,
    ) -> None:
        from .stubs import gs_subscribe  # noqa: PLC0415

        self.bot = bot or MockBot()
        self.history: list[dict[str, Any]] = []
        import gsuid_core.gss as _gss_mod  # noqa: PLC0415

        _gss_mod.gss.register(self.bot)
        self.subscriptions = gs_subscribe
        # 长耗时处理器（如登录等待扫码）：首包回复后宽限 N 秒，仍未结束则转后台
        self.handler_timeout = handler_timeout
        self.first_reply_grace = first_reply_grace
        self.background: list[asyncio.Task] = []

    # -- 配置 ------------------------------------------------------------
    def get_prefixes(self) -> list[str]:
        return get_active_prefixes()

    # -- 主入口 ----------------------------------------------------------
    async def chat(
        self,
        text: str,
        user_id: str = "10001",
        group_id: str | None = None,
        images: list | None = None,
        user_pm: int = 0,
    ) -> DispatchResult:
        import uuid as _uuid  # noqa: PLC0415

        from .turn import current_turn  # noqa: PLC0415

        result = DispatchResult()
        token = _uuid.uuid4().hex[:8]
        reset_token = current_turn.set(token)
        prefixes = self.get_prefixes()
        stripped = strip_prefix(text, prefixes)
        if stripped is None:
            result.trace.append(
                {
                    "kind": "system",
                    "message": f"未命中前缀（当前可用：{' / '.join(prefixes)}），消息被宿主忽略",
                }
            )
            self.history.append({"role": "user", "text": text, "images": images or []})
            self.history.append({"role": "system", "text": result.trace[-1]["message"]})
            current_turn.reset(reset_token)
            return result

        prefix, body = stripped
        result.prefix = prefix
        result.body = body
        ev = make_event(text, user_id=user_id, group_id=group_id, images=images, user_pm=user_pm)
        inbox_before = len(self.bot.inbox)
        self.history.append(
            {"role": "user", "text": text, "images": images or [], "user_id": str(user_id), "group_id": group_id}
        )

        # 路由：trie 类优先，同级 priority 小优先，再按注册顺序；
        # 每个命中拿事件深拷贝（真宿主同样），互不污染。
        candidates = sorted(
            HANDLERS,
            key=lambda h: (_TYPE_RANK.get(h.get("kind", ""), 2), h.get("priority", 5), HANDLERS.index(h)),
        )
        invoked = False
        base_ev = ev
        for handler in candidates:
            # 与真宿主一致：数值越小权限越高，用户 pm 大于指令要求就跳过
            if base_ev.user_pm > handler["pm"]:
                continue
            info = _match_handler(text, body, handler)
            if info is None:
                continue
            ev = copy.deepcopy(base_ev)
            ev.command = info["command"]
            ev.text = info["text"]
            if "regex_dict" in info:
                ev.regex_dict = info["regex_dict"]
                ev.regex_group = info["regex_group"]
            matched_entry = {
                "sv": handler["sv"],
                "handler": handler["func_name"],
                "via": f"{handler['kind']}:{info['trigger']}",
            }
            result.matched.append(matched_entry)
            trace_entry: dict[str, Any] = {
                "kind": "tool",
                "tool": f"{handler['sv']}.{handler['func_name']}",
                "args": {"command": ev.command, "text": ev.text, **({"regex": ev.regex_dict} if ev.regex_dict else {})},
            }
            start = time.perf_counter()
            before = len(self.bot.inbox)
            try:
                await self._run_handler(handler["func"], ev, trace_entry, before)
                trace_entry["ok"] = True
            except Exception as exc:  # noqa: BLE001
                trace_entry["ok"] = False
                trace_entry["error"] = f"{type(exc).__name__}: {exc}"[:500]
                await self.bot.send(f"[mock-host] 处理器执行失败：{exc}")
            finally:
                trace_entry["ms"] = round((time.perf_counter() - start) * 1000, 2)
                trace_entry["sent"] = len(self.bot.inbox) - before
            result.trace.append(trace_entry)
            invoked = True
            if handler.get("block"):
                result.trace.append({"kind": "system", "message": f"{handler['sv']} 阻断后续匹配（block=True）"})
                break

        if not invoked:
            result.trace.append({"kind": "system", "message": f"前缀 {prefix!r} 命中，但没有处理器匹配 body={body!r}"})

        try:
            result.replies = [r.to_dict() for r in self.bot.inbox[inbox_before:] if r.extra.get("turn") == token]
            for record in self.bot.inbox[inbox_before:]:
                self._append_history({"role": "bot", **record.to_dict()}, record.msg_id)
            for trace in result.trace:
                self.history.append({"role": "tool", **trace})
            return result
        finally:
            current_turn.reset(reset_token)

    async def _run_handler(self, func: Any, ev: Any, trace_entry: dict, before: int) -> None:
        ret = func(self.bot, ev)
        if not asyncio.iscoroutine(ret):
            return
        task: asyncio.Task = asyncio.ensure_future(ret)
        deadline = time.perf_counter() + self.handler_timeout
        grace_until: float | None = None
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.2)
            if done:
                exc = task.exception()
                if exc is not None:
                    raise exc
                return
            now = time.perf_counter()
            if len(self.bot.inbox) > before and grace_until is None:
                grace_until = now + self.first_reply_grace
            if grace_until is not None and now >= grace_until:
                break
            if now >= deadline:
                break
        # 转后台：轮询/等待类处理器继续跑，后续回复在下一轮对话中带出
        trace_entry["background"] = True
        trace_entry["note"] = f"处理器 {self.handler_timeout}s 未结束，已转后台继续；后续消息将在下一轮对话中同步"
        self.background.append(task)
        task.add_done_callback(lambda t: self._forget_background(t))

    def _forget_background(self, task: asyncio.Task) -> None:
        if task in self.background:
            self.background.remove(task)
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                self.history.append({"role": "tool", "kind": "error", "message": f"后台任务失败：{exc!r}"[:300]})

    def _append_history(self, entry: dict[str, Any], msg_id: int = 0) -> None:
        """按记录 ID 去重追加（并发/重入下不记重）。"""
        seen = getattr(self, "_history_ids", None)
        if seen is None:
            seen = self._history_ids = set()
        if msg_id and msg_id in seen:
            return
        if msg_id:
            seen.add(msg_id)
        self.history.append(entry)

    def sync_inbox(self) -> int:
        """把后台任务新投递的消息同步进历史（UI 轮询展示）。"""
        count = 0
        for record in self.bot.inbox:
            before = len(self.history)
            self._append_history({"role": "bot", **record.to_dict()}, record.msg_id)
            count += len(self.history) - before
        return count

    def reset(self) -> None:
        for task in self.background:
            task.cancel()
        self.background.clear()
        self.bot.clear()
        self.history.clear()
        self._history_ids = set()
