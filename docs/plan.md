# Plan — audio-story-mcp

_Viết 02/11/2026, cập nhật cùng ngày: **một giọng thuyết minh cho cả truyện** (anh yêu cầu). Nghiên cứu nền: `../nghien-cuu-mcp-truyen-audio.html` (artifact: https://claude.ai/artifact/XjGcqeWCjURGdSARecX9gv)._

## 1. Mục tiêu

Một **MCP server + plugin Claude Code** để từ **một link YouTube truyện audio** (hoặc file audio/transcript trên máy) tạo ra **một
truyện audio mới**:

1. Lấy audio + metadata (+ phụ đề nếu có) từ YouTube.
2. Chuyển thành chữ (phụ đề có sẵn, Whisper tại máy, hoặc OpenAI STT).
3. Claude Code đọc, lập **story bible** (nhân vật, quan hệ, tuyến truyện).
4. Claude Code **đổi tên nhân vật** và **viết lại tình tiết** thành kịch bản mới — các đoạn văn liên tiếp.
5. Tool kiểm kịch bản (tất định): sót tên cũ, % trùng câu với bản gốc, thiếu giọng, đoạn quá dài.
6. **Người dùng duyệt** kịch bản + nghe thử giọng.
7. TTS tiếng Việt (VieNeu-TTS tại máy) — **một giọng thuyết minh đọc hết truyện**, không tách vai; có từ điển phát âm.
8. Ghép thành `mp3` (hoặc `wav`), chèn khoảng nghỉ, chuẩn hoá âm lượng.

Ngoài phạm vi bản đầu: tách vai / nhiều giọng (bỏ theo yêu cầu 02/11), đăng YouTube, dựng video/ảnh, nhạc nền, clone
giọng người đọc gốc.

## 2. Nguyên tắc (lấy từ reuse-agent)

- **LLM đề xuất, tool kiểm.** Claude Code viết bible/kịch bản/bảng giọng; tool MCP **không gọi LLM**, chỉ làm việc tất định
  (tải, STT, kiểm, TTS, ghép) và có test.
- **Thư mục run** chứa mọi file trung gian, đọc được bằng mắt, chạy lại được từng bước; tool nhận/trả **đường dẫn**, không đẩy
  audio lớn qua MCP.
- **Có điểm dừng cho người duyệt** trước bước tốn thời gian (TTS cả truyện).
- **Chạy tiếp được**: `tts_render` bỏ qua đoạn đã đọc đúng (hash nội dung + giọng + từ điển).

## 3. Kiến trúc

```
Claude Code (LLM)                       MCP server audio-story (Python, stdio, không LLM)
  skill audio-story  ── MCP stdio ──►     fetch_source · transcribe · run_status · list_runs
  viết bible/cast/script                  check_script · list_voices · tts_preview
                                          tts_render · qa_audio · assemble_audio · doctor
                                              │
                                              ├─ yt-dlp (thư viện Python) + ffmpeg (imageio-ffmpeg, không cần cài hệ thống)
                                              ├─ STT: phụ đề YouTube | faster-whisper (extra) | OpenAI STT (OPENAI_API_KEY)
                                              └─ VieNeu-TTS server :8165 (scripts/vieneu.sh, API giống OpenAI)
```

Bản đầu: một người dùng, chạy trên máy → **MCP stdio**, không gateway/Keycloak/DB (khác reuse-agent).

## 4. Cấu trúc repo

| Đường dẫn | Nội dung |
|---|---|
| `src/audio_story/server.py` | MCP server (SDK `mcp` v2 `MCPServer`), đăng ký tool |
| `src/audio_story/runs.py` | Tạo/đọc thư mục run, `run.json` + `history[]` |
| `src/audio_story/media.py` | ffmpeg: tìm binary, đổi định dạng, cắt khúc, đọc/ghi WAV |
| `src/audio_story/source.py` | `fetch_source`: YouTube (yt-dlp) hoặc file trên máy |
| `src/audio_story/captions.py` | Đọc phụ đề VTT/json3 → đoạn có thời gian |
| `src/audio_story/stt.py` | Engine STT: `captions` · `whisper` · `openai` |
| `src/audio_story/script.py` | Schema `cast.json` / `script.json` (pydantic) + `check_script` |
| `src/audio_story/textnorm.py` | Bỏ dấu, tách từ, n-gram, CER |
| `src/audio_story/tts.py` | Client VieNeu, từ điển phát âm, `tts_preview`, `tts_render` |
| `src/audio_story/assemble.py` | Ghép đoạn + khoảng nghỉ → wav → mp3 (loudnorm) |
| `src/audio_story/qa.py` | `qa_audio`: STT nghe lại từng đoạn, tính CER |
| `src/audio_story/cli.py` | CLI `audio-story` (doctor, gọi từng bước không qua Claude) |
| `.claude-plugin/plugin.json` · `marketplace.json` | Plugin = **gốc repo** (marketplace `source: "./"`) → cài plugin là có luôn code server |
| `.mcp.json` | Server stdio: `uv run --project ${CLAUDE_PLUGIN_ROOT:-.}`, venv ở `${CLAUDE_PLUGIN_DATA:-.}/.venv` — dùng chung cho plugin và khi mở repo |
| `skills/audio-story/SKILL.md` | Quy trình + cách viết lại truyện cho TTS |
| `hooks/hooks.json` | SessionStart: nhắc nếu VieNeu chưa chạy |
| `scripts/smoke_stdio.py` | Gọi server qua MCP stdio thật |
| `examples/demo/` | Truyện mẫu (tự viết) + cast/script để thử cả chuỗi |
| `scripts/vieneu.sh` | Chạy VieNeu-TTS server (chép ý từ nova_culture_app) |
| `tests/` | pytest, không gọi mạng (VieNeu/OpenAI/YouTube giả lập) |

## 5. Thư mục run

```
audio-story-runs/<slug>-<YYYY-MM-DD>-<id>/      # gốc = $AUDIO_STORY_RUNS_DIR, mặc định ./audio-story-runs
├── run.json                 # source, trạng thái, history[] từng bước
├── source/                  # audio.<ext> · audio16k.wav · meta.json · captions.<lang>.vtt
├── transcript/              # transcript.json (đoạn có thời gian) · transcript.txt (bản đọc, chia khúc)
├── story/                   # story_bible.json · cast.json            (Claude viết)
├── script/                  # script.json · script.md (Claude viết) · check.json (tool)
├── pronunciation.json       # từ điển phát âm (Claude/người dùng viết)
├── audio/                   # seg_00001.wav … · manifest.json
├── qa/                      # report.json
└── out/                     # story.wav · story.mp3
```

## 6. Định dạng dữ liệu

`story/cast.json` — bảng đổi tên (để kiểm sót tên) + **một** giọng thuyết minh
```json
{ "narrator": { "voice": "Quỳnh Anh" },
  "characters": [
    { "id": "c1", "old_names": ["Lâm Phong", "Phong ca"], "new_name": "Trần Khải", "gender": "nam", "note": "nam chính" } ],
  "other_names": [ { "old_names": ["Thanh Vân Môn"], "new_name": "Lạc Hà Cốc" } ] }
```

`script/script.json` — đoạn văn liên tiếp, lời thoại lồng trong lời kể
```json
{ "title": "…", "segments": [
    { "id": 1, "text": "…", "emotion": null, "pause_after_ms": 400, "chapter": "Chương 1" },
    { "id": 2, "text": "…", "pause_after_ms": 600 } ] }
```

`pronunciation.json`: `{ "rules": [ { "pattern": "AI", "say": "ây ai", "regex": false } ] }` — chỉ áp cho chữ đưa vào TTS, kịch bản giữ nguyên.

## 7. Bộ tool MCP

| Tool | Vào → ra | Ghi chú |
|---|---|---|
| `fetch_source` | url hoặc đường dẫn file → run mới | yt-dlp `bestaudio`, phụ đề `vi` (thủ công trước, tự động sau); file `.txt/.md` = transcript sẵn |
| `transcribe` | run, engine → `transcript/` | `auto`: phụ đề → OpenAI (nếu có key) → whisper (nếu cài) |
| `run_status` | run → trạng thái, file đã có, bước kế | để skill biết đang ở đâu |
| `check_script` | run → `script/check.json` | lỗi (chặn TTS) và cảnh báo |
| `list_voices` | → giọng VieNeu | từ `GET /v1/voices` |
| `tts_preview` | text, voice → wav | nghe thử, áp từ điển phát âm |
| `tts_render` | run → `audio/seg_*.wav` | chặn nếu `check_script` còn lỗi hoặc cũ hơn script; bỏ qua đoạn đã có; `limit` để làm thử |
| `qa_audio` | run → `qa/report.json` | STT nghe lại, CER từng đoạn |
| `assemble_audio` | run, format → `out/` | nghỉ theo `pause_after_ms`, +1,5 s giữa chương, loudnorm −16 LUFS |
| `list_runs` · `doctor` | — | run gần nhất · kiểm môi trường |

## 8. Các mốc

| Mốc | Nội dung | Xong khi |
|---|---|---|
| **M0 · Khung** | pyproject, MCP server rỗng, plugin + marketplace, CLI `doctor`, plan/status | `/mcp` thấy server, test xanh |
| **M1 · Nghe được** | `fetch_source`, `transcribe` (captions/openai/whisper), `run_status` | 1 link thật ra `transcript.txt` |
| **M2 · Viết được** | skill `audio-story`, schema cast/script, `check_script` (tên sót, % trùng, giọng, độ dài) | test khoá các luật kiểm |
| **M3 · Đọc được** | client VieNeu, `list_voices`, `tts_preview`, `tts_render` (chạy tiếp), `assemble_audio` | một kịch bản mẫu ra `story.mp3` nghe được |
| **M4 · Chất lượng** | `qa_audio` (CER), từ điển phát âm, chương | đoạn CER cao được đánh dấu để đọc lại |
| **M5 · Thử thật** | 2–3 link truyện thật của anh, đo thời gian STT/TTS, chỉnh skill theo kết quả | anh nghe và duyệt 1 truyện hoàn chỉnh |
| **M6 · Mở rộng** (sau) | nhạc nền, m4b có chương, provider TTS khác (OpenAI/ElevenLabs), VieNeu trên GPU .73 | — |

## 9. Luật trong `check_script`

Lỗi (chặn `tts_render`):
- `schema` — `script.json`/`cast.json` sai cấu trúc.
- `old_name_leak` — còn tên gốc (so khớp không phân biệt hoa thường **và** sau khi bỏ dấu, theo ranh giới từ; che tên mới
  trước khi tìm; tên gốc viết hoa thì chỗ khớp phải viết hoa — «hoa lan» không tính là tên «Lan»). Kiểm cả tiêu đề.
- `voice_missing` — chưa chọn giọng thuyết minh.
- `empty_text` — đoạn rỗng.

Cảnh báo:
- `high_overlap` — tỉ lệ 6-gram của kịch bản trùng transcript > 35% (ngưỡng chỉnh qua tham số).
- `segment_too_long` — đoạn > 1.200 ký tự (nên tách để dễ đọc lại).
- `new_name_collision` — tên mới trùng tên gốc của nhân vật khác.
- `voice_unknown` — giọng không có trong danh sách VieNeu (chỉ khi server chạy).

## 10. Câu hỏi mở

1. STT mặc định: OpenAI (cần key, tốn phí, nhanh) hay Whisper tại máy (miễn phí, chậm trên Mac)? Hiện: `auto`.
2. Ngưỡng % trùng bao nhiêu thì coi là "đủ mới"? Hiện cảnh báo ở 35%.
3. Có cần chạy VieNeu trên máy GPU .73 cho truyện dài không?
4. Có cần provider TTS trả phí (ElevenLabs) làm dự phòng?
5. ~~License~~ → MIT (02/11).
6. Truyện dài nhiều chương: tách theo chương, viết lại từng chương qua nhiều phiên?
