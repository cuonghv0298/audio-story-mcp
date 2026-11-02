"""Ghép các đoạn TTS theo thứ tự kịch bản + khoảng nghỉ ``pause_after_ms`` → ``out/story.wav`` → ``out/story.mp3``."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from . import media, runs
from .script import load_script

CHAPTER_PAUSE_MS = 1500
FORMATS = ("mp3", "wav")


def assemble(run_dir: Path, *, fmt: str = "mp3", lead_in_ms: int = 500, loudnorm: bool = True,
             allow_missing: bool = False) -> dict[str, Any]:
    if fmt not in FORMATS:
        raise runs.RunError(f"format phải là {FORMATS}")
    script = load_script(run_dir)
    adir = run_dir / "audio"
    manifest = runs.read_json(adir / "manifest.json") if (adir / "manifest.json").exists() else {"segments": {}}
    missing = [s.id for s in script.segments
               if not (e := manifest["segments"].get(str(s.id))) or not (adir / e["file"]).exists()]
    if missing and not allow_missing:
        raise runs.RunError(f"còn {len(missing)} đoạn chưa đọc (vd. {missing[:10]}) — chạy tts_render, "
                            "hoặc allow_missing=true để ghép bản nháp")

    out_dir = run_dir / "out"
    out_dir.mkdir(exist_ok=True)
    wav_path = out_dir / "story.wav"
    rate = media.SAMPLE_RATE
    chapters: list[dict[str, Any]] = []
    pos = 0  # số mẫu đã ghi
    tmp = wav_path.with_suffix(".tmp.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(media.SAMPLE_WIDTH)
        w.setframerate(rate)
        w.writeframes(media.silence(lead_in_ms, rate))
        pos += int(rate * lead_in_ms / 1000)
        prev_chapter = None
        for s in script.segments:
            if s.id in missing:
                continue
            if s.chapter and s.chapter != prev_chapter:
                if prev_chapter is not None:
                    w.writeframes(media.silence(CHAPTER_PAUSE_MS, rate))
                    pos += int(rate * CHAPTER_PAUSE_MS / 1000)
                chapters.append({"title": s.chapter, "start_s": round(pos / rate, 2)})
                prev_chapter = s.chapter
            pcm, r = media.read_pcm(adir / manifest["segments"][str(s.id)]["file"])
            if r != rate:
                raise runs.RunError(f"đoạn {s.id} có sample rate {r} ≠ {rate}")
            w.writeframes(pcm)
            pause = media.silence(s.pause_after_ms, rate)
            w.writeframes(pause)
            pos += len(pcm) // 2 + len(pause) // 2
    tmp.replace(wav_path)

    result: dict[str, Any] = {"wav": str(wav_path), "duration_s": round(pos / rate, 1), "chapters": chapters,
                              "missing_segments": missing}
    if fmt == "mp3":
        mp3 = media.wav_to_mp3(wav_path, out_dir / "story.mp3", loudnorm=loudnorm)
        result["mp3"] = str(mp3)
        result["mp3_mb"] = round(mp3.stat().st_size / 1e6, 2)
    runs.write_json(out_dir / "chapters.json", chapters)
    runs.record(run_dir, "assemble", "assembled", duration_s=result["duration_s"], format=fmt,
                missing=len(missing))
    return result
