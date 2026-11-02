"""ffmpeg + WAV. ffmpeg lấy từ PATH, không có thì dùng binary đi kèm ``imageio-ffmpeg`` (không cần cài hệ thống)."""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from functools import lru_cache
from pathlib import Path

SAMPLE_RATE = 24_000  # mọi đoạn TTS ghi ở 24 kHz mono s16le
SAMPLE_WIDTH = 2


class MediaError(Exception):
    pass


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    env = os.environ.get("AUDIO_STORY_FFMPEG")
    if env:
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover - phụ thuộc máy
        raise MediaError("không tìm thấy ffmpeg (cài `brew install ffmpeg` hoặc gói imageio-ffmpeg)") from e


def run_ffmpeg(*args: str) -> None:
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise MediaError(f"ffmpeg lỗi ({proc.returncode}): {proc.stderr.strip()[-800:]}")


def to_wav(src: Path, dst: Path, rate: int = 16_000) -> Path:
    """Đổi mọi định dạng audio về WAV mono s16le ``rate`` Hz (dùng cho STT)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg("-i", str(src), "-vn", "-ac", "1", "-ar", str(rate), "-sample_fmt", "s16", str(dst))
    return dst


def wav_to_mp3(src: Path, dst: Path, *, loudnorm: bool = True, bitrate: str = "128k") -> Path:
    af = ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"] if loudnorm else []
    run_ffmpeg("-i", str(src), *af, "-ac", "1", "-codec:a", "libmp3lame", "-b:a", bitrate, str(dst))
    return dst


def wav_chunk_to_mp3(src: Path, dst: Path, start: float, duration: float, bitrate: str = "64k") -> Path:
    run_ffmpeg("-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src), "-ac", "1", "-codec:a", "libmp3lame",
               "-b:a", bitrate, str(dst))
    return dst


def wav_info(path: Path) -> tuple[int, int, int, float]:
    """(sample_rate, channels, sample_width, giây)."""
    with wave.open(str(path), "rb") as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
    return rate, ch, width, n / rate if rate else 0.0


def write_wav(path: Path, pcm: bytes, rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(rate)
        w.writeframes(pcm)
    tmp.replace(path)


def read_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != SAMPLE_WIDTH:
            raise MediaError(f"{path}: cần WAV mono 16-bit")
        return w.readframes(w.getnframes()), w.getframerate()


def silence(ms: int, rate: int = SAMPLE_RATE) -> bytes:
    return b"\x00\x00" * int(rate * max(ms, 0) / 1000)
