from pathlib import Path

import pytest

from audio_story import captions, runs, source, stt

VTT_AUTO = """WEBVTT
Kind: captions
Language: vi

00:00:00.000 --> 00:00:02.000 align:start position:0%
xin<00:00:00.500><c> chào</c><00:00:01.000><c> các</c><00:00:01.500><c> bạn</c>

00:00:02.000 --> 00:00:02.010 align:start position:0%
xin chào các bạn


00:00:02.010 --> 00:00:04.000 align:start position:0%
xin chào các bạn
hôm<00:00:02.500><c> nay</c><00:00:03.000><c> kể</c><00:00:03.500><c> chuyện</c>
"""

SRT = """1
00:00:01,000 --> 00:00:02,500
Dòng một &amp; hai

2
00:00:03,000 --> 00:00:04,000
<i>Dòng ba</i>
"""


def test_parse_vtt_dedupes_rolling_lines():
    segs = captions.parse(VTT_AUTO)
    assert [s["text"] for s in segs] == ["xin chào các bạn", "hôm nay kể chuyện"]
    assert segs[1]["start"] == 2.01


def test_parse_srt():
    segs = captions.parse(SRT)
    assert segs == [{"start": 1.0, "end": 2.5, "text": "Dòng một & hai"}, {"start": 3.0, "end": 4.0, "text": "Dòng ba"}]


def test_fetch_text_file_then_transcribe(tmp_path):
    f = tmp_path / "truyen.txt"
    f.write_text("Đoạn một.\n\nĐoạn hai dài hơn.\n", encoding="utf-8")
    out = source.fetch(str(f))
    run = Path(out["run_dir"])
    assert run.parent == runs.runs_root()
    assert stt.pick_engine(run, "auto") == "text"
    res = stt.transcribe(run)
    assert res["segments"] == 2
    assert (run / "transcript" / "transcript.txt").read_text(encoding="utf-8").startswith("Đoạn một.")
    hist = runs.load(run)["history"]
    assert [h["step"] for h in hist] == ["fetch_source", "transcribe"]


def test_fetch_vtt_file_uses_captions(tmp_path):
    f = tmp_path / "sub.vtt"
    f.write_text(VTT_AUTO, encoding="utf-8")
    run = Path(source.fetch(str(f))["run_dir"])
    assert stt.pick_engine(run, "auto") == "captions"
    assert stt.transcribe(run)["segments"] == 2


def test_auto_engine_without_anything_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(stt, "has_whisper", lambda: False)
    f = tmp_path / "a.wav"
    from audio_story import media

    media.write_wav(f, b"\x00\x00" * 100)
    run = Path(source.fetch(str(f))["run_dir"])
    with pytest.raises(runs.RunError, match="không có engine STT"):
        stt.pick_engine(run, "auto")


def test_unknown_extension(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF")
    with pytest.raises(runs.RunError, match="chưa hỗ trợ"):
        source.fetch(str(f))


def test_resolve_by_name_and_path(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("a", encoding="utf-8")
    run = Path(source.fetch(str(f))["run_dir"])
    assert runs.resolve(str(run)) == run
    assert runs.resolve(run.name) == run
    with pytest.raises(runs.RunError):
        runs.resolve("khong-co")


def test_pick_sub_prefers_manual():
    info = {"subtitles": {"vi": []}, "automatic_captions": {"vi-orig": []}}
    assert source._pick_sub(info) == ("vi", False)
    assert source._pick_sub({"automatic_captions": {"vi-orig": [], "en": []}}) == ("vi-orig", True)
    assert source._pick_sub({"automatic_captions": {"en": []}}) is None
