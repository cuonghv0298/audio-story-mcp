from pathlib import Path

from audio_story import chapters, runs, source, stt


def test_find_marks_keeps_increasing_only():
    text = "đuôi chương trước. Chương 12 Mở đầu. như ở chương 3 đã kể. Chương 12 lặp. Chương 13 Tiếp."
    assert [n for n, _ in chapters.find_marks(text)] == [12, 13]


def test_split_writes_files(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("đuôi chương trước.\n\nChương 219 Của ta. Nàng cười.\n\nNhư chương 5 đã kể.\n\nChương 220 Gió nổi. Hết.",
                 encoding="utf-8")
    run = Path(source.fetch(str(f))["run_dir"])
    stt.transcribe(run, "text")
    res = chapters.split(run)
    assert res["count"] == 2
    assert [c["chapter"] for c in res["chapters"]] == [None, 219, 220]
    body = Path(res["chapters"][1]["file"]).read_text(encoding="utf-8")
    assert body.startswith("Chương 219 Của ta.") and "chương 5" in body and "220" not in body
    assert runs.load(run)["history"][-1]["step"] == "split_chapters"


def test_split_without_marks(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("Truyện ngắn không có chương.", encoding="utf-8")
    run = Path(source.fetch(str(f))["run_dir"])
    stt.transcribe(run, "text")
    res = chapters.split(run)
    assert res["count"] == 0 and res["chapters"][0]["file"].endswith("phan-dau.txt")
