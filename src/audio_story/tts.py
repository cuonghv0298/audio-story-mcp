"""TTS qua server VieNeu-TTS (API giống OpenAI: ``POST /v1/audio/speech``, ``GET /v1/voices``).

Chép ý từ ``nova_culture_app/agent/vieneu_tts.py`` (29/10/2026): xin ``response_format=pcm`` + ``sample_rate`` cố định
rồi tự ghi WAV (server trả WAV «độ dài không biết trước» khi stream). Bỏ phần LiveKit.

Từ điển phát âm (``pronunciation.json``) chỉ áp cho chữ đưa vào TTS — kịch bản giữ nguyên (mẫu ``ai_voice.speak_text``).
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from . import media, runs
from .script import load_cast, load_script

MODEL = "vieneu-v3-turbo"


class TTSError(runs.RunError):
    pass


def base_url() -> str:
    return os.environ.get("VIENEU_URL", "http://127.0.0.1:8165").rstrip("/")


def _headers() -> dict[str, str]:
    key = os.environ.get("VIENEU_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


def health(timeout: float = 3.0) -> dict[str, Any]:
    try:
        r = httpx.get(f"{base_url()}/health", timeout=timeout)
        r.raise_for_status()
        return {"ok": True, "url": base_url(), **r.json()}
    except Exception as e:  # noqa: BLE001 — health chỉ báo trạng thái
        return {"ok": False, "url": base_url(), "error": str(e),
                "hint": "chạy `scripts/vieneu.sh run` (hoặc đặt VIENEU_URL tới server VieNeu khác)"}


def list_voices() -> list[dict[str, Any]]:
    try:
        r = httpx.get(f"{base_url()}/v1/voices", headers=_headers(), timeout=10)
    except httpx.HTTPError as e:
        raise TTSError(f"không gọi được VieNeu ở {base_url()}: {e}. Chạy `scripts/vieneu.sh run`.") from e
    if r.status_code >= 400:
        raise TTSError(f"VieNeu /v1/voices {r.status_code}: {r.text[:200]}")
    return [{k: v.get(k) for k in ("id", "description", "gender", "featured")} for v in r.json().get("data", [])]


def synth(text: str, voice: str, *, client: httpx.Client | None = None, rate: int = media.SAMPLE_RATE,
          retries: int = 3) -> bytes:
    """Đọc ``text`` bằng ``voice`` → PCM s16le mono ``rate`` Hz. Thử lại khi 429 (server CPU chỉ phục vụ 1 luồng)."""
    body = {"model": MODEL, "voice": voice, "input": text, "response_format": "pcm", "stream_format": "audio",
            "sample_rate": rate}
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(600, connect=10))
    try:
        for attempt in range(retries + 1):
            try:
                with client.stream("POST", f"{base_url()}/v1/audio/speech", json=body, headers=_headers()) as r:
                    if r.status_code == 429 and attempt < retries:
                        time.sleep(float(r.headers.get("Retry-After", "2")))
                        continue
                    if r.status_code >= 400:
                        r.read()
                        raise TTSError(f"VieNeu {r.status_code}: {r.text[:300]}")
                    return b"".join(r.iter_bytes())
            except httpx.TransportError as e:
                if attempt >= retries:
                    raise TTSError(f"không gọi được VieNeu ở {base_url()}: {e}") from e
                time.sleep(1 + attempt)
        raise TTSError("VieNeu bận (429) quá số lần thử")
    finally:
        if own:
            client.close()


# ---------------------------------------------------------------- phát âm


def load_pronunciation(run_dir: Path | None) -> list[dict[str, Any]]:
    if run_dir is None:
        return []
    p = run_dir / "pronunciation.json"
    if not p.exists():
        return []
    data = runs.read_json(p)
    rules = data.get("rules", []) if isinstance(data, dict) else data
    for r in rules:
        if not r.get("pattern") or "say" not in r:
            raise runs.RunError(f"pronunciation.json: mỗi luật cần 'pattern' và 'say' — lỗi ở {r}")
    return rules


def speak_text(text: str, rules: list[dict[str, Any]]) -> str:
    for r in rules:
        flags = 0 if r.get("case_sensitive") else re.IGNORECASE
        pat = r["pattern"] if r.get("regex") else r"(?<!\w)" + re.escape(r["pattern"]) + r"(?!\w)"
        text = re.sub(pat, r["say"], text, flags=flags)
    return text


# ---------------------------------------------------------------- preview / render


def preview(text: str, voice: str, out: Path, run_dir: Path | None = None) -> dict[str, Any]:
    spoken = speak_text(text, load_pronunciation(run_dir))
    t0 = time.time()
    pcm = synth(spoken, voice)
    media.write_wav(out, pcm)
    secs = len(pcm) / 2 / media.SAMPLE_RATE
    return {"file": str(out), "voice": voice, "spoken_text": spoken, "audio_s": round(secs, 2),
            "rtf": round((time.time() - t0) / secs, 2) if secs else None}


def _gate(run_dir: Path) -> None:
    chk = run_dir / "script" / "check.json"
    if not chk.exists():
        raise runs.RunError("chưa chạy check_script cho kịch bản này")
    for f in (run_dir / "script" / "script.json", run_dir / "story" / "cast.json"):
        if not f.exists():
            raise runs.RunError(f"chưa có {f.relative_to(run_dir)} — check_script còn lỗi")
    newest = max((run_dir / "script" / "script.json").stat().st_mtime, (run_dir / "story" / "cast.json").stat().st_mtime)
    if chk.stat().st_mtime < newest:
        raise runs.RunError("script.json/cast.json đã sửa sau lần check_script cuối — chạy lại check_script")
    if not runs.read_json(chk).get("ok"):
        raise runs.RunError("check_script còn lỗi — sửa kịch bản trước khi đọc (xem script/check.json)")


def _hash(spoken: str, voice: str) -> str:
    return hashlib.sha1(f"{MODEL}|{media.SAMPLE_RATE}|{voice}|{spoken}".encode()).hexdigest()[:16]


def render(run_dir: Path, *, segment_ids: list[int] | None = None, limit: int | None = None, workers: int = 1,
           force: bool = False) -> dict[str, Any]:
    """Đọc các đoạn của kịch bản bằng giọng thuyết minh → ``audio/seg_XXXXX.wav``. Đoạn đã đọc (cùng chữ + giọng) thì
    bỏ qua."""
    _gate(run_dir)
    cast, script = load_cast(run_dir), load_script(run_dir)
    rules = load_pronunciation(run_dir)
    adir = run_dir / "audio"
    mpath = adir / "manifest.json"
    manifest = runs.read_json(mpath) if mpath.exists() else {"segments": {}}
    segs = script.segments
    if segment_ids:
        want = set(segment_ids)
        segs = [s for s in segs if s.id in want]
    jobs, skipped = [], 0
    voice = cast.voice
    for s in segs:
        spoken = speak_text(s.text, rules)
        h = _hash(spoken, voice or "")
        f = adir / f"seg_{s.id:05d}.wav"
        old = manifest["segments"].get(str(s.id))
        if not force and old and old.get("hash") == h and f.exists():
            skipped += 1
            continue
        jobs.append((s, voice, spoken, h, f))
    if limit is not None:
        jobs = jobs[:limit]

    t0 = time.time()
    done: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    with httpx.Client(timeout=httpx.Timeout(600, connect=10)) as client:
        def work(job):
            s, voice, spoken, h, f = job
            t = time.time()
            pcm = synth(spoken, voice, client=client)
            media.write_wav(f, pcm)
            return s.id, {"file": f.name, "hash": h, "voice": voice,
                          "audio_s": round(len(pcm) / 2 / media.SAMPLE_RATE, 2), "synth_s": round(time.time() - t, 2)}

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = [(job, pool.submit(work, job)) for job in jobs]
            for job, fut in futures:
                try:
                    sid, entry = fut.result()
                    manifest["segments"][str(sid)] = entry
                    done.append(entry)
                    runs.write_json(mpath, manifest)  # ghi sau mỗi đoạn để bị ngắt vẫn chạy tiếp được
                except Exception as e:  # noqa: BLE001 — một đoạn lỗi không dừng cả truyện
                    failed.append({"segment": job[0].id, "error": str(e)})
    manifest["updated_at"] = runs.now()
    runs.write_json(mpath, manifest)

    total_ids = {s.id for s in script.segments}
    have = {int(k) for k, v in manifest["segments"].items() if (adir / v["file"]).exists()} & total_ids
    audio_s = sum(e["audio_s"] for e in done)
    wall = time.time() - t0
    result = {"rendered": len(done), "skipped": skipped, "failed": failed, "remaining": len(total_ids - have),
              "total_segments": len(total_ids), "audio_s": round(audio_s, 1), "wall_s": round(wall, 1),
              "rtf": round(wall / audio_s, 2) if audio_s else None, "manifest": str(mpath)}
    runs.record(run_dir, "tts_render", "rendered" if not result["remaining"] else "rendering",
                rendered=len(done), failed=len(failed), remaining=result["remaining"])
    return result
