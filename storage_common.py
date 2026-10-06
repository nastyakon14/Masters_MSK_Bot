from datetime import datetime

from form import display_value, fields_for, price_for

PAID = "оплачено"
UNPAID = "не оплачено"
NO_PAYMENT = "не требуется"

SHEET_TITLES = {
    "casting": "Кастинг",
    "class": "Класс",
    "kids": "Дети",
}


def payment_label(record: dict) -> str:
    if record.get("payment") in {PAID, UNPAID, NO_PAYMENT}:
        return record["payment"]
    if record.get("status") == "registered":
        return PAID
    return UNPAID


def sheet_headers(event_type: str, kids_role: str | None = None) -> list[str]:
    return (
        ["Telegram ID", "Username"]
        + [field.title for field in fields_for(event_type, kids_role)]
        + ["Оплата"]
    )


def sheet_values(record: dict) -> list[str]:
    event_type = record.get("event_type", "")
    kids_role = record.get("kids_role")
    answers = record.get("answers") or {}
    values = [
        str(record.get("user_id", "") or ""),
        str(record.get("username") or ""),
    ]
    for field in fields_for(event_type, kids_role):
        raw = answers.get(field.id, "")
        values.append("" if raw in ("", None) else str(display_value(raw)))
    values.append(payment_label(record))
    return values


def sheet_row_matches(header: list[str], current: list[str], record: dict) -> bool:
    padded = current + [""] * (len(header) - len(current))
    uid_idx = header.index("Telegram ID") if "Telegram ID" in header else 0
    if str(padded[uid_idx]) != str(record.get("user_id", "")):
        return False
    if record.get("event_type") != "kids":
        return True
    child_title = "ФИО ребенка"
    if child_title not in header:
        return True
    child_idx = header.index(child_title)
    existing = str(padded[child_idx] or "").strip()
    incoming = str((record.get("answers") or {}).get("child_fio") or "").strip()
    if incoming:
        return existing.casefold() == incoming.casefold() or existing == ""
    return existing == ""


def a1_column(index: int) -> str:
    name = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _fmt_dt(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value or "")


def registration_row(record: dict) -> dict:
    """Flat dict for internal use / Excel fallback."""
    event_type = record.get("event_type", "")
    headers = sheet_headers(event_type, record.get("kids_role"))
    values = sheet_values(record)
    row = dict(zip(headers, values))
    row["event_type"] = event_type
    row["price"] = record.get("price") or (price_for(event_type) if event_type else "")
    row["updated_at"] = _fmt_dt(record.get("updated_at")) or datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return row
