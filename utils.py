import re
from difflib import SequenceMatcher
from typing import Iterable


_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_@#]+")


def normalize_text(text: str) -> str:
    lowered = text.lower().replace("ё", "е")
    lowered = re.sub(r"https?://\S+", " ", lowered)
    lowered = re.sub(r"[^a-zа-я0-9_@#\s-]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def words(text: str) -> list[str]:
    return _WORD_RE.findall(normalize_text(text))


def jaccard_similarity(a: str, b: str) -> float:
    set_a = set(words(a))
    set_b = set(words(b))
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def sequence_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def first_words_signature(text: str, count: int = 6) -> str:
    return " ".join(words(text)[:count])


def extract_mentions(text: str) -> list[str]:
    return sorted(set(re.findall(r"@[A-Za-z0-9_]{3,32}", text)))


def is_too_similar(candidate: str, previous_texts: Iterable[str]) -> tuple[bool, str]:
    candidate_signature = first_words_signature(candidate)
    for old in previous_texts:
        if not old:
            continue

        old_signature = first_words_signature(old)
        if candidate_signature and old_signature and candidate_signature == old_signature:
            return True, "совпадает начало ответа"

        seq = sequence_similarity(candidate, old)
        jac = jaccard_similarity(candidate, old)

        if seq >= 0.72:
            return True, f"слишком похожая формулировка ({seq:.2f})"

        if jac >= 0.55:
            return True, f"слишком похожий набор слов ({jac:.2f})"

    return False, ""


def clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def safe_short(text: str, max_len: int = 3500) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def clean_bot_reply(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:\w+)?", "", text)
    text = re.sub(r"```$", "", text)
    text = text.strip().strip('"').strip()
    return text
