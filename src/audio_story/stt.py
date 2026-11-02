"""Chuyển audio thành chữ. Engine:

- ``captions``: phụ đề tải từ YouTube / file .vtt .srt (nhanh, miễn phí; phụ đề tự động tiếng Việt thường thiếu dấu câu).
- ``text``: file .txt/.md người dùng đưa sẵn.
- ``openai``: OpenAI STT (``OPENAI_API_KEY``; model ``AUDIO_STORY_OPENAI_STT_MODEL``, mặc định ``gpt-4o-transcribe``),
  cắt khúc ``AUDIO_STORY_STT_CHUNK_S`` giây (mặc định 600) thành mp3 64 kbps để dưới giới hạn 25 MB; khúc đã chép
  được lưu lại nên chạy lại không tốn tiền lần nữa.
- ``whisper``: faster-whisper tại máy (``uv sync --extra whisper``; model ``AUDIO_STORY_WHISPER_MODEL``, mặc định
  ``large-v3-turbo``) — miễn phí nhưng chậm trên CPU.
- ``auto``: captions/text nếu có → openai nếu có key → whisper nếu đã cài.
"""

from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from . import captions, media, runs

ENGINES = ("auto", "captions", "text", "openai", "whisper")
OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"


def has_openai() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def has_whisper() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _find(src: Path, patterns: tuple[str, ...]) -> Path | None:
    for pat in patterns:
        hit = sorted(src.glob(pat))
        if hit:
            return hit[0]
    return None


def _audio(src: Path) -> Path | None:
    return next((p for p in sorted(src.glob("audio.*")) if p.suffix not in {".part", ".ytdl"}), None)


def pick_engine(run_dir: Path, engine: str) -> str:
    if engine not in ENGINES:
        raise runs.RunError(f"engine phải là một trong {ENGINES}")
    if engine != "auto":
        return engine
    src = run_dir / "source"
    if _find(src, ("transcript.*",)):
        return "text"
    if _find(src, ("captions.*.vtt", "captions.*.srt")):
        return "captions"
    if has_openai():
        return "openai"
    if has_whisper():
        return "whisper"
    raise runs.RunError("không có engine STT nào dùng được: video không có phụ đề tiếng Việt, chưa đặt OPENAI_API_KEY, "
                        "chưa cài faster-whisper (`uv sync --extra whisper`).")


def transcribe(run_dir: Path, engine: str = "auto", *, language: str = "vi") -> dict[str, Any]:
    eng = pick_engine(run_dir, engine)
    src = run_dir / "source"
    t0 = time.time()
    if eng == "text":
        f = _find(src, ("transcript.*",))
        if not f:
            raise runs.RunError("không có source/transcript.txt|md")
        paras = [p.strip() for p in f.read_text(encoding="utf-8").split("\n\n") if p.strip()]
        segs = [{"start": None, "end": None, "text": " ".join(p.split())} for p in paras]
    elif eng == "captions":
        f = _find(src, ("captions.*.vtt", "captions.*.srt"))
        if not f:
            raise runs.RunError("run này không có phụ đề — dùng engine openai hoặc whisper")
        segs = captions.parse_file(f)
    else:
        audio = _audio(src)
        if not audio:
            raise runs.RunError("run này chưa có audio (fetch_source với with_audio=true)")
        wav = src / "audio16k.wav"
        if not wav.exists():
            media.to_wav(audio, wav)
        segs = _openai(wav, run_dir, language) if eng == "openai" else _whisper(wav, language)

    if not segs:
        raise runs.RunError(f"engine {eng} không ra chữ nào")
    out = write_transcript(run_dir, segs, eng)
    out["seconds"] = round(time.time() - t0, 1)
    runs.record(run_dir, "transcribe", "transcribed", engine=eng, chars=out["chars"], seconds=out["seconds"])
    return out


def write_transcript(run_dir: Path, segs: list[dict], engine: str) -> dict[str, Any]:
    tdir = run_dir / "transcript"
    text = "\n".join(s["text"] for s in segs)
    runs.write_json(tdir / "transcript.json", {"engine": engine, "segments": segs, "chars": len(text)})
    # bản đọc: gộp đoạn thành khúc ~1.500 ký tự, mỗi khúc có mốc thời gian để Claude đọc dần
    lines, buf, start = [], [], None
    for s in segs:
        if start is None:
            start = s.get("start")
        buf.append(s["text"])
        if sum(len(b) for b in buf) > 1500:
            lines.append(_block(start, buf))
            buf, start = [], None
    if buf:
        lines.append(_block(start, buf))
    (tdir / "transcript.txt").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    return {"engine": engine, "segments": len(segs), "chars": len(text), "words": len(text.split()),
            "transcript_txt": str(tdir / "transcript.txt"), "transcript_json": str(tdir / "transcript.json"),
            "preview": text[:600]}


def _block(start: float | None, buf: list[str]) -> str:
    head = f"[{_hms(start)}] " if isinstance(start, (int, float)) else ""
    return head + " ".join(buf)


def _hms(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


# ---------------------------------------------------------------- OpenAI


def _openai(wav: Path, run_dir: Path, language: str) -> list[dict]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise runs.RunError("chưa đặt OPENAI_API_KEY")
    model = os.environ.get("AUDIO_STORY_OPENAI_STT_MODEL", "gpt-4o-transcribe")
    chunk_s = float(os.environ.get("AUDIO_STORY_STT_CHUNK_S", "600"))
    _, _, _, total = media.wav_info(wav)
    cache = run_dir / "transcript" / "chunks"
    cache.mkdir(parents=True, exist_ok=True)
    segs: list[dict] = []
    i, start = 0, 0.0
    with httpx.Client(timeout=600) as client:
        while start < total:
            dur = min(chunk_s, total - start)
            cached = cache / f"{i:04d}.json"
            if cached.exists():
                text = json.loads(cached.read_text(encoding="utf-8"))["text"]
            else:
                mp3 = cache / f"{i:04d}.mp3"
                media.wav_chunk_to_mp3(wav, mp3, start, dur)
                text = stt_openai_file(client, mp3, key=key, model=model, language=language)
                runs.write_json(cached, {"start": start, "end": start + dur, "text": text, "model": model})
                mp3.unlink(missing_ok=True)
            if text.strip():
                segs.append({"start": round(start, 3), "end": round(start + dur, 3), "text": " ".join(text.split())})
            i, start = i + 1, start + dur
    return segs


def stt_openai_file(client: httpx.Client, path: Path, *, key: str, model: str, language: str = "vi") -> str:
    with path.open("rb") as fh:
        r = client.post(OPENAI_URL, headers={"Authorization": f"Bearer {key}"},
                        data={"model": model, "language": language, "response_format": "json"},
                        files={"file": (path.name, fh, "audio/mpeg" if path.suffix == ".mp3" else "audio/wav")})
    if r.status_code >= 400:
        raise runs.RunError(f"OpenAI STT {r.status_code}: {r.text[:300]}")
    return r.json().get("text", "")


# ---------------------------------------------------------------- faster-whisper

_WHISPER = None


def _whisper_model():
    global _WHISPER
    if _WHISPER is None:
        if not has_whisper():
            raise runs.RunError("chưa cài faster-whisper: `uv sync --extra whisper` (hoặc dùng engine openai)")
        from faster_whisper import WhisperModel

        name = os.environ.get("AUDIO_STORY_WHISPER_MODEL", "large-v3-turbo")
        _WHISPER = WhisperModel(name, device="auto", compute_type=os.environ.get("AUDIO_STORY_WHISPER_COMPUTE", "int8"))
    return _WHISPER


def _pcm16k(path: Path):
    """Đọc audio thành float32 16 kHz mono cho faster-whisper — tự giải mã bằng ffmpeg + wave, không qua PyAV
    (faster-whisper 1.2 gọi ``av.open(metadata_errors=…)`` mà bản av mới đã bỏ)."""
    import tempfile

    import numpy as np

    if path.suffix == ".wav" and media.wav_info(path)[0] == 16_000:
        pcm, _ = media.read_pcm(path)
    else:
        with tempfile.TemporaryDirectory() as d:
            tmp = media.to_wav(path, Path(d) / "a.wav", rate=16_000)
            pcm, _ = media.read_pcm(tmp)
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def _whisper(wav: Path, language: str) -> list[dict]:
    segments, _ = _whisper_model().transcribe(_pcm16k(wav), language=language, vad_filter=True)
    return [{"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()} for s in segments if s.text.strip()]


def stt_clip(path: Path, engine: str = "auto", language: str = "vi") -> str:
    """Chép lại một đoạn audio ngắn (dùng cho ``qa_audio``)."""
    if engine == "auto":
        engine = "openai" if has_openai() else "whisper" if has_whisper() else ""
    if engine == "openai":
        model = os.environ.get("AUDIO_STORY_OPENAI_STT_MODEL", "gpt-4o-transcribe")
        with httpx.Client(timeout=120) as c:
            return stt_openai_file(c, path, key=os.environ["OPENAI_API_KEY"], model=model, language=language)
    if engine == "whisper":
        segments, _ = _whisper_model().transcribe(_pcm16k(path), language=language)
        return " ".join(s.text.strip() for s in segments)
    raise runs.RunError("qa_audio cần OPENAI_API_KEY hoặc faster-whisper")
