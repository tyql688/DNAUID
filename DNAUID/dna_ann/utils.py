from __future__ import annotations

import re
import html
import time
from typing import Any
from datetime import datetime
from collections.abc import Iterable

from ..utils.dna_api import dna_api

POST_DETAIL_URL_TPL = "https://dnabbs.yingxiong.com/pc/detail/{post_id}"

LIST_DISPLAY_LIMIT = 20

_HTML_BREAK_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_LINE_RE = re.compile(r"\n{3,}")
_RELATIVE_TIME_PARTS = ("小时前", "分钟前", "刚刚")
_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
_IMAGE_EXTS = ("jpg", "jpeg", "png", "webp")


async def fetch_ann_list(*, prefer_cache: bool = True) -> list[dict[str, Any]]:
    return await dna_api.get_ann_list(is_cache=prefer_cache) or []


def build_index_map(posts: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {idx: post for idx, post in enumerate(posts, start=1)}


def resolve_index(token: str, index_map: dict[int, dict[str, Any]]) -> str | None:
    cleaned = token.strip().replace("#", "")
    if not cleaned.isdigit():
        return None
    post = index_map.get(int(cleaned))
    return str(post["postId"]) if post else None


def get_post_url(post_id: str) -> str:
    return POST_DETAIL_URL_TPL.format(post_id=post_id)


def format_post_time(raw: Any) -> str:
    if raw in (None, ""):
        return ""
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(int(raw)).strftime("%Y-%m-%d %H:%M")

    text = str(raw).strip()
    if any(part in text for part in _RELATIVE_TIME_PARTS):
        return text

    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    try:
        return datetime.strptime(f"{datetime.now().year}-{text}", "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return text


def post_time_to_timestamp(raw: Any) -> int:
    if raw in (None, ""):
        return 0
    if isinstance(raw, (int, float)):
        return int(raw)

    text = str(raw).strip()
    match = re.search(r"(\d+)\s*小时前", text)
    if match:
        return int(time.time()) - int(match.group(1)) * 3600
    match = re.search(r"(\d+)\s*分钟前", text)
    if match:
        return int(time.time()) - int(match.group(1)) * 60

    for fmt in _TIME_FORMATS:
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue

    try:
        return int(datetime.strptime(f"{datetime.now().year}-{text}", "%Y-%m-%d").timestamp())
    except ValueError:
        return 0


def normalize_text(text: str) -> str:
    raw = html.unescape(text)
    raw = _HTML_BREAK_RE.sub("\n", raw)
    raw = _HTML_TAG_RE.sub("", raw)
    raw = raw.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    raw = _BLANK_LINE_RE.sub("\n\n", raw)
    return raw.strip()


def extract_blocks(post_content: list[dict[str, Any]]) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for item in post_content or []:
        kind = item.get("contentType")
        if kind == 1:
            text = normalize_text(item.get("content") or "")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    blocks.append(("text", stripped))
        elif kind == 2:
            url = (item.get("url") or "").strip()
            if url.lower().endswith(_IMAGE_EXTS):
                blocks.append(("image", url))
        elif kind == 5:
            video = item.get("contentVideo") or {}
            cover = (video.get("coverUrl") or "").strip()
            if cover.lower().endswith(_IMAGE_EXTS):
                blocks.append(("image", cover))
    return blocks


def pick_preview(post: dict[str, Any]) -> str:
    cover = (post.get("postCover") or "").strip()
    if cover.lower().endswith(_IMAGE_EXTS):
        return cover
    video = post.get("videoContent") or {}
    if isinstance(video, dict):
        video_cover = (video.get("coverUrl") or "").strip()
        if video_cover.lower().endswith(_IMAGE_EXTS):
            return video_cover
    images = post.get("imgContent") or []
    if isinstance(images, list):
        for entry in images:
            if isinstance(entry, dict):
                url = (entry.get("url") or "").strip()
                if url.lower().endswith(_IMAGE_EXTS):
                    return url
    return ""


def pick_subject(post: dict[str, Any]) -> str:
    title = (post.get("postTitle") or "").strip()
    if title:
        return title
    content = post.get("postContent")
    if isinstance(content, str):
        text = normalize_text(content)
        if text:
            return text.splitlines()[0][:40]
    return f"#{post.get('postId', '')}"


def pick_time(post: dict[str, Any]) -> str:
    show = (post.get("showTime") or "").strip()
    if show:
        return show
    raw = post.get("postTime") or post.get("createTime")
    return format_post_time(raw) if raw else ""
