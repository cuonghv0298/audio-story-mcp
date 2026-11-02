import copy
import os
import time

from audio_story import runs, script

from .conftest import GOOD_CAST, GOOD_SCRIPT, TRANSCRIPT, make_run


def codes(res, kind="errors"):
    return sorted({i["code"] for i in res[kind]})


def test_good_script_passes(tmp_path):
    run = make_run(tmp_path, cast=GOOD_CAST, script=GOOD_SCRIPT)
    res = script.check(run, known_voices=["Quỳnh Anh", "Thanh Bình"])
    assert res["ok"], res["errors"]
    assert res["warnings"] == []
    assert res["stats"]["segments"] == 4
    assert (run / "script" / "check.json").exists()


def test_old_name_leak_detected_without_accents(tmp_path):
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"][0]["text"] = "Chiều mưa, LAM PHONG dừng chân."
    s["segments"][1]["text"] = "Thanh Van Mon đã đóng cửa."
    run = make_run(tmp_path, cast=GOOD_CAST, script=s)
    res = script.check(run)
    leaks = [e for e in res["errors"] if e["code"] == "old_name_leak"]
    assert {e["segment"] for e in leaks} == {1, 2}
    assert not res["ok"]


def test_old_name_in_title_detected(tmp_path):
    s = copy.deepcopy(GOOD_SCRIPT)
    s["title"] = "Truyền thuyết Tô Nhi"
    run = make_run(tmp_path, cast=GOOD_CAST, script=s)
    assert "old_name_leak" in codes(script.check(run))


def test_no_false_positive_on_substring(tmp_path):
    cast = copy.deepcopy(GOOD_CAST)
    cast["characters"][2]["old_names"] = ["Lan"]
    cast["characters"][2]["new_name"] = "Lan Anh"  # tên mới chứa tên cũ → không báo
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"][3]["text"] = "Lan Anh cười. Hoa lan nở. Cô Lanh lợi."
    run = make_run(tmp_path, cast=cast, script=s)
    assert "old_name_leak" not in codes(script.check(run))
    # nhưng «Lan» đứng riêng, viết hoa → vẫn là tên gốc bị sót
    s["segments"][3]["text"] = "Lan Anh cười. Lan bảo: đi thôi."
    runs.write_json(run / "script" / "script.json", s)
    leaks = [e for e in script.check(run)["errors"] if e["code"] == "old_name_leak"]
    assert len(leaks) == 1 and "Lan bảo" in leaks[0]["context"]


def test_leak_with_lowercase_title_words(tmp_path):
    cast = copy.deepcopy(GOOD_CAST)
    cast["other_names"].append({"old_names": ["Tiêu Sư Bá"], "new_name": "Văn sư bá"})
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"][1]["text"] = "Nếu Tiêu sư bá biết chuyện này thì sao?"
    run = make_run(tmp_path, cast=cast, script=s)
    assert "old_name_leak" in codes(script.check(run))


def test_missing_voice_and_empty_text(tmp_path):
    cast = copy.deepcopy(GOOD_CAST)
    cast["narrator"]["voice"] = ""
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"].append({"id": 10, "text": "   "})
    run = make_run(tmp_path, cast=cast, script=s)
    assert codes(script.check(run)) == ["empty_text", "voice_missing"]


def test_extra_fields_ignored(tmp_path):
    """Kịch bản cũ có `speaker` / nhân vật có `voice` vẫn đọc được (bỏ qua) — cả truyện một giọng."""
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"][1]["speaker"] = "c2"
    cast = copy.deepcopy(GOOD_CAST)
    cast["characters"][0]["voice"] = "Thanh Bình"
    run = make_run(tmp_path, cast=cast, script=s)
    assert script.check(run)["ok"]


def test_schema_errors(tmp_path):
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"][1]["id"] = 1  # trùng id
    run = make_run(tmp_path, cast=GOOD_CAST, script=s)
    res = script.check(run)
    assert codes(res) == ["schema"]
    run2 = make_run(tmp_path / "b", cast={"narrator": {}, "characters": [{"id": "narrator", "new_name": "X"}]},
                    script=GOOD_SCRIPT)
    assert "schema" in codes(script.check(run2))


def test_missing_files(tmp_path):
    run = make_run(tmp_path)
    res = script.check(run)
    assert codes(res) == ["schema"] and len(res["errors"]) == 2


def test_high_overlap_warning(tmp_path):
    s = copy.deepcopy(GOOD_SCRIPT)
    # chép nguyên văn bản gốc (đã đổi tên) → trùng nhiều cụm 6 từ
    copied = TRANSCRIPT.replace("Lâm Phong", "Trần Khải").replace("Bạch Vân", "Hàn Sơn").replace("Tô Nhi", "Diệp Lam")
    copied = copied.replace("Thanh Vân Môn", "Lạc Hà Cốc")
    s["segments"] = [{"id": 1, "speaker": "narrator", "text": copied}]
    run = make_run(tmp_path, cast=GOOD_CAST, script=s)
    res = script.check(run)
    assert res["ok"]
    assert "high_overlap" in codes(res, "warnings")
    assert res["stats"]["overlap"] > 0.35
    res2 = script.check(run, max_overlap=0.99)
    assert "high_overlap" not in codes(res2, "warnings")


def test_warnings_collision_long_unknown_voice(tmp_path):
    cast = copy.deepcopy(GOOD_CAST)
    cast["narrator"]["voice"] = "Giọng Lạ"
    cast["characters"][2]["new_name"] = "Bạch Vân"  # trùng tên gốc của c2
    s = copy.deepcopy(GOOD_SCRIPT)
    s["segments"][0]["text"] = "Trời mưa. " * 200
    run = make_run(tmp_path, cast=cast, script=s)
    res = script.check(run, known_voices=["Quỳnh Anh", "Thanh Bình"])
    assert set(codes(res, "warnings")) == {"new_name_collision", "segment_too_long", "voice_unknown"}


def test_render_markdown(tmp_path):
    run = make_run(tmp_path, cast=GOOD_CAST, script=GOOD_SCRIPT)
    md = script.render_markdown(run).read_text(encoding="utf-8")
    assert "## Chương 1" in md and "## Chương 2" in md
    assert "Giọng thuyết minh: **Quỳnh Anh**" in md
    assert "| c1 | Trần Khải | Lâm Phong |" in md
    assert "`2` Hàn Sơn hỏi" in md


def test_check_records_history(tmp_path):
    run = make_run(tmp_path, cast=GOOD_CAST, script=GOOD_SCRIPT)
    script.check(run)
    data = runs.load(run)
    assert data["status"] == "checked"
    assert data["history"][-1]["step"] == "check_script"
    # sửa script sau khi check → tts gate phải đòi check lại (kiểm ở test_tts)
    time.sleep(0.01)
    os.utime(run / "script" / "script.json")
