from datetime import datetime

from form import display_value, fields_for, price_for

PAID = "оплачено"
UNPAID = "не оплачено"

SHEET_TITLES = {
    "casting": "Кастинг",
    "class": "Класс",
}


def payment_label(record: dict) -> str:
    if record.get("payment") in {PAID, UNPAID}:
        return record["payment"]
    if record.get("status") == "registered":
        return PAID
    return UNPAID


def sheet_headers(event_type: str) -> list[str]:
    return (
        ["Telegram ID", "Username"]
        + [field.title for field in fields_for(event_type)]
        + ["Оплата"]
    )


def sheet_values(record: dict) -> list[str]:
    event_type = record.get("event_type", "")
    answers = record.get("answers") or {}
    values = [
        str(record.get("user_id", "") or ""),
        str(record.get("username") or ""),
    ]
    for field in fields_for(event_type):
        raw = answers.get(field.id, "")
        values.append("" if raw in ("", None) else str(display_value(raw)))
    values.append(payment_label(record))
    return values


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
    headers = sheet_headers(event_type)
    values = sheet_values(record)
    row = dict(zip(headers, values))
    row["event_type"] = event_type
    row["price"] = record.get("price") or (price_for(event_type) if event_type else "")
    row["updated_at"] = _fmt_dt(record.get("updated_at")) or datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return row
