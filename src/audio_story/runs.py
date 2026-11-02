"""Thư mục run: nơi mọi bước đọc/ghi file. ``run.json`` ghi nguồn, trạng thái và lịch sử từng bước."""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .textnorm import slugify

RUN_FILE = "run.json"
SUBDIRS = ("source", "transcript", "story", "script", "audio", "qa", "out")


class RunError(Exception):
    """Lỗi người dùng sửa được (sai đường dẫn, thiếu file bước trước…)."""


def runs_root() -> Path:
    return Path(os.environ.get("AUDIO_STORY_RUNS_DIR", "audio-story-runs")).expanduser().resolve()


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def create(title_hint: str, source: dict[str, Any], root: Path | None = None) -> Path:
    root = root or runs_root()
    run_id = secrets.token_hex(3)
    day = datetime.now().strftime("%Y-%m-%d")
    path = root / f"{slugify(title_hint)}-{day}-{run_id}"
    for d in SUBDIRS:
        (path / d).mkdir(parents=True, exist_ok=True)
    write_json(path / RUN_FILE, {"run_id": run_id, "created_at": now(), "source": source, "status": "created",
                                 "history": []})
    return path


def resolve(run: str) -> Path:
    """``run`` = đường dẫn thư mục run (tuyệt đối/tương đối) hoặc tên thư mục dưới ``runs_root()``."""
    p = Path(run).expanduser()
    for cand in (p, runs_root() / run):
        if (cand / RUN_FILE).is_file():
            return cand.resolve()
    raise RunError(f"không thấy thư mục run «{run}» (cần có {RUN_FILE}). Gốc mặc định: {runs_root()}")


def load(path: Path) -> dict[str, Any]:
    return read_json(path / RUN_FILE)


def record(path: Path, step: str, status: str, **info: Any) -> None:
    """Ghi một bước vào ``history`` và cập nhật ``status``."""
    data = load(path)
    data["status"] = status
    data["history"].append({"step": step, "at": now(), **info})
    write_json(path / RUN_FILE, data)


def update(path: Path, **fields: Any) -> None:
    data = load(path)
    data.update(fields)
    write_json(path / RUN_FILE, data)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RunError(f"thiếu file {path}") from None
    except json.JSONDecodeError as e:
        raise RunError(f"{path} không phải JSON hợp lệ: {e}") from None


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def files(path: Path) -> dict[str, Any]:
    """Các file chính đã có — để biết run đang ở bước nào."""
    want = {
        "audio": next((str(p) for p in sorted((path / "source").glob("audio.*")) if p.suffix != ".part"), None),
        "transcript": path / "transcript" / "transcript.txt",
        "story_bible": path / "story" / "story_bible.json",
        "cast": path / "story" / "cast.json",
        "script": path / "script" / "script.json",
        "check": path / "script" / "check.json",
        "pronunciation": path / "pronunciation.json",
        "audio_manifest": path / "audio" / "manifest.json",
        "qa": path / "qa" / "report.json",
        "mp3": path / "out" / "story.mp3",
        "wav": path / "out" / "story.wav",
    }
    out: dict[str, Any] = {}
    for k, v in want.items():
        if v is None:
            out[k] = None
        else:
            p = Path(v)
            out[k] = str(p) if p.exists() else None
    return out


def next_step(f: dict[str, Any]) -> str:
    if not f["transcript"]:
        return "transcribe" if f["audio"] else "fetch_source"
    if not f["cast"] or not f["script"]:
        return "write_story (Claude: story_bible.json → cast.json → script.json + script.md)"
    if not f["check"]:
        return "check_script"
    if not f["audio_manifest"]:
        return "user_review → tts_render"
    if not f["mp3"] and not f["wav"]:
        return "assemble"
    return "done"
