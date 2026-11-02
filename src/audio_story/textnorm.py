"""Chuẩn hoá chữ tiếng Việt cho các phép kiểm tất định: bỏ dấu, tách từ, n-gram, CER."""

from __future__ import annotations

import re
import unicodedata

_WORD = re.compile(r"\w+", re.UNICODE)


def strip_accents(text: str) -> str:
    """«Trần Khải Đức» → «Tran Khai Duc» (đ/Đ không tách được bằng NFD nên đổi tay)."""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def words(text: str, *, fold: bool = True) -> list[str]:
    """Tách từ (âm tiết) chữ thường; ``fold`` = bỏ dấu."""
    text = unicodedata.normalize("NFC", text).lower()
    if fold:
        text = strip_accents(text)
    return _WORD.findall(text)


def ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def overlap_ratio(candidate: str, source: str, n: int = 6) -> float:
    """Tỉ lệ n-gram (theo từ, có dấu) của ``candidate`` cũng xuất hiện trong ``source``. 0 khi ``candidate`` quá ngắn."""
    cand = ngrams(words(candidate, fold=False), n)
    if not cand:
        return 0.0
    src = set(ngrams(words(source, fold=False), n))
    return sum(1 for g in cand if g in src) / len(cand)


def name_pattern(name: str) -> re.Pattern[str]:
    """Regex tìm ``name`` theo ranh giới từ trên chữ đã bỏ dấu + chữ thường (dùng với ``fold_for_search``)."""
    toks = words(name)
    if not toks:
        raise ValueError(f"tên rỗng: {name!r}")
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(t) for t in toks) + r"(?!\w)")


def fold_for_search(text: str) -> str:
    """Chữ thường + bỏ dấu, giữ nguyên độ dài từng ký tự gốc (để vị trí khớp trỏ lại được chữ gốc)."""
    out = []
    for ch in unicodedata.normalize("NFC", text):
        f = strip_accents(ch.lower())
        out.append(f if len(f) == 1 else (f[:1] or " "))
    return "".join(out)


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate trên chữ thường, bỏ dấu câu, gộp khoảng trắng (giữ dấu tiếng Việt)."""
    ref = " ".join(words(reference, fold=False))
    hyp = " ".join(words(hypothesis, fold=False))
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, hc in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return prev[-1] / len(ref)


def slugify(text: str, max_len: int = 40) -> str:
    s = "-".join(words(text))
    return (s[:max_len].rstrip("-")) or "story"


def split_sentences(text: str, max_chars: int) -> list[str]:
    """Tách đoạn dài thành khúc ≤ ``max_chars`` theo câu (rồi theo dấu phẩy / khoảng trắng nếu câu vẫn quá dài)."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text] if text else []
    parts = re.split(r"(?<=[.!?…;:])\s+", text)
    out: list[str] = []
    buf = ""
    for p in parts:
        for piece in _hard_split(p, max_chars):
            if buf and len(buf) + 1 + len(piece) > max_chars:
                out.append(buf)
                buf = piece
            else:
                buf = f"{buf} {piece}".strip()
    if buf:
        out.append(buf)
    return out


def _hard_split(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    out, buf = [], ""
    for tok in re.split(r"(?<=,)\s+|\s+", sentence):
        if buf and len(buf) + 1 + len(tok) > max_chars:
            out.append(buf)
            buf = tok
        else:
            buf = f"{buf} {tok}".strip()
    if buf:
        out.append(buf)
    return out
