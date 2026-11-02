from audio_story.textnorm import (
    cer,
    fold_for_search,
    name_pattern,
    overlap_ratio,
    slugify,
    split_sentences,
    strip_accents,
    words,
)


def test_strip_accents_handles_d():
    assert strip_accents("Trần Khải Đức đi đâu") == "Tran Khai Duc di dau"


def test_words_fold():
    assert words("Lâm  Phong, ĐI!") == ["lam", "phong", "di"]
    assert words("Lâm Phong", fold=False) == ["lâm", "phong"]


def test_fold_keeps_length():
    s = "Ồ! Lâm Phong — Đạo hữu"
    assert len(fold_for_search(s)) == len(s)


def test_name_pattern_matches_without_accents_and_word_boundary():
    pat = name_pattern("Lâm Phong")
    assert pat.search(fold_for_search("hôm ấy lam phong đến"))
    assert pat.search(fold_for_search("LÂM   PHONG cười"))
    assert not pat.search(fold_for_search("Lâm Phongg"))
    assert not pat.search(fold_for_search("Thanh Lâm Phongsơn"))


def test_overlap_ratio():
    src = "một hai ba bốn năm sáu bảy tám chín mười"
    assert overlap_ratio("một hai ba bốn năm sáu", src, 6) == 1.0
    assert overlap_ratio("khác hẳn hoàn toàn không giống chút nào", src, 6) == 0.0
    assert overlap_ratio("ngắn", src, 6) == 0.0


def test_cer():
    assert cer("xin chào", "xin chào") == 0.0
    assert cer("xin chào", "xin chao") > 0
    assert cer("", "") == 0.0


def test_slugify():
    assert slugify("Truyện Ma: Ngôi Nhà Số 7!") == "truyen-ma-ngoi-nha-so-7"


def test_split_sentences_respects_max():
    text = "Câu một ngắn. " * 30 + "Một câu rất dài " + "chữ " * 100
    parts = split_sentences(text, 120)
    assert all(len(p) <= 120 for p in parts)
    assert " ".join(parts).split() == " ".join(text.split()).split()
