from app.services.vietnamese import (
    lexical_score,
    normalize_vietnamese_text,
    normalized_search_text,
    tokenize_vietnamese_query,
)


def test_normalize_vietnamese_text_compacts_whitespace():
    text = "Thanh   toán\r\n\r\n\r\ntrong  30 ngày"

    assert normalize_vietnamese_text(text) == "Thanh toán\n\ntrong 30 ngày"


def test_normalized_search_text_is_diacritic_insensitive():
    assert normalized_search_text("Thời hạn thanh toán") == "thoi han thanh toan"


def test_tokenize_vietnamese_query_removes_common_stopwords():
    assert tokenize_vietnamese_query("thời hạn thanh toán là bao lâu") == ["thoi", "han", "thanh", "toan", "lau"]


def test_lexical_score_matches_vietnamese_without_diacritics():
    content = "Hợp đồng quy định thời hạn thanh toán là 30 ngày kể từ ngày nhận hóa đơn."

    assert lexical_score("thoi han thanh toan", content) > 0.8
    assert lexical_score("quy trình tuyển dụng", content) == 0
