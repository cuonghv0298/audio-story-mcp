from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

from audio_story import media, runs


@pytest.fixture(autouse=True)
def _runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_STORY_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("VIENEU_URL", "http://127.0.0.1:9")  # không bao giờ gọi server thật trong test
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


TRANSCRIPT = (
    "Lâm Phong bước vào Thanh Vân Môn. Sư phụ Bạch Vân nhìn hắn rồi nói rằng con đường tu tiên rất dài và gian khổ. "
    "Lâm Phong cúi đầu đáp lời, trong lòng thầm thề sẽ bảo vệ tiểu sư muội Tô Nhi đến cùng."
)


def make_run(tmp_path: Path, *, cast: dict | None = None, script: dict | None = None, transcript: str = TRANSCRIPT) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "src.txt"
    src.write_text(transcript, encoding="utf-8")
    from audio_story import source, stt

    run = Path(source.fetch(str(src), title="Thử nghiệm")["run_dir"])
    stt.transcribe(run, "text")
    if cast is not None:
        runs.write_json(run / "story" / "cast.json", cast)
    if script is not None:
        runs.write_json(run / "script" / "script.json", script)
    return run


GOOD_CAST = {
    "narrator": {"voice": "Quỳnh Anh"},
    "characters": [
        {"id": "c1", "old_names": ["Lâm Phong"], "new_name": "Trần Khải", "gender": "nam"},
        {"id": "c2", "old_names": ["Bạch Vân"], "new_name": "Hàn Sơn", "gender": "nam"},
        {"id": "c3", "old_names": ["Tô Nhi"], "new_name": "Diệp Lam", "gender": "nữ"},
    ],
    "other_names": [{"old_names": ["Thanh Vân Môn"], "new_name": "Lạc Hà Cốc"}],
}

GOOD_SCRIPT = {
    "title": "Lạc Hà Cốc",
    "segments": [
        {"id": 1, "text": "Chiều mưa, Trần Khải dừng chân trước cổng Lạc Hà Cốc.", "chapter": "Chương 1"},
        {"id": 2, "text": "Hàn Sơn hỏi: ngươi đến đây vì điều gì?", "pause_after_ms": 600},
        {"id": 3, "text": "Trần Khải đáp rằng muốn học cách giữ lời hứa với một người.", "chapter": "Chương 1"},
        {"id": 4, "text": "Diệp Lam dặn huynh nhớ quay về sớm.", "chapter": "Chương 2"},
    ],
}


def tone_pcm(seconds: float, rate: int = media.SAMPLE_RATE, freq: float = 440.0) -> bytes:
    n = int(seconds * rate)
    return b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))
