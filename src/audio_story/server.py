"""MCP server ``audio-story`` (stdio) — tool tất định cho quy trình truyện audio. Không gọi LLM: Claude Code viết
story bible / cast / kịch bản; server tải, chép lời, kiểm, đọc TTS và ghép.

Chạy:  ``uv run audio-story-mcp``  (Claude Code tự chạy qua ``.mcp.json`` của plugin).
SDK ``mcp`` v2 (``MCPServer``) như reuse-agent-server; tool đồng bộ được SDK chạy trong thread.
"""

from __future__ import annotations

import functools
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from . import __version__, assemble, qa, runs, script, stt, tts
from . import source as source_mod

INSTRUCTIONS = """Tool cho quy trình truyện audio: link YouTube → transcript → (Claude viết story_bible, cast, script) →
check_script → người dùng duyệt → tts_render → assemble. Mọi file nằm trong một thư mục run; tool nhận `run`
(đường dẫn thư mục run do fetch_source trả về). Dùng skill `audio-story` để biết quy trình và định dạng file."""

mcp = MCPServer("audio-story", version=__version__, instructions=INSTRUCTIONS)


def _tool(fn):
    """Đổi lỗi người dùng sửa được thành ``ToolError`` (thông điệp rõ ràng cho Claude)."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (runs.RunError, ValidationError, FileNotFoundError) as e:
            raise ToolError(str(e)) from e

    return mcp.tool()(wrapper)


@_tool
def fetch_source(source: str, title: str | None = None, with_audio: bool = True) -> dict[str, Any]:
    """Tạo thư mục run mới từ link YouTube (tải audio + metadata + phụ đề tiếng Việt nếu có) hoặc từ file trên máy
    (audio .mp3/.m4a/.wav…, phụ đề .vtt/.srt, hay transcript .txt/.md). Trả `run_dir` để dùng cho các tool sau.
    with_audio=false: chỉ lấy metadata + phụ đề (nhanh, khi chắc chắn phụ đề đủ tốt)."""
    return source_mod.fetch(source, title=title, with_audio=with_audio)


@_tool
def transcribe(run: str, engine: str = "auto", language: str = "vi") -> dict[str, Any]:
    """Chuyển audio của run thành chữ → transcript/transcript.txt (bản đọc, có mốc thời gian) + transcript.json.
    engine: auto | captions (phụ đề YouTube) | text (file .txt có sẵn) | openai (cần OPENAI_API_KEY) |
    whisper (faster-whisper tại máy). Sau đó đọc transcript.txt bằng công cụ đọc file (có thể dài — đọc theo phần)."""
    return stt.transcribe(runs.resolve(run), engine, language=language)


@_tool
def run_status(run: str) -> dict[str, Any]:
    """Trạng thái một run: nguồn, file đã có, lịch sử bước, bước kế tiếp nên làm."""
    p = runs.resolve(run)
    data = runs.load(p)
    f = runs.files(p)
    return {"run_dir": str(p), "status": data["status"], "source": data["source"], "files": f,
            "history": data["history"][-10:], "next": runs.next_step(f)}


@_tool
def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    """Liệt kê các run gần nhất dưới thư mục gốc ($AUDIO_STORY_RUNS_DIR, mặc định ./audio-story-runs)."""
    root = runs.runs_root()
    items = sorted((d for d in root.glob("*") if (d / runs.RUN_FILE).is_file()), key=lambda d: d.stat().st_mtime,
                   reverse=True)
    out = []
    for d in items[:limit]:
        data = runs.load(d)
        out.append({"run_dir": str(d), "status": data["status"], "created_at": data["created_at"],
                    "source": data["source"]})
    return out


@_tool
def check_script(run: str, max_overlap: float = script.DEFAULT_MAX_OVERLAP,
                 max_segment_chars: int = script.DEFAULT_MAX_SEGMENT_CHARS) -> dict[str, Any]:
    """Kiểm tất định story/cast.json + script/script.json → script/check.json, và dựng lại script/script.md để duyệt.
    Lỗi (chặn tts_render): schema, old_name_leak (còn tên gốc — so cả không dấu), voice_missing (chưa chọn giọng
    thuyết minh), empty_text. Cảnh báo: high_overlap (% cụm 6 từ trùng bản gốc > max_overlap), segment_too_long,
    new_name_collision, voice_unknown (khi server TTS đang chạy)."""
    p = runs.resolve(run)
    try:
        known = [v["id"] for v in tts.list_voices()]
    except runs.RunError:
        known = None
    result = script.check(p, max_overlap=max_overlap, max_segment_chars=max_segment_chars, known_voices=known)
    if not any(e["code"] == "schema" for e in result["errors"]):
        result["script_md"] = str(script.render_markdown(p))
    result["voices_checked"] = known is not None
    return result


@_tool
def list_voices() -> dict[str, Any]:
    """Danh sách giọng của server VieNeu-TTS (id dùng làm `narrator.voice` trong cast.json) + tình trạng server."""
    h = tts.health()
    if not h["ok"]:
        raise ToolError(f"VieNeu chưa chạy ở {h['url']}: {h['error']}. {h['hint']}")
    return {"server": h, "voices": tts.list_voices()}


@_tool
def tts_preview(text: str, voice: str, run: str | None = None, name: str = "preview") -> dict[str, Any]:
    """Đọc thử một câu bằng một giọng → file WAV (áp pronunciation.json của run nếu có). Dùng để chọn giọng / thử
    cách đọc tên trước khi đọc cả truyện. Không có run thì ghi vào ./audio-story-runs/_preview/."""
    p = runs.resolve(run) if run else None
    out_dir = (p / "audio" / "preview") if p else runs.runs_root() / "_preview"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{name}-{voice}")
    return tts.preview(text, voice, out_dir / f"{safe}.wav", p)


@_tool
def tts_render(run: str, segment_ids: list[int] | None = None, limit: int | None = None, workers: int = 1,
               force: bool = False) -> dict[str, Any]:
    """Đọc kịch bản bằng VieNeu → audio/seg_XXXXX.wav, cả truyện một giọng thuyết minh (cast.narrator.voice). Chỉ chạy khi
    check_script mới nhất không còn lỗi. Đoạn đã đọc với cùng chữ + giọng thì bỏ qua → gọi lại để chạy tiếp.
    limit: chỉ đọc N đoạn (làm thử); segment_ids: đọc lại đúng các đoạn này; workers>1 khi server có GPU."""
    return tts.render(runs.resolve(run), segment_ids=segment_ids, limit=limit, workers=workers, force=force)


@_tool
def qa_audio(run: str, engine: str = "auto", max_cer: float = qa.DEFAULT_MAX_CER, segment_ids: list[int] | None = None,
             limit: int | None = None) -> dict[str, Any]:
    """Nghe lại các đoạn đã đọc bằng STT (openai | whisper), tính CER so với chữ đưa vào TTS → qa/report.json.
    Trả các đoạn CER > max_cer để sửa phát âm (pronunciation.json) rồi đọc lại."""
    return qa.qa(runs.resolve(run), engine=engine, max_cer=max_cer, segment_ids=segment_ids, limit=limit)


@_tool
def assemble_audio(run: str, format: str = "mp3", loudnorm: bool = True, allow_missing: bool = False) -> dict[str, Any]:
    """Ghép các đoạn theo thứ tự kịch bản, chèn khoảng nghỉ pause_after_ms (+1,5 s giữa chương) → out/story.wav và
    out/story.mp3 (chuẩn hoá âm lượng -16 LUFS). allow_missing=true: ghép bản nháp dù còn đoạn chưa đọc."""
    return assemble.assemble(runs.resolve(run), fmt=format, loudnorm=loudnorm, allow_missing=allow_missing)


@_tool
def doctor() -> dict[str, Any]:
    """Kiểm môi trường: ffmpeg, yt-dlp, engine STT có sẵn, server VieNeu, thư mục run."""
    from .cli import doctor_report

    return doctor_report()


def main() -> None:
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)  # stderr gọn: không log từng request VieNeu
    mcp.run("stdio")


if __name__ == "__main__":
    main()

