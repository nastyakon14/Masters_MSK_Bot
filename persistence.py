from __future__ import annotations

import logging
from aiogram.types import User

from db_connect import Database
from excel_store import ExcelStore
from form import price_for
from google_sheets import GoogleSheets
from storage_common import PAID, UNPAID


class Persistence:
    def __init__(self) -> None:
        self.db = Database()
        self.excel = ExcelStore()
        self.sheets = GoogleSheets()

    def init(self) -> None:
        self.db.init()

    def log(self, user: User | None, action: str, details: dict | None = None) -> None:
        self.db.log_event(
            action=action,
            user_id=user.id if user else None,
            username=user.username if user else None,
            full_name=user.full_name if user else None,
            details=details or {},
        )

    def save_registration(
        self,
        user: User,
        *,
        event_type: str,
        answers: dict,
        current_index: int,
        status: str,
    ) -> None:
        record = {
            "user_id": user.id,
            "event_type": event_type,
            "username": user.username,
            "full_name": user.full_name,
            "status": status,
            "current_index": current_index,
            "answers": answers,
            "price": price_for(event_type),
            "payment": PAID if status == "registered" else UNPAID,
        }
        self.db.upsert_registration(record)
        errors: list[Exception] = []
        try:
            self.excel.upsert(record)
        except Exception as exc:
            logging.exception("Не удалось сохранить Excel")
            errors.append(exc)
        try:
            self.sheets.upsert(record)
        except Exception as exc:
            logging.exception("Не удалось обновить Google Sheets")
            errors.append(exc)
        if errors:
            raise errors[0]

    def get_draft(self, user_id: int, event_type: str) -> dict | None:
        return self.db.get_registration(user_id, event_type)


persist = Persistence()
