import logging
import os

import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from storage_common import SHEET_TITLES, a1_column, sheet_headers, sheet_values

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    "masters-msc-bot-47f443f738d7.json",
)
SPREADSHEET_ID = os.getenv(
    "GOOGLE_SHEETS_ID",
    "1mbzIQ5Kl0RJf4BneqYTAMgBdMyHRlVc-1OpNTSyCgLU",
).strip()


class GoogleSheets:
    def __init__(self) -> None:
        self._book = None
        self._sheets: dict[str, gspread.Worksheet] = {}

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

    def _worksheet(self, event_type: str):
        if event_type in self._sheets:
            return self._sheets[event_type]
        title = SHEET_TITLES[event_type]
        book = self._spreadsheet()
        worksheet = None
        for item in book.worksheets():
            if item.title.casefold() == title.casefold():
                worksheet = item
                break
        if worksheet is None:
            worksheet = book.add_worksheet(
                title=title,
                rows=200,
                cols=len(sheet_headers(event_type)),
            )
        headers = sheet_headers(event_type)
        current = worksheet.row_values(1)
        if current != headers:
            end = a1_column(len(headers))
            worksheet.update(f"A1:{end}1", [headers], value_input_option="USER_ENTERED")
        self._sheets[event_type] = worksheet
        return worksheet

    def upsert(self, record: dict) -> None:
        if not SPREADSHEET_ID:
            logging.info("Google Sheets пропущен: GOOGLE_SHEETS_ID не задан")
            return
        event_type = record["event_type"]
        worksheet = self._worksheet(event_type)
        headers = sheet_headers(event_type)
        values = sheet_values(record)
        existing = worksheet.get_all_values()
        header = existing[0] if existing else headers
        uid_idx = header.index("Telegram ID") if "Telegram ID" in header else 0
        row_number = None
        user_id = str(record["user_id"])
        for index, current in enumerate(existing[1:], start=2):
            padded = current + [""] * (len(header) - len(current))
            if padded[uid_idx] == user_id:
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
