---
name: audio-story
description: Tạo truyện audio mới từ một link YouTube truyện audio (hoặc file audio / transcript trên máy) — tải và chép lời bằng MCP audio-story, đọc hiểu truyện, đổi tên nhân vật, viết lại tình tiết thành kịch bản mới, kiểm bằng check_script, dừng cho người dùng duyệt, rồi đọc bằng MỘT giọng thuyết minh tiếng Việt (VieNeu-TTS) và ghép ra mp3. Dùng khi người dùng đưa link YouTube truyện và muốn «viết lại», «đổi tên nhân vật», «làm truyện audio mới», «audio story», hoặc muốn tiếp tục một run truyện audio đang dở.
---

# Audio Story — từ link YouTube ra truyện audio mới

Bạn là **người viết lại truyện**. Tool MCP `audio-story` lo phần tất định (tải, chép lời, kiểm, TTS, ghép) và **không gọi
LLM**. Bạn đọc hiểu, đổi tên, viết lại. Con số kiểm (sót tên, % trùng bản gốc) do `check_script` trả về — đừng tự chấm.

**Cả truyện đọc bằng MỘT giọng thuyết minh** — không tách vai, không gán giọng cho nhân vật. Lời thoại vẫn viết trong
đoạn văn như người kể chuyện thuật lại.

## 0 · Trước khi bắt đầu

- Gọi `doctor`. Nếu `vieneu.ok = false` → khởi động VieNeu ở **nền** (lần đầu cài ~1–2 phút, tải model ~vài trăm MB):
  `VIENEU_VENV="${CLAUDE_PLUGIN_DATA}/vieneu-venv" "${CLAUDE_PLUGIN_ROOT}/scripts/vieneu.sh" run`
  (chạy bằng Bash với run_in_background). Không cần VieNeu cho bước 1–4.
- Tiếp tục run đang dở: `list_runs` / `run_status(run)` → làm tiếp từ `next`.

## 1 · Lấy nguồn

`fetch_source(source=<link YouTube hoặc đường dẫn file>)` → nhớ `run_dir`. Báo người dùng: tiêu đề, kênh, thời lượng, có
phụ đề tiếng Việt không.

- Lỗi chống bot / đăng nhập → bảo người dùng đặt `AUDIO_STORY_YT_BROWSER=chrome` (hoặc `AUDIO_STORY_YT_COOKIES=<file>`)
  rồi mở lại Claude Code.

## 2 · Chép lời

`transcribe(run)` (engine `auto`: phụ đề → OpenAI nếu có `OPENAI_API_KEY` → faster-whisper nếu đã cài).

- Không có engine nào → hỏi người dùng: đặt `OPENAI_API_KEY` (nhanh, tốn phí) hay cài whisper tại máy
  (`uv sync --extra whisper` trong thư mục plugin; chậm trên CPU).
- Phụ đề tự động thường không dấu câu, sai tên riêng — vẫn đủ để hiểu cốt truyện vì bạn sẽ viết lại.
- Truyện dài 1–3 giờ: STT có thể lâu; gợi ý người dùng chạy CLI ngoài Claude:
  `uv run --project "${CLAUDE_PLUGIN_ROOT}" audio-story transcribe <run_dir>`.

## 3 · Đọc hiểu → story bible

Truyện dài (> ~15.000 ký tự) hoặc người dùng chỉ muốn vài chương: gọi `split_chapters(run)` → mỗi chương một file
`transcript/chapters/chuong-XXXX.txt` (kèm số ký tự, mốc thời gian, ước lượng phút audio). Đọc đúng file chương cần làm
bằng Read — **không** tự viết script Python/Bash để cắt transcript. Báo người dùng số chương và độ dài ước lượng.

Đọc transcript (hoặc file chương) **theo phần** (Read với offset/limit nếu dài). Ghi `story/story_bible.json`:

```json
{ "title_goc": "…", "the_loai": "tiên hiệp | ma | ngôn tình | đời thường …", "boi_canh": "…",
  "nhan_vat": [ { "ten_goc": "Lâm Phong", "biet_danh": ["Phong ca"], "vai_tro": "nam chính", "tinh_cach": "…" } ],
  "dia_danh_to_chuc": ["Thanh Vân Môn"],
  "tuyen_truyen": [ { "phan": 1, "tom_tat": "…" } ],
  "chi_tiet_dat": ["các chi tiết làm nên cái hay của truyện"] }
```

Tóm tắt cho người dùng trong 5–8 dòng: nhân vật chính, cốt truyện, độ dài.

## 4 · Viết kịch bản mới

Hỏi người dùng (một lần, gộp câu hỏi) nếu chưa rõ: muốn đổi bao nhiêu (chỉ tên / tên + bối cảnh / viết lại tình tiết),
giữ thể loại không, độ dài mong muốn. Mặc định: **đổi toàn bộ tên riêng, giữ thể loại, viết lại tình tiết và lời văn,
độ dài tương đương**.

**`story/cast.json`** — bảng đổi tên (dùng để kiểm sót tên) + giọng thuyết minh:

```json
{ "narrator": { "voice": "<chọn ở bước 5, tạm để null>" },
  "characters": [ { "id": "c1", "old_names": ["Lâm Phong", "Phong ca", "Lâm huynh"], "new_name": "Trần Khải",
                    "gender": "nam", "note": "nam chính" } ],
  "other_names": [ { "old_names": ["Thanh Vân Môn"], "new_name": "Lạc Hà Cốc" } ] }
```

- `old_names` liệt kê **mọi cách gọi** trong bản gốc (tên đầy đủ, tên gọi tắt, biệt danh, cách xưng hô gắn tên).
  Không đưa đại từ/xưng hô chung («huynh», «sư phụ») vào.
- Tên mới hợp thể loại, không trùng tên gốc của nhân vật khác, dễ đọc bằng TTS (tránh chữ nước ngoài, ký hiệu).

**`script/script.json`** — các đoạn văn liên tiếp, đọc bằng một giọng:

```json
{ "title": "Tên truyện mới",
  "segments": [
    { "id": 1, "chapter": "Phần 1", "text": "…", "pause_after_ms": 400 },
    { "id": 2, "text": "…", "emotion": "hồi hộp" } ] }
```

Cách viết cho TTS (quan trọng):
- **Viết lại thật sự**: đổi diễn biến phụ, thứ tự tiết lộ, chi tiết, câu chữ; giữ mạch cảm xúc. Không chép câu gốc rồi
  thay tên. Mục tiêu `overlap` < 35%.
- Mỗi đoạn 2–5 câu, khoảng 200–600 ký tự; `id` tăng dần từ 1, không trùng.
- Lời thoại viết lồng trong lời kể: «Khải khẽ đáp: "Đệ tử hiểu rồi."» — một giọng đọc nên cần câu dẫn rõ ai nói.
- Không emoji, không markdown, không ký hiệu lạ (*, #, →, …). Số và đơn vị viết sao cho dễ đọc («ba năm», «năm trăm lượng»).
- `pause_after_ms`: 300–500 giữa đoạn thường, 800–1500 trước bước ngoặt. `chapter` đặt ở đoạn đầu mỗi phần.
- Truyện dài: viết **từng phần** — tạo file với phần 1, rồi thêm các phần sau (Edit) — đừng viết một khối JSON khổng lồ.
- Mở đầu có câu giới thiệu tên truyện; kết thúc có câu khép lại. **Không** nhắc tên kênh/tác giả gốc.

## 5 · Kiểm

`check_script(run)` → sửa đến khi `ok = true`. Lỗi chặn đọc: `old_name_leak` (xem `context`, sửa đúng chỗ — kể cả
dạng không dấu), `voice_missing`, `empty_text`, `schema`. Cảnh báo `high_overlap`: viết lại các đoạn trong
`stats.most_similar_segments` rồi kiểm lại.

Chọn giọng thuyết minh: **mặc định `Quỳnh Anh`** (nữ miền Bắc, đọc truyện — anh chọn 02/11/2026); chỉ đổi khi người
dùng yêu cầu. Muốn so giọng: `list_voices` → gợi ý 2–3 giọng hợp thể loại (giọng có «đọc truyện / kể chuyện»: Quỳnh Anh, Mỹ
Duyên, Kim Thanh, Ngọc Linh, Thục Đoan, Đức Trí, Thanh Bình, Thiện Minh, Thái Sơn…) → `tts_preview` đoạn mở đầu với từng
giọng → đưa đường dẫn file cho người dùng nghe → ghi `narrator.voice` → `check_script` lại.

## 6 · ✋ Dừng cho người dùng duyệt

Đưa người dùng: `script/script.md`, bảng đổi tên, giọng, `overlap`, số đoạn/ký tự và ước lượng thời gian đọc
(≈ 1 phút audio / 900 ký tự; trên Mac CPU sinh ≈ 0,3–0,5 × thời lượng). **Không** chạy `tts_render` cả truyện trước
khi người dùng đồng ý. Sửa theo góp ý → `check_script` lại.

## 7 · Đọc + ghép

1. `tts_render(run, limit=3)` → `assemble_audio(run, allow_missing=true)` → người dùng nghe thử đoạn đầu.
2. Đồng ý → `tts_render(run)` (gọi lại nếu bị ngắt — đoạn đã đọc được bỏ qua). Truyện dài: gợi ý CLI
   `uv run --project "${CLAUDE_PLUGIN_ROOT}" audio-story render <run_dir>`.
3. Nếu có STT: `qa_audio(run)` → đoạn CER cao: thêm luật vào `pronunciation.json`
   (`{ "rules": [ { "pattern": "AI", "say": "ây ai" } ] }`) hoặc sửa chữ → `check_script` → `tts_render(segment_ids=[…])`.
4. `assemble_audio(run)` → báo đường dẫn `out/story.mp3`, thời lượng, các chương.

## Lưu ý bản quyền

Viết lại từ truyện của người khác vẫn có thể là tác phẩm phái sinh; YouTube hạn chế kiếm tiền với nội dung dùng lại.
Nếu người dùng định đăng lại, nhắc một lần (không giảng giải) rằng nên dùng truyện họ có quyền hoặc viết lại phần lớn, và
báo `overlap` để họ tự quyết. Không clone giọng người đọc gốc.
