import copy
import os
import time
from pathlib import Path

import pytest

from audio_story import assemble, media, runs, script, tts

from .conftest import GOOD_CAST, GOOD_SCRIPT, make_run, tone_pcm


@pytest.fixture
def fake_synth(monkeypatch):
    calls = []

    def synth(text, voice, *, client=None, rate=media.SAMPLE_RATE, retries=3):
        calls.append((text, voice))
        return tone_pcm(0.2 + len(text) / 500)

    monkeypatch.setattr(tts, "synth", synth)
    return calls


def checked_run(tmp_path, **kw):
    run = make_run(tmp_path, cast=kw.get("cast", GOOD_CAST), script=kw.get("script", GOOD_SCRIPT))
    res = script.check(run)
    assert res["ok"], res["errors"]
    return run


def test_speak_text_rules():
    rules = [{"pattern": "AI", "say": "ây ai"}, {"pattern": r"(\d+)%", "say": r"\1 phần trăm", "regex": True}]
    assert tts.speak_text("Culture AI tăng 12% nhưng AIM thì không", rules) == \
        "Culture ây ai tăng 12 phần trăm nhưng AIM thì không"


def test_render_gate_requires_check(tmp_path, fake_synth):
    run = make_run(tmp_path, cast=GOOD_CAST, script=GOOD_SCRIPT)
    with pytest.raises(runs.RunError, match="chưa chạy check_script"):
        tts.render(run)
    script.check(run)
    future = time.time() + 5
    os.utime(run / "script" / "script.json", (future, future))
    with pytest.raises(runs.RunError, match="chạy lại check_script"):
        tts.render(run)


def test_render_gate_blocks_errors(tmp_path, fake_synth):
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"][0]["text"] = "Lâm Phong đến."
    run = make_run(tmp_path, cast=GOOD_CAST, script=s)
    script.check(run)
    with pytest.raises(runs.RunError, match="còn lỗi"):
        tts.render(run)


def test_render_one_voice_pronunciation_and_resume(tmp_path, fake_synth):
    run = checked_run(tmp_path)
    runs.write_json(run / "pronunciation.json", {"rules": [{"pattern": "Lạc Hà Cốc", "say": "Lạc Hà Cốc ạ"}]})
    res = tts.render(run, limit=2)
    assert res["rendered"] == 2 and res["remaining"] == 2
    assert fake_synth[0] == ("Chiều mưa, Trần Khải dừng chân trước cổng Lạc Hà Cốc ạ.", "Quỳnh Anh")
    res = tts.render(run)
    assert res["rendered"] == 2 and res["skipped"] == 2 and res["remaining"] == 0
    assert {v for _, v in fake_synth} == {"Quỳnh Anh"} and len(fake_synth) == 4
    # sửa chữ 1 đoạn → chỉ đọc lại đoạn đó
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"][3]["text"] = "Diệp Lam dặn huynh nhớ quay về trước Tết."
    runs.write_json(run / "script" / "script.json", s)
    script.check(run)
    res = tts.render(run)
    assert res["rendered"] == 1 and fake_synth[-1][0] == "Diệp Lam dặn huynh nhớ quay về trước Tết."
    # đổi giọng thuyết minh → đọc lại tất cả
    cast = copy.deepcopy(GOOD_CAST)
    cast["narrator"]["voice"] = "Mỹ Duyên"
    runs.write_json(run / "story" / "cast.json", cast)
    script.check(run)
    assert tts.render(run)["rendered"] == 4


def test_render_reports_failures(tmp_path, monkeypatch):
    run = checked_run(tmp_path)

    def boom(text, voice, **kw):
        if text.startswith("Hàn Sơn"):
            raise tts.TTSError("VieNeu 400: unknown voice")
        return tone_pcm(0.1)

    monkeypatch.setattr(tts, "synth", boom)
    res = tts.render(run)
    assert res["rendered"] == 3 and res["remaining"] == 1
    assert res["failed"][0]["segment"] == 2


def test_assemble_mp3_with_pauses_and_chapters(tmp_path, fake_synth):
    run = checked_run(tmp_path)
    with pytest.raises(runs.RunError, match="chưa đọc"):
        assemble.assemble(run)
    tts.render(run)
    res = assemble.assemble(run, fmt="mp3")
    assert Path(res["mp3"]).stat().st_size > 1000
    _, _, _, secs = media.wav_info(Path(res["wav"]))
    seg_s = sum(e["audio_s"] for e in runs.read_json(run / "audio" / "manifest.json")["segments"].values())
    pauses = (0.5 + 0.35 + 0.6 + 0.35 + 0.35 + assemble.CHAPTER_PAUSE_MS / 1000)
    assert abs(secs - (seg_s + pauses)) < 0.05
    assert [c["title"] for c in res["chapters"]] == ["Chương 1", "Chương 2"]
    assert runs.load(run)["status"] == "assembled"


def test_assemble_allow_missing(tmp_path, fake_synth):
    run = checked_run(tmp_path)
    tts.render(run, limit=1)
    res = assemble.assemble(run, fmt="wav", allow_missing=True)
    assert res["missing_segments"] == [2, 3, 4]
    assert "mp3" not in res


def test_run_status_next_step(tmp_path, fake_synth):
    run = make_run(tmp_path)
    assert runs.next_step(runs.files(run)).startswith("write_story")
    runs.write_json(run / "story" / "cast.json", GOOD_CAST)
    runs.write_json(run / "script" / "script.json", GOOD_SCRIPT)
    assert runs.next_step(runs.files(run)) == "check_script"
    script.check(run)
    assert runs.next_step(runs.files(run)).startswith("user_review")
    tts.render(run)
    assert runs.next_step(runs.files(run)) == "assemble"
    assemble.assemble(run, fmt="wav")
    assert runs.next_step(runs.files(run)) == "done"
