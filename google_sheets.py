import logging
import os
import time

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from requests.exceptions import ConnectionError, SSLError, Timeout

from storage_common import SHEET_TITLES, a1_column, sheet_headers, sheet_row_matches, sheet_values

load_dotenv()


def _env_value(name: str, default: str = "") -> str:
    raw = os.getenv(name) or default
    return raw.split("#", 1)[0].strip()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SERVICE_ACCOUNT_FILE = _env_value(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "masters-msc-bot-47f443f738d7.json",
)
SPREADSHEET_ID = _env_value(
    "GOOGLE_SHEETS_ID",
    "152jO_hpBpKLeHzoQz8wyVJ2xwYPUe2z0hKmjvOemX3M",
)

_RETRYABLE = (SSLError, ConnectionError, Timeout, OSError)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _RETRYABLE):
        return True
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and cause is not exc and _is_retryable(cause):
        return True
    text = str(exc).casefold()
    return any(
        token in text
        for token in ("ssl", "unexpected_eof", "max retries", "connection aborted")
    )


class GoogleSheets:
    def __init__(self) -> None:
        self._book = None
        self._sheets: dict[str, gspread.Worksheet] = {}

    def _reset(self) -> None:
        self._book = None
        self._sheets = {}

    def _spreadsheet(self):
        if self._book is not None:
            return self._book
        if not SPREADSHEET_ID:
            raise RuntimeError("GOOGLE_SHEETS_ID не задан в .env")
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            raise RuntimeError(
                f"Файл сервисного аккаунта не найден: {SERVICE_ACCOUNT_FILE}"
            )
        credentials = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=SCOPES,
        )
        self._book = gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)
        return self._book

    def _worksheet(self, event_type: str, kids_role: str | None = None):
        cache_key = event_type
        if cache_key in self._sheets:
            return self._sheets[cache_key]
        title = SHEET_TITLES[event_type]
        book = self._spreadsheet()
        worksheet = None
        for item in book.worksheets():
            if item.title.strip().casefold() == title.casefold():
                worksheet = item
                break
        if worksheet is None:
            worksheet = book.add_worksheet(
                title=title,
                rows=200,
                cols=len(sheet_headers(event_type, kids_role)),
            )
        headers = sheet_headers(event_type, kids_role)
        current = worksheet.row_values(1)
        if current != headers:
            end = a1_column(len(headers))
            worksheet.update(f"A1:{end}1", [headers], value_input_option="USER_ENTERED")
        self._sheets[cache_key] = worksheet
        return worksheet

    def _upsert_once(self, record: dict) -> None:
        event_type = record["event_type"]
        worksheet = self._worksheet(event_type, record.get("kids_role"))
        headers = sheet_headers(event_type, record.get("kids_role"))
        values = sheet_values(record)
        existing = worksheet.get_all_values()
        header = existing[0] if existing else headers
        row_number = None
        for index, current in enumerate(existing[1:], start=2):
            if sheet_row_matches(header, current, record):
                row_number = index
                break
        if row_number is None:
            worksheet.append_row(values, value_input_option="USER_ENTERED")
            return
        end = a1_column(len(headers))
        worksheet.update(
            f"A{row_number}:{end}{row_number}",
            [values],
            value_input_option="USER_ENTERED",
        )

    def upsert(self, record: dict) -> None:
        if not SPREADSHEET_ID:
            logging.info("Google Sheets пропущен: GOOGLE_SHEETS_ID не задан")
            return
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                self._upsert_once(record)
                return
            except Exception as exc:
                if not _is_retryable(exc) or attempt == 3:
                    self._reset()
                    raise
                last_error = exc
                logging.warning(
                    "Google Sheets SSL/сеть, попытка %s/3: %s",
                    attempt,
                    exc,
                )
                self._reset()
                time.sleep(0.7 * attempt)
        if last_error:
            raise last_error
