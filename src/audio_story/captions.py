"""Đọc phụ đề WebVTT / SRT thành đoạn có thời gian.

Phụ đề tự động của YouTube lặp dòng kiểu «cuộn» (mỗi cue nhắc lại dòng trước) và có thẻ thời gian nội dòng
``<00:00:01.200><c>…</c>`` — bỏ thẻ và bỏ dòng trùng dòng vừa ghi.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")
_ARROW = re.compile(r"^\s*(\S+)\s*-->\s*(\S+)")
_TAG = re.compile(r"<[^>]+>")


def _sec(ts: str) -> float:
    m = _TS.match(ts)
    if not m:
        raise ValueError(f"mốc thời gian lạ: {ts!r}")
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000


def parse(text: str) -> list[dict]:
    """VTT hoặc SRT → ``[{"start", "end", "text"}]`` (đã bỏ dòng lặp)."""
    segs: list[dict] = []
    last_line = ""
    for block in re.split(r"\r?\n\s*\r?\n", text.replace("﻿", "")):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        idx = next((i for i, ln in enumerate(lines) if _ARROW.match(ln)), None)
        if idx is None:
            continue
        m = _ARROW.match(lines[idx])
        try:
            start, end = _sec(m.group(1)), _sec(m.group(2))
        except ValueError:
            continue
        fresh = []
        for ln in lines[idx + 1 :]:
            clean = " ".join(html.unescape(_TAG.sub("", ln)).split())
            if not clean or clean == last_line:
                continue
            fresh.append(clean)
            last_line = clean
        if fresh:
            segs.append({"start": round(start, 3), "end": round(end, 3), "text": " ".join(fresh)})
    return segs


def parse_file(path: Path) -> list[dict]:
    return parse(path.read_text(encoding="utf-8", errors="replace"))
