import os

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv

from form import fields_for
from storage_common import PAID, UNPAID

load_dotenv()

DB_NAME = os.getenv("POSTGRES_DB", "Masters_MSC_bot")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DB_CONFIG = {
    "dbname": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "host": DB_HOST,
    "port": DB_PORT,
}

TABLE_BY_EVENT = {
    "casting": "casting",
    "class": "class_signups",
}

CASTING_ANSWER_COLUMNS = [field.id for field in fields_for("casting")]
CLASS_ANSWER_COLUMNS = [field.id for field in fields_for("class")]
ANSWER_COLUMNS = {
    "casting": CASTING_ANSWER_COLUMNS,
    "class": CLASS_ANSWER_COLUMNS,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS event_logs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id BIGINT,
    username TEXT,
    full_name TEXT,
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS event_logs_created_at_idx ON event_logs (created_at);
CREATE INDEX IF NOT EXISTS event_logs_user_id_idx ON event_logs (user_id);

CREATE TABLE IF NOT EXISTS casting (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    fio TEXT,
    age TEXT,
    contact TEXT,
    socials TEXT,
    experience TEXT,
    main_styles TEXT,
    other_styles TEXT,
    team_exp TEXT,
    events TEXT,
    knows TEXT,
    why TEXT,
    goals TEXT,
    time TEXT,
    money TEXT,
    payment TEXT NOT NULL DEFAULT 'не оплачено',
    current_index INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS class_signups (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    fio TEXT,
    contact TEXT,
    payment TEXT NOT NULL DEFAULT 'не оплачено',
    current_index INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _admin_config() -> dict:
    config = dict(DB_CONFIG)
    config["dbname"] = "postgres"
    return config


def ensure_database() -> None:
    conn = psycopg2.connect(**_admin_config())
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{DB_NAME}"')
    finally:
        conn.close()


def _flatten_answers(event_type: str, answers: dict) -> dict:
    flat = {}
    for field_id in ANSWER_COLUMNS[event_type]:
        value = answers.get(field_id, "")
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        flat[field_id] = value or None
    return flat


class Database:
    def __init__(self) -> None:
        self.pool: SimpleConnectionPool | None = None

    def init(self) -> None:
        ensure_database()
        self.pool = SimpleConnectionPool(1, 8, **DB_CONFIG)
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
                self._migrate_legacy(cur)
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def _migrate_legacy(self, cur) -> None:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'registrations'
            )
            """
        )
        if not cur.fetchone()[0]:
            return
        cur.execute(
            """
            SELECT user_id, event_type, username, full_name, status,
                   current_index, answers
            FROM registrations
            """
        )
        for row in cur.fetchall():
            user_id, event_type, username, full_name, status, current_index, answers = row
            if event_type not in TABLE_BY_EVENT:
                continue
            payment = PAID if status == "registered" else UNPAID
            self._upsert_on_cursor(
                cur,
                {
                    "user_id": user_id,
                    "event_type": event_type,
                    "username": username,
                    "full_name": full_name,
                    "answers": answers or {},
                    "current_index": current_index,
                    "payment": payment,
                },
            )

    def _conn(self):
        if self.pool is None:
            raise RuntimeError("База данных не инициализирована")
        return self.pool.getconn()

    def log_event(
        self,
        *,
        action: str,
        user_id: int | None = None,
        username: str | None = None,
        full_name: str | None = None,
        details: dict | None = None,
    ) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO event_logs (user_id, username, full_name, action, details)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, username, full_name, action, Json(details or {})),
                )
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def _upsert_on_cursor(self, cur, record: dict) -> None:
        event_type = record["event_type"]
        table = TABLE_BY_EVENT[event_type]
        columns = ANSWER_COLUMNS[event_type]
        flat = _flatten_answers(event_type, record.get("answers") or {})
        all_columns = [
            "user_id",
            "username",
            "full_name",
            *columns,
            "payment",
            "current_index",
        ]
        values = [
            record["user_id"],
            record.get("username"),
            record.get("full_name"),
            *[flat[column] for column in columns],
            record.get("payment", UNPAID),
            record.get("current_index", 0),
        ]
        placeholders = ", ".join(["%s"] * len(all_columns))
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in all_columns
            if column != "user_id"
        )
        cur.execute(
            f"""
            INSERT INTO {table} ({", ".join(all_columns)})
            VALUES ({placeholders})
            ON CONFLICT (user_id) DO UPDATE SET
                {assignments},
                updated_at = NOW()
            """,
            values,
        )

    def upsert_registration(self, record: dict) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                self._upsert_on_cursor(cur, record)
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def get_registration(self, user_id: int, event_type: str) -> dict | None:
        table = TABLE_BY_EVENT[event_type]
        columns = ANSWER_COLUMNS[event_type]
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT user_id, username, full_name, payment, current_index,
                           created_at, updated_at, {", ".join(columns)}
                    FROM {table}
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                data = dict(row)
                answers = {}
                for field_id in columns:
                    value = data.pop(field_id)
                    if value not in (None, ""):
                        answers[field_id] = value
                payment = data.get("payment") or UNPAID
                current_index = int(data.get("current_index") or 0)
                total = len(columns)
                if payment == PAID:
                    status = "registered"
                elif current_index >= total:
                    status = "waiting_payment"
                else:
                    status = "in_progress"
                return {
                    **data,
                    "event_type": event_type,
                    "answers": answers,
                    "status": status,
                    "payment": payment,
                }
        finally:
            self.pool.putconn(conn)
