"""Schema ``cast.json`` / ``script.json`` và ``check_script`` — kiểm tất định kịch bản Claude viết, trước khi tốn công TTS.

Cả truyện đọc bằng **một giọng thuyết minh** (``cast.narrator.voice``) — không tách vai (quyết định 02/11/2026).
``cast.json`` vẫn liệt kê nhân vật để đối chiếu tên gốc → tên mới. Kịch bản = các đoạn văn liên tiếp.

Lỗi (``errors``) chặn ``tts_render``; cảnh báo (``warnings``) chỉ báo để người dùng quyết.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from . import runs
from .textnorm import fold_for_search, name_pattern, overlap_ratio, words

NARRATOR = "narrator"
OVERLAP_N = 6
DEFAULT_MAX_OVERLAP = 0.35
DEFAULT_MAX_SEGMENT_CHARS = 1200


class Narrator(BaseModel):
    voice: str | None = None


class Character(BaseModel):
    id: str = Field(min_length=1)
    old_names: list[str] = Field(default_factory=list)
    new_name: str = Field(min_length=1)
    gender: str | None = None
    note: str | None = None

    @field_validator("id")
    @classmethod
    def _not_narrator(cls, v: str) -> str:
        if v == NARRATOR:
            raise ValueError("id «narrator» dành cho người dẫn truyện")
        return v


class Cast(BaseModel):
    narrator: Narrator = Field(default_factory=Narrator)
    characters: list[Character] = Field(default_factory=list)
    # tên riêng khác cần đổi (địa danh, môn phái…): {"old_names": [...], "new_name": "..."}
    other_names: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def voice(self) -> str | None:
        return self.narrator.voice


class Segment(BaseModel):
    id: int
    text: str
    emotion: str | None = None
    pause_after_ms: int = Field(default=350, ge=0, le=10_000)
    chapter: str | None = None


class Script(BaseModel):
    title: str | None = None
    segments: list[Segment]

    @field_validator("segments")
    @classmethod
    def _unique_ids(cls, v: list[Segment]) -> list[Segment]:
        seen: set[int] = set()
        for s in v:
            if s.id in seen:
                raise ValueError(f"id đoạn bị trùng: {s.id}")
            seen.add(s.id)
        return v


def load_cast(run_dir: Path) -> Cast:
    return Cast.model_validate(runs.read_json(run_dir / "story" / "cast.json"))


def load_script(run_dir: Path) -> Script:
    return Script.model_validate(runs.read_json(run_dir / "script" / "script.json"))


def _issue(code: str, msg: str, **ctx: Any) -> dict[str, Any]:
    return {"code": code, "message": msg, **ctx}


def check(run_dir: Path, *, max_overlap: float = DEFAULT_MAX_OVERLAP,
          max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS, known_voices: list[str] | None = None) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []
    try:
        cast = load_cast(run_dir)
    except (ValidationError, runs.RunError) as e:
        cast = None
        errors.append(_issue("schema", f"story/cast.json: {e}"))
    try:
        script = load_script(run_dir)
    except (ValidationError, runs.RunError) as e:
        script = None
        errors.append(_issue("schema", f"script/script.json: {e}"))

    stats: dict[str, Any] = {}
    if cast and script:
        _check_cast(cast, errors, warnings, known_voices)
        _check_segments(script, errors, warnings, max_segment_chars)
        _check_names(cast, script, errors)
        stats = _overlap(run_dir, script, max_overlap, warnings)
        stats.update(segments=len(script.segments), chars=sum(len(s.text) for s in script.segments),
                     voice=cast.voice)

    result = {"ok": not errors, "errors": errors, "warnings": warnings, "stats": stats,
              "checked_at": runs.now(), "params": {"max_overlap": max_overlap, "max_segment_chars": max_segment_chars}}
    runs.write_json(run_dir / "script" / "check.json", result)
    runs.record(run_dir, "check_script", "checked" if result["ok"] else "check_failed",
                errors=len(errors), warnings=len(warnings))
    return result


def _check_cast(cast: Cast, errors: list, warnings: list, known_voices: list[str] | None) -> None:
    if not cast.narrator.voice:
        errors.append(_issue("voice_missing", "chưa chọn giọng thuyết minh (cast.narrator.voice)"))
    elif known_voices is not None and cast.narrator.voice.casefold() not in {v.casefold() for v in known_voices}:
        warnings.append(_issue("voice_unknown", f"giọng «{cast.narrator.voice}» không có trong danh sách TTS"))
    ids: set[str] = set()
    for c in cast.characters:
        if c.id in ids:
            errors.append(_issue("schema", f"id nhân vật trùng: {c.id}"))
        ids.add(c.id)
    # tên mới trùng tên gốc của ai đó → người nghe lẫn nhân vật
    olds = {" ".join(words(o)): c.id for c in cast.characters for o in c.old_names}
    for c in cast.characters:
        key = " ".join(words(c.new_name))
        if key in olds and olds[key] != c.id:
            warnings.append(_issue("new_name_collision", f"tên mới «{c.new_name}» trùng tên gốc của {olds[key]}",
                                   character=c.id))


def _check_segments(script: Script, errors: list, warnings: list, max_chars: int) -> None:
    for s in script.segments:
        if not s.text.strip():
            errors.append(_issue("empty_text", f"đoạn {s.id} rỗng", segment=s.id))
        elif len(s.text) > max_chars:
            warnings.append(_issue("segment_too_long", f"đoạn {s.id} dài {len(s.text)} ký tự (> {max_chars})",
                                   segment=s.id))


def _check_names(cast: Cast, script: Script, errors: list) -> None:
    """Tên gốc còn sót trong kịch bản — so khớp không dấu, không phân biệt hoa thường, theo ranh giới từ.

    Tránh báo nhầm với tên là từ thường (Lan, Phong, Hoa…):
    - che tên mới trước khi tìm (đổi «Lan» → «Lan Anh» thì «Lan Anh» không tính);
    - tên gốc viết hoa thì chỗ khớp phải viết hoa chữ đầu («hoa lan nở» không tính; «LAN», «Tiêu sư bá» có tính).
    """
    new_names = [c.new_name for c in cast.characters] + [o.get("new_name", "") for o in cast.other_names]
    new_pats = [name_pattern(n) for n in new_names if words(n)]
    new_folded = {" ".join(words(n)) for n in new_names}
    targets: list[tuple[str, str]] = []
    for c in cast.characters:
        targets += [(o, c.id) for o in c.old_names]
    for o in cast.other_names:
        targets += [(n, "other") for n in o.get("old_names", [])]
    pats = []
    for old, who in targets:
        if not words(old) or " ".join(words(old)) in new_folded:
            continue
        pats.append((old, who, name_pattern(old), any(ch.isupper() for ch in old)))
    if not pats:
        return
    for sid, text in [("tiêu đề", script.title or "")] + [(s.id, s.text) for s in script.segments]:
        folded = fold_for_search(text)
        for p in new_pats:
            folded = p.sub(lambda m: " " * len(m.group(0)), folded)
        for old, who, pat, capitalized in pats:
            for m in pat.finditer(folded):
                span = text[m.start() : m.end()]
                if capitalized and not span[:1].isupper():
                    continue
                a, b = max(0, m.start() - 25), min(len(text), m.end() + 25)
                where = sid if sid == "tiêu đề" else f"đoạn {sid}"
                errors.append(_issue("old_name_leak", f"{where}: còn tên gốc «{old}»", segment=sid,
                                     character=who, context=text[a:b]))
                break


def _overlap(run_dir: Path, script: Script, max_overlap: float, warnings: list) -> dict[str, Any]:
    tjson = run_dir / "transcript" / "transcript.json"
    if not tjson.exists():
        return {"overlap": None}
    source = "\n".join(s["text"] for s in runs.read_json(tjson)["segments"])
    full = "\n".join(s.text for s in script.segments)
    ratio = overlap_ratio(full, source, OVERLAP_N)
    worst = sorted(((overlap_ratio(s.text, source, OVERLAP_N), s.id) for s in script.segments
                    if len(words(s.text)) >= OVERLAP_N * 2), reverse=True)[:5]
    if ratio > max_overlap:
        warnings.append(_issue("high_overlap", f"{ratio:.0%} cụm {OVERLAP_N} từ của kịch bản trùng nguyên văn bản gốc "
                                               f"(ngưỡng {max_overlap:.0%}) — nên viết lại nhiều hơn",
                               ratio=round(ratio, 3)))
    return {"overlap": round(ratio, 3), "overlap_n": OVERLAP_N,
            "most_similar_segments": [{"segment": sid, "ratio": round(r, 3)} for r, sid in worst if r > 0]}


def render_markdown(run_dir: Path) -> Path:
    """Dựng lại ``script/script.md`` (bản đọc duyệt) từ ``script.json`` + ``cast.json``."""
    cast, script = load_cast(run_dir), load_script(run_dir)
    lines = [f"# {script.title or 'Kịch bản'}", "", f"Giọng thuyết minh: **{cast.voice or '⚠ chưa chọn'}**", "",
             "| Nhân vật | Tên mới | Tên gốc |", "|---|---|---|"]
    for c in cast.characters:
        lines.append(f"| {c.id} | {c.new_name} | {', '.join(c.old_names) or '—'} |")
    for o in cast.other_names:
        lines.append(f"| (tên riêng) | {o.get('new_name', '')} | {', '.join(o.get('old_names', []))} |")
    chapter = None
    for s in script.segments:
        if s.chapter and s.chapter != chapter:
            chapter = s.chapter
            lines += ["", f"## {chapter}"]
        emo = f" _({s.emotion})_" if s.emotion else ""
        lines += ["", f"`{s.id}`{emo} {s.text}"]
    out = run_dir / "script" / "script.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
