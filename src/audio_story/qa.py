"""``qa_audio``: STT nghe lại từng đoạn TTS, tính CER so với chữ đã đưa vào TTS — đánh dấu đoạn cần đọc lại.

Ý từ Audio-Truyen (kiểm bằng ASR) và nghiên cứu VieNeu ở nova_culture_app (kiểm độ rõ bằng STT, 29/10/2026).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import runs, stt, tts
from .script import load_script
from .textnorm import cer

DEFAULT_MAX_CER = 0.15


def qa(run_dir: Path, *, engine: str = "auto", max_cer: float = DEFAULT_MAX_CER, segment_ids: list[int] | None = None,
       limit: int | None = None) -> dict[str, Any]:
    script = load_script(run_dir)
    rules = tts.load_pronunciation(run_dir)
    adir = run_dir / "audio"
    manifest = runs.read_json(adir / "manifest.json")
    rpath = run_dir / "qa" / "report.json"
    report = runs.read_json(rpath) if rpath.exists() else {"segments": {}}
    segs = [s for s in script.segments if str(s.id) in manifest["segments"]]
    if segment_ids:
        segs = [s for s in segs if s.id in set(segment_ids)]
    todo = [s for s in segs if report["segments"].get(str(s.id), {}).get("hash") != manifest["segments"][str(s.id)]["hash"]]
    if limit is not None:
        todo = todo[:limit]
    for s in todo:
        entry = manifest["segments"][str(s.id)]
        heard = stt.stt_clip(adir / entry["file"], engine)
        expected = tts.speak_text(s.text, rules)
        report["segments"][str(s.id)] = {"hash": entry["hash"], "cer": round(cer(expected, heard), 3),
                                         "heard": heard, "expected": expected}
        runs.write_json(rpath, report)
    bad = sorted((int(k), v["cer"]) for k, v in report["segments"].items() if v["cer"] > max_cer)
    report.update(max_cer=max_cer, checked=len(report["segments"]), bad=[{"segment": k, "cer": c} for k, c in bad],
                  updated_at=runs.now())
    runs.write_json(rpath, report)
    runs.record(run_dir, "qa_audio", "qa_done", checked=len(todo), bad=len(bad))
    return {"checked_now": len(todo), "checked_total": report["checked"], "bad": report["bad"], "report": str(rpath),
            "hint": "đoạn CER cao: thêm luật vào pronunciation.json hoặc sửa chữ, rồi tts_render segment_ids=[…]"}
