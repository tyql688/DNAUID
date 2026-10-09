"""全指令动态横扫：对路由表里每个触发器真实分发，揪出 mock 缺口。

- fullmatch/command/prefix：全触发器覆盖
- regex：按模式配构造样本（见 REGEX_SAMPLES）
- 图片类指令附带真实 sample 图片（走 ev.image_list）

只把 `ok=False`（处理器抛错）计为缺口；业务性回复（未登录/无数据）
属于真实行为，不算错。

用法：``uv run --group e2e e2e/mock_host/sweep.py``
"""

from __future__ import annotations

import io
import sys
import time
import base64
import asyncio
from typing import Any
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# regex handler -> 样本（按 sv 名匹配，找不到的用通用回退）
REGEX_SAMPLES: list[tuple[str, list[str]]] = [
    (
        "别名",
        [
            "添加测试角色别名测试名",
            "删除测试角色别名测试名",
            "测试角色别名",
            "武器测试别名列表",
            "卡米拉别名",
            "添加卡米拉别名卡姐",
            "卡姐别名",
            "删除卡米拉别名卡姐",
        ],
    ),
    ("详情卡片", ["测试角色面板", "测试角色信息", "测试角色详情", "男主面板"]),
    ("攻略", ["测试角色攻略", "刻舟攻略", "卡米拉攻略"]),
    ("密函订阅", ["订阅调停密函", "订阅角色调停密函", "取消订阅调停密函", "订阅密函周期8:30"]),
    ("签到", ["订阅签到结果", "取消订阅签到结果"]),
    ("上传", ["上传测试角色面板图", "上传男主面板图"]),
    ("删除", ["删除测试角色面板图abc123", "删除测试角色全部面板图"]),
    ("列表", ["测试角色面板图列表", "男主面板图列表"]),
    ("图鉴", ["测试角色图鉴", "测试角色wiki"]),
    ("演示", ["复读hello"]),
]


async def run_upload_chain(host: Any, prefix: str) -> dict:
    """上传→列表→删除→列表：面板图真实落盘链路（主角免登录可走通）。"""
    from e2e.mock_host import MockHost  # noqa: PLC0415

    assert isinstance(host, MockHost)
    user = "sweep_chain"
    img = _sample_image()
    steps: list[dict] = []

    async def step(text: str, images: list | None = None) -> Any:
        res = await host.chat(prefix + text, user_id=user, images=images or [])
        tools = [t for t in res.trace if t.get("kind") == "tool"]
        failed = [t for t in tools if t.get("ok") is False]
        segs = [s for r in res.replies for s in r.get("segments", [])]
        first_text = next((s.get("text", "") for s in segs if s.get("kind") == "text"), "")
        out = {
            "text": text,
            "ok": not failed,
            "error": (failed[0].get("error", "") if failed else "")[:200],
            "reply": first_text[:120],
            "segments": segs,
        }
        steps.append(out)
        return out

    await step("上传男主面板图", [img])
    s2 = await step("男主面板图列表")
    image_id = ""
    if s2["ok"]:
        import re  # noqa: PLC0415

        texts = [s.get("text", "") for s in s2.get("segments", [])]
        m = re.search(r"ID[：:](\S+)", "\n".join(texts))
        image_id = m.group(1) if m else ""
    if image_id:
        await step(f"删除男主面板图{image_id}")
        await step("男主面板图列表")
    else:
        steps.append({"text": "(skip delete: no id)", "ok": True, "error": "", "reply": ""})
    failed = [s for s in steps if not s["ok"]]
    return {"steps": steps, "ok": not failed, "error": "; ".join(s["error"] for s in failed)[:300]}


SKIP_SUBSTR = ("删除全部UID",)  # 破坏性指令只在隔离用户下跑（见下）


def _sample_image() -> str:
    img = Image.new("RGB", (120, 90), (90, 140, 250))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _regex_samples(sv: str) -> list[str]:
    for key, samples in REGEX_SAMPLES:
        if key in sv:
            return samples
    return []


def build_cases(prefix: str) -> list[dict]:
    from e2e.mock_host import HANDLERS  # noqa: PLC0415

    cases: list[dict] = []
    for h in HANDLERS:
        for trigger in h["triggers"]:
            text = str(trigger)
            if h["kind"] == "fullmatch":
                body = text
            elif h["kind"] == "command":
                body = text
            elif h["kind"] == "prefix":
                body = text + "自动签到"
            elif h["kind"] == "regex":
                continue  # 下面按 sv 配样本
            elif h["kind"] == "keyword":
                body = f"前{text}后"
            else:
                body = text
            if any(s in body for s in SKIP_SUBSTR):
                continue
            cases.append({"sv": h["sv"], "via": f"{h['kind']}:{text[:40]}", "text": prefix + body, "images": []})
        if h["kind"] == "regex":
            for sample in _regex_samples(h["sv"]):
                images = [_sample_image()] if ("上传" in h["sv"] and _sample_image()) else []
                cases.append({"sv": h["sv"], "via": f"regex:{sample[:40]}", "text": prefix + sample, "images": images})
    # 破坏性指令：专用隔离用户单独跑
    for h in HANDLERS:
        for trigger in h["triggers"]:
            if h["kind"] == "fullmatch" and any(s in str(trigger) for s in SKIP_SUBSTR):
                cases.append(
                    {
                        "sv": h["sv"],
                        "via": f"fullmatch:{trigger}",
                        "text": prefix + str(trigger),
                        "images": [],
                        "user": "sweep_destructive",
                    }
                )
    return cases


def _image_blank_flags(replies: list) -> list[str]:
    """图片回复像素方差为 0 即判空白（远端图没 Render 出来的典型症状）。"""
    flags: list[str] = []
    for reply in replies:
        for seg in reply.get("segments", []):
            if seg.get("kind") != "image" or not seg.get("url"):
                continue
            try:
                raw = base64.b64decode(seg["url"].split(",", 1)[1])
                img = Image.open(io.BytesIO(raw)).convert("L")
                # 小图（取样图等纯色块）不判；只抓大面积空白渲染失败
                if max(img.size) >= 200 and ImageStat.Stat(img).stddev[0] == 0:
                    flags.append(f"blank-image {img.size}")
            except (ValueError, OSError, IndexError):
                flags.append("undecodable-image")
    return flags


async def run_sweep() -> dict:
    from e2e.mock_host import MockHost, load_plugin, reset_state  # noqa: PLC0415
    from e2e.mock_host.loader import init_runtime  # noqa: PLC0415

    reset_state()
    report = load_plugin()
    await init_runtime()
    prefixes = report["prefixes"]
    prefix = prefixes[0] if prefixes else ""
    base = build_cases(prefix)
    # 变体维度：群聊 / 二次调用（订阅更新、重复绑定等分支）
    cases: list[dict] = []
    for case in base:
        cases.append(case)
        if case.get("user") != "sweep_destructive":
            again = dict(case)
            again["via"] = case["via"] + "#2nd"
            again["repeat"] = True
            cases.append(again)
            group = dict(case)
            group["via"] = case["via"] + "#group"
            group["group_id"] = "sweep_g1"
            cases.append(group)
    host = MockHost(handler_timeout=25.0, first_reply_grace=1.0)
    chain = await run_upload_chain(host, prefix)
    if not chain["ok"]:
        chain_case = {
            "text": prefix + "上传链路",
            "sv": "upload-chain",
            "via": "scenario",
            "matched": 1,
            "replies": 0,
            "ok": False,
            "error": chain["error"],
            "ms": 0,
        }
    else:
        chain_case = None
    results: list[dict] = []
    for i, case in enumerate(cases):
        user = case.get("user", f"sweep{i:03d}")
        started = time.perf_counter()
        try:
            res = await host.chat(case["text"], user_id=user, group_id=case.get("group_id"), images=case["images"])
            tools = [t for t in res.trace if t.get("kind") == "tool"]
            failed = [t for t in tools if t.get("ok") is False]
            blanks = _image_blank_flags(res.replies)
            err = failed[0].get("error", "")[:200] if failed else ""
            if blanks:
                err = (err + " | " + ", ".join(blanks))[:200]
            results.append(
                {
                    "text": case["text"],
                    "sv": case["sv"],
                    "via": case["via"],
                    "matched": len(res.matched),
                    "replies": len(res.replies),
                    "ok": not failed and not blanks,
                    "error": err,
                    "ms": round((time.perf_counter() - started) * 1000),
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "text": case["text"],
                    "sv": case["sv"],
                    "via": case["via"],
                    "matched": 0,
                    "replies": 0,
                    "ok": False,
                    "error": repr(exc)[:200],
                    "ms": 0,
                }
            )
    if chain_case is not None:
        results.append(chain_case)
    return {"cases": results, "prefix": prefix, "chain": chain, "failures": [r for r in results if not r["ok"]]}


def main() -> int:
    started = time.perf_counter()
    report = asyncio.run(run_sweep())
    total = len(report["cases"])
    failures = report["failures"]
    unmatched = [r for r in report["cases"] if not r["matched"]]
    print(
        f"\n共 {total} 个用例，失败 {len(failures)}，未命中路由 {len(unmatched)}，"
        f"耗时 {time.perf_counter() - started:.0f}s"
    )
    for r in failures:
        print(f"FAIL [{r['sv']}] {r['text']} :: {r['error']}")
    for r in unmatched:
        print(f"NOMATCH [{r['sv']}] {r['text']} ({r['via']})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
