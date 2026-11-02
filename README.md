# audio-story-mcp

MCP server + plugin Claude Code: **link YouTube truyện audio → chép lời → Claude đổi tên nhân vật, viết lại tình tiết →
đọc bằng một giọng thuyết minh tiếng Việt (VieNeu-TTS) → `story.mp3`.**

Tool MCP không gọi LLM — Claude Code viết lại truyện; server tải, chép lời, **kiểm** (sót tên cũ, % trùng bản gốc),
đọc TTS và ghép. Plan: [`docs/plan.md`](docs/plan.md) · tiến độ: [`docs/status.md`](docs/status.md).

## Cài

Cần: [Claude Code](https://code.claude.com) · [uv](https://docs.astral.sh/uv/). ffmpeg và yt-dlp đi kèm gói Python,
không cần cài hệ thống.

```text
/plugin marketplace add https://github.com/cuonghv0298/audio-story-mcp.git
/plugin install audio-story@audio-story
```

Gõ `/mcp` → `plugin:audio-story:audio-story ✔ connected` (lần đầu uv cài thư viện ~30 s).

**VieNeu-TTS** (giọng đọc, chạy trên máy, Apache-2.0): skill tự nhắc khởi động khi cần. Chạy tay:

```bash
scripts/vieneu.sh run          # http://127.0.0.1:8165 — lần đầu cài ~1–2 phút + tải model
```

Đặt `VIENEU_URL` nếu chạy VieNeu ở máy khác (vd. máy có GPU).

**Chép lời (STT)** — một trong:
- phụ đề tiếng Việt có sẵn trên video (tự dùng, miễn phí);
- `OPENAI_API_KEY` (model `gpt-4o-transcribe`, nhanh, tốn phí);
- whisper tại máy: `uv sync --extra whisper` (miễn phí, chậm trên CPU; model đặt bằng `AUDIO_STORY_WHISPER_MODEL`).

## Dùng

```text
Làm truyện audio mới từ https://www.youtube.com/watch?v=…  — đổi hết tên nhân vật, viết lại tình tiết
```

Skill `audio-story` đi qua: `fetch_source` → `transcribe` → Claude viết `story_bible.json`, `cast.json`, `script.json` →
`check_script` → **anh duyệt `script.md` + nghe thử giọng** → `tts_render` → `assemble_audio` → `out/story.mp3`.

Mọi file nằm trong thư mục run `./audio-story-runs/<slug>-<ngày>-<id>/` (đổi gốc bằng `AUDIO_STORY_RUNS_DIR`).

## Tool MCP

| Tool | Làm gì |
|---|---|
| `fetch_source` | Link YouTube (audio + metadata + phụ đề vi) hoặc file audio/.vtt/.srt/.txt → run mới |
| `transcribe` | `captions` · `text` · `openai` · `whisper` · `auto` → `transcript/transcript.txt` |
| `run_status` · `list_runs` | Run đang ở bước nào |
| `check_script` | Kiểm `cast.json` + `script.json`: sót tên gốc (cả không dấu), thiếu giọng, đoạn rỗng; cảnh báo % trùng bản gốc, đoạn quá dài |
| `list_voices` · `tts_preview` | 25 giọng VieNeu, nghe thử một câu |
| `tts_render` | Đọc từng đoạn (bỏ qua đoạn đã đọc → chạy tiếp được khi bị ngắt) |
| `qa_audio` | STT nghe lại từng đoạn, CER → đoạn cần đọc lại |
| `assemble_audio` | Ghép + khoảng nghỉ + chương → `story.wav` / `story.mp3` (−16 LUFS) |
| `doctor` | Kiểm ffmpeg, yt-dlp, STT, VieNeu |

## CLI (không qua Claude — cho bước dài)

```bash
uv run audio-story doctor
uv run audio-story fetch <url|file>
uv run audio-story transcribe <run> --engine whisper
uv run audio-story check <run>
uv run audio-story render <run> [--limit 3]
uv run audio-story assemble <run>
```

## Phát triển

```bash
uv sync                 # + --extra whisper nếu cần
uv run pytest           # không gọi mạng
uv run ruff check src tests
uv run python scripts/smoke_stdio.py   # gọi server qua MCP stdio thật
```

Mở Claude Code trong repo này là dùng được server luôn (`.mcp.json` ở gốc). Truyện mẫu: `examples/demo/`.
