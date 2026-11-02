# Status — audio-story-mcp

_Cập nhật 02/11/2026._ Plan: [`plan.md`](plan.md).

## Tóm tắt

| Mốc | Trạng thái | Ghi chú |
|---|---|---|
| M0 · Khung | ✅ xong | pyproject (uv, Python 3.12), MCP server stdio, plugin + marketplace (gốc repo), hook, CLI `doctor` |
| M1 · Nghe được | ✅ xong | `fetch_source` (YouTube + file), `transcribe` (captions · text · openai · whisper · auto), `split_chapters`, `run_status`, `list_runs` |
| M2 · Viết được | ✅ xong | skill `audio-story`, schema cast/script, `check_script` |
| M3 · Đọc được | ✅ xong | `list_voices`, `tts_preview`, `tts_render` (chạy tiếp), `assemble_audio` → mp3 |
| M4 · Chất lượng | 🟡 phần lớn | `qa_audio` (CER) + `pronunciation.json` có; chưa đo trên truyện dài |
| M5 · Thử thật | ✅ trong Claude Code | 2 phiên `claude -p --plugin-dir` tự chạy skill từ link → mp3 (chương 219, 220), giọng Quỳnh Anh |

`uv run pytest` → **42 passed** (không gọi mạng) · `ruff check` sạch · `claude plugin validate .` → passed with warnings
(thiếu icon). License MIT.

## Quyết định

- **02/11 — Giọng mặc định Quỳnh Anh** (anh chọn sau khi nghe 3 giọng); ghi trong skill.
- **02/11 — Một giọng thuyết minh cho cả truyện** (anh yêu cầu). Bỏ tách vai/gán giọng theo nhân vật. `cast.json` vẫn giữ
  danh sách nhân vật để đối chiếu tên gốc → tên mới; giọng chỉ ở `narrator.voice`. Kịch bản = đoạn văn liên tiếp, lời thoại
  lồng trong lời kể. Trường `speaker` / `voice` theo vai (nếu có) bị bỏ qua.
- **Plugin = gốc repo** (marketplace `source: "./"`), khác reuse-agent (plugin con + CLI cài riêng): cài plugin là có luôn
  code server; server chạy bằng `uv run --project ${CLAUDE_PLUGIN_ROOT}`, venv ở `${CLAUDE_PLUGIN_DATA}/.venv` (không ghi vào
  thư mục plugin). Cùng `.mcp.json` dùng được khi mở Claude Code trong repo (`${…:-.}`).
- **MCP stdio, không gateway/Keycloak/DB** — một người dùng trên máy.
- **ffmpeg + yt-dlp là gói Python** (`imageio-ffmpeg`, `yt-dlp`) → không cần `brew install`. Có ffmpeg hệ thống thì dùng
  bản đó trước. Không cần ffprobe (đọc độ dài bằng `wave`).
- **faster-whisper không qua PyAV**: faster-whisper 1.2 gọi `av.open(metadata_errors=…)` mà bản `av` mới đã bỏ → tự giải
  mã bằng ffmpeg + `wave` rồi đưa mảng numpy (`stt._pcm16k`).
- **Kiểm sót tên tránh báo nhầm** tên là từ thường (Lan, Phong…): che tên mới trước khi tìm; tên gốc viết hoa thì chỗ khớp
  phải viết hoa chữ đầu mỗi tiếng.
- **Kiểm sót tên chỉ đòi viết hoa chữ đầu** (02/11, gặp ở link thật): «Tiêu Sư Bá» trong truyện còn viết «Tiêu sư bá».
- **TTS xin PCM 24 kHz** rồi tự ghi WAV (như `nova_culture_app/agent/vieneu_tts.py`); hash (model, rate, giọng, chữ sau
  phát âm) quyết định đoạn nào cần đọc lại.

## Kết quả đo (02/11, MacBook Apple Silicon, CPU)

| Việc | Kết quả |
|---|---|
| `fetch_source` YouTube (video 19 s, «Me at the zoo») | 4,8 s, ra `audio.webm` + metadata + 3 chapter; không có phụ đề vi (đúng) |
| VieNeu-TTS v3 Turbo (ONNX CPU, vieneu 3.8.3), giọng Quỳnh Anh | 5 đoạn / 496 ký tự → **29,4 s audio trong 9,1 s (RTF 0,31)** |
| `assemble_audio` | `story.mp3` 33,9 s, 0,54 MB, 2 chương, loudnorm −16 LUFS |
| `qa_audio` bằng faster-whisper `small` | 11,7 s cho 5 đoạn; CER 0,05–0,14 (lỗi chủ yếu do whisper small nghe tiếng Việt kém: «lái đò» → «lấy đỏ») |
| `transcribe` whisper `small` từ mp3 | 10 s cho 34 s audio |
| Server qua MCP stdio (`scripts/smoke_stdio.py`) | 11 tool, gọi `doctor` / `list_voices` / lỗi `run_status` đúng |
| Mô phỏng chế độ plugin (venv mới trong DATA, cwd khác) | khởi động 2,3 s (uv có cache); run tạo trong thư mục dự án |

### Link thật 02/11 — https://youtu.be/RbVGn7Qc6ls («06 - Tiểu Sư Muội Quá Mạnh, Cả Tông Môn Cầu Ta Phi Thăng», kênh TÁM ĐỌC TRUYỆN)

| Bước | Kết quả |
|---|---|
| `fetch_source` | 36 s: audio.webm 289 MB, **6 giờ 7 phút**; phụ đề tự động `vi-orig` 4,3 MB |
| `transcribe` (captions) | 0,2 s → 9.959 đoạn, **387.084 ký tự**, ~40 chương (219–259). Phụ đề có dấu câu, tên riêng đôi chỗ sai («Lê Ngự Ương» / «Lê Ngữ Ương») |
| Viết lại (làm thay Claude, chương 219, 7.542 ký tự) | story_bible + cast (5 nhân vật, 7 tên riêng) + script 25 đoạn / 5.516 ký tự, 4 phần |
| `check_script` | sót tên: 0 · **overlap 0,8%** · lỗi duy nhất ban đầu: chưa chọn giọng |
| `tts_preview` | Quỳnh Anh · Mỹ Duyên · Đức Trí (RTF 0,30–0,34) → chọn **Mỹ Duyên** |
| `tts_render` | 25 đoạn → **383,5 s audio trong 114 s (RTF 0,30)** |
| `assemble_audio` | `story.mp3` **6 phút 41 giây**, 6,4 MB, 4 phần |
| `qa_audio` (whisper small) | 87 s; CER trung vị 0,049; 1 đoạn bị đánh dấu (đoạn 1, 0,29: «chương một» nghe thành «trường 1» — đoạn quá ngắn, nghi do STT) |

Suy ra cho cả tập 6 giờ: viết lại ~40 chương (nhiều phiên Claude, nên làm từng chương), TTS ≈ 1 giờ 50 phút trên Mac CPU.

Ước lượng truyện 1 giờ (~55.000 ký tự): TTS ≈ 20 phút trên Mac CPU; whisper `large-v3-turbo` trên CPU sẽ chậm hơn nhiều so
với `small` — nên dùng phụ đề có sẵn hoặc OpenAI STT cho truyện dài.

### Phiên Claude Code thật (02/11) — `claude -p --plugin-dir <repo>` trong thư mục trống

| Lần | Kết quả |
|---|---|
| Kiểm plugin #1 | ❌ MCP `CONNECTION_CLOSED`: log `Failed to spawn: audio-story-mcp` — trong plugin `${CLAUDE_PLUGIN_ROOT:-.}` **không** được thay, rơi về `.` |
| Sửa | khai server trong `plugin.json` `mcpServers` bằng `${CLAUDE_PLUGIN_ROOT}` / `${CLAUDE_PLUGIN_DATA}` trơn (đè lên `.mcp.json`); `.mcp.json` gốc chỉ cho dev trong repo |
| Kiểm plugin #2 | ✅ 11 tool, `doctor` ok, skill `audio-story:audio-story` có trong danh sách |
| E2E chương 219 | ✅ 15 lệnh gọi, 6 phút 4 giây, $0,90 — tự gọi skill → doctor → fetch → transcribe → viết bible/cast/script → check (overlap 1%, sót tên 0) → render 22 đoạn → mp3 7 phút 59 giây. **Vướng:** phải tự viết Python qua Bash để cắt chương 219, một lệnh `cd …` bị chặn quyền |
| Sửa | thêm tool **`split_chapters`** (mốc «Chương N» tăng dần → `transcript/chapters/`), skill dặn dùng tool thay vì script |
| E2E chương 220 (không cho Bash) | ✅ 13 lệnh gọi, **0 lỗi**, 5 phút 13 giây, $0,73 — gọi `split_chapters` rồi Read đúng file chương; overlap 0,2%, sót tên 0, 24 đoạn → mp3 8 phút 1 giây |

Nghe hai chương: https://claude.ai/artifact/GCAxMfbQC8JNk93Aew7aTy

## Lệch plan

- Tool `assemble` đổi tên thành **`assemble_audio`**; thêm `list_runs`, `doctor`.
- Bản plan đầu đặt plugin ở `plugins/audio-story/` → chuyển về gốc repo (`.claude-plugin/`, `skills/`, `hooks/`,
  `.mcp.json`); plan đã sửa theo.
- Bỏ luật `unknown_speaker`, `same_voice` (không còn tách vai).

## Chưa làm / rủi ro

- Truyện dài (6 giờ, 42 chương): đã tách được theo chương; còn thiếu cách ghép nhiều chương thành một tập (mỗi run
  hiện là một kịch bản).
- Chưa thử `/plugin marketplace add` từ GitHub trong phiên tương tác (đã thử bằng `--plugin-dir`, cùng cơ chế nạp).
- Venv của plugin (`${CLAUDE_PLUGIN_DATA}/.venv`) không có faster-whisper → `qa_audio` không chạy được trong plugin trừ khi
  có `OPENAI_API_KEY`; cài thêm: `UV_PROJECT_ENVIRONMENT=<data>/.venv uv sync --extra whisper --project <plugin>`.
- Chưa có `OPENAI_API_KEY` trong môi trường → nhánh OpenAI STT mới có test giả lập, chưa gọi thật.
- yt-dlp có thể bị YouTube chặn (cần cookie trình duyệt: `AUDIO_STORY_YT_BROWSER=chrome`).
- Ngưỡng `qa_audio` (CER 0,15) phụ thuộc model STT — với whisper `small` dễ báo nhầm; nên dùng `large-v3-turbo` hoặc OpenAI.
- VieNeu: tên/từ nước ngoài có thể đọc sai (nova đã gặp với «Culture AI») → dùng `pronunciation.json`.

## Việc kế tiếp

1. Anh nghe hai chương ở artifact và góp ý cách viết lại.
2. Làm nhiều chương trong một run (kịch bản theo chương, ghép thành một tập dài, m4b có mục lục).
3. Cài plugin từ GitHub trong phiên tương tác.
4. (M6) nhạc nền, m4b có chương, VieNeu trên GPU .73.
