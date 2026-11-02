"""CLI ``audio-story``: kiểm môi trường và chạy từng bước không qua Claude (hữu ích cho bước dài như STT/TTS cả truyện).

    audio-story doctor [--hook]
    audio-story fetch <url|file> [--title T] [--no-audio]
    audio-story transcribe <run> [--engine auto|captions|text|openai|whisper]
    audio-story chapters <run>
    audio-story check <run>
    audio-story voices
    audio-story preview "<câu>" --voice "<giọng>" [--run <run>]
    audio-story render <run> [--limit N] [--workers N] [--force]
    audio-story qa <run> [--engine …] [--limit N]
    audio-story assemble <run> [--format mp3|wav] [--allow-missing]
    audio-story status <run>
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from typing import Any

from . import __version__, assemble, chapters, media, qa, runs, script, stt, tts
from . import source as source_mod


def doctor_report() -> dict[str, Any]:
    checks: dict[str, Any] = {"version": __version__}
    try:
        checks["ffmpeg"] = {"ok": True, "path": media.ffmpeg_exe(), "system": bool(shutil.which("ffmpeg"))}
    except media.MediaError as e:
        checks["ffmpeg"] = {"ok": False, "error": str(e)}
    try:
        import yt_dlp.version

        checks["yt_dlp"] = {"ok": True, "version": yt_dlp.version.__version__}
    except Exception as e:  # noqa: BLE001 — doctor báo mọi lỗi import
        checks["yt_dlp"] = {"ok": False, "error": str(e)}
    checks["stt"] = {"openai": stt.has_openai(), "whisper": stt.has_whisper(), "captions": True}
    checks["vieneu"] = tts.health()
    checks["runs_root"] = str(runs.runs_root())
    checks["ok"] = checks["ffmpeg"]["ok"] and checks["yt_dlp"]["ok"]
    return checks


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="audio-story", description="audio-story-mcp CLI")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor")
    d.add_argument("--hook", action="store_true", help="chế độ hook SessionStart: chỉ in khi có vấn đề")
    f = sub.add_parser("fetch")
    f.add_argument("source")
    f.add_argument("--title")
    f.add_argument("--no-audio", action="store_true")
    t = sub.add_parser("transcribe")
    t.add_argument("run")
    t.add_argument("--engine", default="auto", choices=stt.ENGINES)
    sc = sub.add_parser("chapters")
    sc.add_argument("run")
    c = sub.add_parser("check")
    c.add_argument("run")
    sub.add_parser("voices")
    p = sub.add_parser("preview")
    p.add_argument("text")
    p.add_argument("--voice", required=True)
    p.add_argument("--run")
    r = sub.add_parser("render")
    r.add_argument("run")
    r.add_argument("--limit", type=int)
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--force", action="store_true")
    q = sub.add_parser("qa")
    q.add_argument("run")
    q.add_argument("--engine", default="auto")
    q.add_argument("--limit", type=int)
    a = sub.add_parser("assemble")
    a.add_argument("run")
    a.add_argument("--format", default="mp3", choices=assemble.FORMATS)
    a.add_argument("--allow-missing", action="store_true")
    s = sub.add_parser("status")
    s.add_argument("run")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "doctor":
            rep = doctor_report()
            if args.hook:
                msgs = []
                if not rep["ok"]:
                    msgs.append("ffmpeg/yt-dlp chưa sẵn sàng — chạy `audio-story doctor`.")
                if not rep["vieneu"]["ok"]:
                    msgs.append(f"VieNeu-TTS chưa chạy ở {rep['vieneu']['url']} (cần cho tts_*): `scripts/vieneu.sh run`.")
                if msgs:
                    print("audio-story: " + " ".join(msgs))
                return 0
            _print(rep)
            return 0 if rep["ok"] else 1
        if args.cmd == "fetch":
            _print(source_mod.fetch(args.source, title=args.title, with_audio=not args.no_audio))
        elif args.cmd == "transcribe":
            _print(stt.transcribe(runs.resolve(args.run), args.engine))
        elif args.cmd == "chapters":
            _print(chapters.split(runs.resolve(args.run)))
        elif args.cmd == "check":
            p = runs.resolve(args.run)
            try:
                known = [v["id"] for v in tts.list_voices()]
            except runs.RunError:
                known = None
            res = script.check(p, known_voices=known)
            if res["ok"] or not any(e["code"] == "schema" for e in res["errors"]):
                script.render_markdown(p)
            _print(res)
            return 0 if res["ok"] else 1
        elif args.cmd == "voices":
            _print(tts.list_voices())
        elif args.cmd == "preview":
            p = runs.resolve(args.run) if args.run else None
            out = (p / "audio" / "preview" if p else runs.runs_root() / "_preview") / f"preview-{args.voice}.wav"
            _print(tts.preview(args.text, args.voice, out, p))
        elif args.cmd == "render":
            _print(tts.render(runs.resolve(args.run), limit=args.limit, workers=args.workers, force=args.force))
        elif args.cmd == "qa":
            _print(qa.qa(runs.resolve(args.run), engine=args.engine, limit=args.limit))
        elif args.cmd == "assemble":
            _print(assemble.assemble(runs.resolve(args.run), fmt=args.format, allow_missing=args.allow_missing))
        elif args.cmd == "status":
            pth = runs.resolve(args.run)
            fl = runs.files(pth)
            _print({"run_dir": str(pth), **runs.load(pth), "files": fl, "next": runs.next_step(fl)})
    except runs.RunError as e:
        print(f"lỗi: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

