"""``fetch_source``: tạo run từ link YouTube (yt-dlp) hoặc từ file trên máy (audio / transcript có sẵn)."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from . import media, runs

AUDIO_EXT = {".mp3", ".m4a", ".wav", ".webm", ".ogg", ".opus", ".flac", ".aac", ".mp4", ".mkv"}
TEXT_EXT = {".txt", ".md"}
SUB_EXT = {".vtt", ".srt"}
SUB_LANGS = ["vi", "vi-orig", "vi-VN"]


def is_url(source: str) -> bool:
    return bool(re.match(r"^https?://", source.strip()))


def fetch(source: str, *, title: str | None = None, with_audio: bool = True, root: Path | None = None) -> dict[str, Any]:
    source = source.strip()
    if is_url(source):
        return _fetch_url(source, title=title, with_audio=with_audio, root=root)
    return _fetch_file(Path(source).expanduser(), title=title, root=root)


# ---------------------------------------------------------------- YouTube


def _ydl_opts(src_dir: Path) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "ffmpeg_location": media.ffmpeg_exe(),
        "outtmpl": str(src_dir / "audio.%(ext)s"),
    }
    if cookies := os.environ.get("AUDIO_STORY_YT_COOKIES"):
        opts["cookiefile"] = os.path.expanduser(cookies)
    if browser := os.environ.get("AUDIO_STORY_YT_BROWSER"):
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def _pick_sub(info: dict[str, Any]) -> tuple[str, bool] | None:
    """Chọn (ngôn ngữ, tự_động?) — phụ đề thủ công tiếng Việt trước, rồi phụ đề tự động gốc tiếng Việt."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    for lang in SUB_LANGS:
        if lang in manual:
            return lang, False
    for lang in ("vi-orig", "vi"):
        if lang in auto:
            return lang, True
    return None


def _fetch_url(url: str, *, title: str | None, with_audio: bool, root: Path | None) -> dict[str, Any]:
    import yt_dlp

    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True,
                               **{k: v for k, v in _ydl_opts(Path(".")).items() if k.startswith("cookie")}}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise runs.RunError(f"yt-dlp không đọc được link: {e}. Nếu YouTube đòi đăng nhập/chống bot, đặt "
                            "AUDIO_STORY_YT_BROWSER=chrome (lấy cookie trình duyệt) hoặc AUDIO_STORY_YT_COOKIES=<file>.") from e
    meta = {k: info.get(k) for k in ("id", "title", "channel", "uploader", "duration", "upload_date", "webpage_url",
                                      "description", "language")}
    meta["chapters"] = [{"title": c.get("title"), "start": c.get("start_time"), "end": c.get("end_time")}
                        for c in info.get("chapters") or []]
    path = runs.create(title or meta.get("title") or meta.get("id") or "youtube",
                       {"kind": "youtube", "url": url, "id": meta.get("id")}, root)
    src_dir = path / "source"
    runs.write_json(src_dir / "meta.json", meta)

    warnings: list[str] = []
    sub = _pick_sub(info)
    sub_file = None
    if sub:
        lang, is_auto = sub
        try:
            opts = _ydl_opts(src_dir) | {"skip_download": True, "subtitleslangs": [lang], "subtitlesformat": "vtt",
                                          "writesubtitles": not is_auto, "writeautomaticsub": is_auto,
                                          "outtmpl": str(src_dir / "captions.%(ext)s")}
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            found = sorted(src_dir.glob("captions*.vtt"))
            if found:
                sub_file = found[0].rename(src_dir / f"captions.{lang}{'.auto' if is_auto else ''}.vtt")
        except Exception as e:  # noqa: BLE001 — phụ đề lỗi không chặn tải audio
            warnings.append(f"không tải được phụ đề {lang}: {e}")

    audio = None
    if with_audio:
        try:
            with yt_dlp.YoutubeDL(_ydl_opts(src_dir) | {"format": "bestaudio/best"}) as ydl:
                ydl.download([url])
            audio = next((p for p in sorted(src_dir.glob("audio.*")) if p.suffix not in {".part", ".ytdl"}), None)
        except Exception as e:
            raise runs.RunError(f"tải audio lỗi: {e}") from e

    runs.record(path, "fetch_source", "fetched", audio=str(audio) if audio else None,
                captions=str(sub_file) if sub_file else None)
    return {
        "run_dir": str(path),
        "title": meta.get("title"),
        "channel": meta.get("channel") or meta.get("uploader"),
        "duration_s": meta.get("duration"),
        "chapters": len(meta["chapters"]),
        "audio": str(audio) if audio else None,
        "captions": {"file": str(sub_file), "lang": sub[0], "auto": sub[1]} if sub_file and sub else None,
        "warnings": warnings,
        "next": "transcribe",
    }


# ---------------------------------------------------------------- file trên máy


def _fetch_file(p: Path, *, title: str | None, root: Path | None) -> dict[str, Any]:
    if not p.is_file():
        raise runs.RunError(f"không thấy file {p}")
    ext = p.suffix.lower()
    if ext not in AUDIO_EXT | TEXT_EXT | SUB_EXT:
        raise runs.RunError(f"định dạng {ext} chưa hỗ trợ (audio: {sorted(AUDIO_EXT)}; chữ: {sorted(TEXT_EXT | SUB_EXT)})")
    path = runs.create(title or p.stem, {"kind": "file", "path": str(p.resolve())}, root)
    src_dir = path / "source"
    out: dict[str, Any] = {"run_dir": str(path), "title": title or p.stem, "audio": None, "captions": None,
                           "transcript_text": None, "warnings": []}
    if ext in AUDIO_EXT:
        dst = src_dir / f"audio{ext}"
        shutil.copy2(p, dst)
        out["audio"] = str(dst)
    elif ext in SUB_EXT:
        dst = src_dir / f"captions.file{ext}"
        shutil.copy2(p, dst)
        out["captions"] = {"file": str(dst), "lang": "vi", "auto": False}
    else:
        dst = src_dir / f"transcript{ext}"
        shutil.copy2(p, dst)
        out["transcript_text"] = str(dst)
    runs.write_json(src_dir / "meta.json", {"title": out["title"], "file": str(p.resolve())})
    runs.record(path, "fetch_source", "fetched", file=str(dst))
    out["next"] = "transcribe"
    return out
