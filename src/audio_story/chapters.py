"""``split_chapters``: tách transcript dài thành từng chương theo mốc «Chương <số>» → ``transcript/chapters/``.

Thêm 02/11/2026 sau lần chạy thử trong Claude Code: truyện 6 giờ (387k ký tự, ~40 chương) — Claude phải tự viết Python
để cắt chương 219. Mốc chương chỉ nhận khi số **tăng dần** (bỏ qua câu nhắc lại «như ở chương 12…»).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import runs

_MARK = re.compile(r"(?<!\w)(?:Chương|CHƯƠNG|chương)\s+(\d{1,5})(?!\d)")


def find_marks(text: str) -> list[tuple[int, int]]:
    """[(số chương, vị trí)] — chỉ giữ mốc có số lớn hơn mốc trước (bỏ lặp và nhắc lại)."""
    out: list[tuple[int, int]] = []
    for m in _MARK.finditer(text):
        n = int(m.group(1))
        if not out or n > out[-1][0]:
            out.append((n, m.start()))
    return out


def split(run_dir: Path) -> dict[str, Any]:
    tjson = run_dir / "transcript" / "transcript.json"
    segs = runs.read_json(tjson)["segments"]
    # nối lại, nhớ vị trí bắt đầu mỗi đoạn để suy ra mốc thời gian
    text, starts = "", []
    for s in segs:
        starts.append((len(text), s.get("start")))
        text += s["text"] + "\n"
    marks = find_marks(text)
    out_dir = run_dir / "transcript" / "chapters"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.txt"):
        old.unlink()

    def time_at(pos: int) -> float | None:
        t = None
        for p, st in starts:
            if p > pos:
                break
            t = st
        return t

    items: list[dict[str, Any]] = []
    bounds: list[tuple[int | None, int]] = [] if marks and marks[0][1] == 0 else [(None, 0)]
    bounds += marks
    for i, (n, pos) in enumerate(bounds):
        end = bounds[i + 1][1] if i + 1 < len(bounds) else len(text)
        body = " ".join(text[pos:end].split())
        if not body:
            continue
        name = f"chuong-{n:04d}.txt" if n is not None else "phan-dau.txt"
        f = out_dir / name
        f.write_text(body + "\n", encoding="utf-8")
        items.append({"chapter": n, "file": str(f), "chars": len(body), "start_s": time_at(pos),
                      "est_audio_min": round(len(body) / 900, 1)})
    runs.record(run_dir, "split_chapters", runs.load(run_dir)["status"], chapters=len(marks))
    return {"chapters": items, "count": len([x for x in items if x["chapter"] is not None]),
            "dir": str(out_dir), "note": "phan-dau.txt = phần trước mốc chương đầu tiên (thường là đuôi chương trước)"}
