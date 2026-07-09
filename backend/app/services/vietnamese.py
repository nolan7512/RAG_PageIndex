import re
import unicodedata
from collections import Counter
from math import log
from typing import Iterable, List


VIETNAMESE_STOPWORDS = {
    "a",
    "ai",
    "anh",
    "ban",
    "bang",
    "bao",
    "bi",
    "boi",
    "cac",
    "cai",
    "can",
    "cang",
    "chi",
    "cho",
    "co",
    "con",
    "cua",
    "cung",
    "da",
    "dang",
    "de",
    "den",
    "di",
    "do",
    "duoc",
    "gi",
    "hay",
    "hon",
    "khi",
    "khong",
    "la",
    "lai",
    "lam",
    "len",
    "mot",
    "nay",
    "neu",
    "nhieu",
    "nhung",
    "nhu",
    "o",
    "qua",
    "ra",
    "rang",
    "rieng",
    "sau",
    "se",
    "tai",
    "tat",
    "the",
    "thi",
    "theo",
    "toi",
    "trong",
    "tu",
    "va",
    "ve",
    "voi",
}


def normalize_vietnamese_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def remove_vietnamese_diacritics(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


def normalized_search_text(text: str) -> str:
    text = normalize_vietnamese_text(text).lower()
    text = remove_vietnamese_diacritics(text)
    return re.sub(r"[^0-9a-zA-Z]+", " ", text).strip()


def tokenize_vietnamese_query(text: str) -> List[str]:
    normalized = normalized_search_text(text)
    tokens = [token for token in normalized.split() if len(token) >= 2]
    return [token for token in tokens if token not in VIETNAMESE_STOPWORDS]


def lexical_score(query: str, content: str) -> float:
    query_tokens = tokenize_vietnamese_query(query)
    if not query_tokens:
        return 0.0

    content_text = normalized_search_text(content)
    if not content_text:
        return 0.0

    content_tokens = content_text.split()
    content_counts = Counter(content_tokens)
    total_terms = max(1, len(content_tokens))
    unique_query_terms = list(dict.fromkeys(query_tokens))

    matched = 0
    weighted = 0.0
    for token in unique_query_terms:
        frequency = content_counts.get(token, 0)
        if frequency:
            matched += 1
            weighted += 1.0 + log(1 + frequency / total_terms * 100)

    if len(unique_query_terms) > 1 and (matched < 2 or matched / len(unique_query_terms) < 0.4):
        return 0.0

    phrase_bonus = 0.0
    query_phrase = " ".join(query_tokens)
    if len(query_tokens) >= 2 and query_phrase in content_text:
        phrase_bonus = 0.25

    coverage = matched / len(unique_query_terms)
    density = min(0.35, weighted / max(1, len(unique_query_terms)) * 0.12)
    return min(1.0, coverage * 0.65 + density + phrase_bonus)


def best_lexical_matches(query: str, contents: Iterable[tuple]) -> List[tuple]:
    scored = []
    for item in contents:
        score = lexical_score(query, item[-1])
        if score > 0:
            scored.append((*item, score))
    scored.sort(key=lambda value: value[-1], reverse=True)
    return scored
