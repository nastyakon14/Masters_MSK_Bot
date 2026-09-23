import re

FIO_WORD_RE = re.compile(
    r"^(?:[А-Яа-яЁё]{2,}(?:-[А-Яа-яЁё]{2,})*|[A-Za-z]{2,}(?:-[A-Za-z]{2,})*)$"
)
CUSTOM_STYLE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 \-/]{1,39}$")


def _title_word(word: str) -> str:
    return "-".join(part.capitalize() for part in word.split("-"))


def validate_fio(text: str) -> str | None:
    parts = text.split()
    if not 2 <= len(parts) <= 4:
        return None
    if any(len(part) > 30 or not FIO_WORD_RE.fullmatch(part) for part in parts):
        return None
    return " ".join(_title_word(part) for part in parts)


def validate_contact(text: str) -> str | None:
    raw = text.strip()
    if not raw or len(raw) > 40:
        return None

    compact = re.sub(r"[\s\-()]+", "", raw)
    digits = compact[1:] if compact.startswith("+") else compact
    if digits.isdigit():
        if len(digits) == 11 and digits[0] in "78":
            return f"+7{digits[1:]}"
        if len(digits) == 10 and digits.startswith("9"):
            return f"+7{digits}"
    return None


def validate_age(text: str) -> str | None:
    raw = text.strip().lower()
    match = re.fullmatch(r"(\d{1,2})\s*(?:год|года|лет)?", raw)
    if not match:
        return None
    age = int(match.group(1))
    if not 10 <= age <= 70:
        return None
    return str(age)


def validate_socials(text: str) -> str | None:
    raw = text.strip()
    if not raw:
        return None
    return raw


def validate_short_text(text: str, min_len: int = 4, max_len: int = 300) -> str | None:
    raw = " ".join(text.split())
    if not min_len <= len(raw) <= max_len:
        return None
    if raw.isdigit() and min_len > 2:
        return None
    return raw


def validate_custom_style(text: str) -> str | None:
    raw = " ".join(text.split())
    if not CUSTOM_STYLE_RE.fullmatch(raw):
        return None
    return raw
