import os

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv

from form import fields_for
from storage_common import NO_PAYMENT, PAID, UNPAID

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
    "kids": "kids_signups",
}

CASTING_ANSWER_COLUMNS = [field.id for field in fields_for("casting")]
CLASS_ANSWER_COLUMNS = [field.id for field in fields_for("class")]
KIDS_ANSWER_COLUMNS = [field.id for field in fields_for("kids", "child")]
ANSWER_COLUMNS = {
    "casting": CASTING_ANSWER_COLUMNS,
    "class": CLASS_ANSWER_COLUMNS,
    "kids": KIDS_ANSWER_COLUMNS,
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

CREATE TABLE IF NOT EXISTS kids_signups (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT,
    full_name TEXT,
    kids_role TEXT,
    child_fio TEXT,
    child_age TEXT,
    parent_fio TEXT,
    parent_phone TEXT,
    main_styles TEXT,
    other_styles TEXT,
    experience TEXT,
    payment TEXT NOT NULL DEFAULT 'не оплачено',
    current_index INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS kids_signups_user_id_idx ON kids_signups (user_id);
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
                self._migrate_kids_multi_child(cur)
                self._migrate_legacy(cur)
            conn.commit()
        finally:
            self.pool.putconn(conn)

    def _migrate_kids_multi_child(self, cur) -> None:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'kids_signups'
            )
            """
        )
        if not cur.fetchone()[0]:
            return
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'kids_signups' AND column_name = 'id'
            """
        )
        has_id = cur.fetchone() is not None
        cur.execute(
            """
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name = 'kids_signups' AND constraint_type = 'PRIMARY KEY'
            """
        )
        pk = cur.fetchone()
        if not has_id:
            if pk:
                cur.execute(f'ALTER TABLE kids_signups DROP CONSTRAINT "{pk[0]}"')
            cur.execute("ALTER TABLE kids_signups ADD COLUMN id BIGSERIAL PRIMARY KEY")
        cur.execute("CREATE INDEX IF NOT EXISTS kids_signups_user_id_idx ON kids_signups (user_id)")

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
                    "kids_role": None,
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

    def _upsert_on_cursor(self, cur, record: dict) -> int | None:
        event_type = record["event_type"]
        table = TABLE_BY_EVENT[event_type]
        columns = ANSWER_COLUMNS[event_type]
        flat = _flatten_answers(event_type, record.get("answers") or {})
        base_columns = [
            "user_id",
            "username",
            "full_name",
        ]
        values = [
            record["user_id"],
            record.get("username"),
            record.get("full_name"),
        ]
        if event_type == "kids":
            base_columns.append("kids_role")
            values.append(record.get("kids_role"))

        all_columns = [
            *base_columns,
            *columns,
            "payment",
            "current_index",
        ]
        default_payment = UNPAID
        values.extend([flat[column] for column in columns])
        values.extend(
            [
                record.get("payment", default_payment),
                record.get("current_index", 0),
            ]
        )
        if event_type == "kids":
            return self._upsert_kids(cur, all_columns, values, record, len(columns))
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in all_columns
            if column != "user_id"
        )
        placeholders = ", ".join(["%s"] * len(all_columns))
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
        return None

    def _upsert_kids(self, cur, all_columns: list[str], values: list, record: dict, total: int) -> int:
        assignments = ", ".join(
            f"{column} = %s" for column in all_columns if column != "user_id"
        )
        update_values = [
            values[all_columns.index(column)]
            for column in all_columns
            if column != "user_id"
        ]
        record_id = record.get("record_id") or record.get("id")
        if not record_id:
            cur.execute(
                """
                SELECT id FROM kids_signups
                WHERE user_id = %s AND current_index < %s
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (record["user_id"], total),
            )
            found = cur.fetchone()
            if found:
                record_id = found[0]
        if record_id:
            cur.execute(
                f"""
                UPDATE kids_signups
                SET {assignments}, updated_at = NOW()
                WHERE id = %s
                """,
                [*update_values, record_id],
            )
            return int(record_id)
        placeholders = ", ".join(["%s"] * len(all_columns))
        cur.execute(
            f"""
            INSERT INTO kids_signups ({", ".join(all_columns)})
            VALUES ({placeholders})
            RETURNING id
            """,
            values,
        )
        return int(cur.fetchone()[0])

    def upsert_registration(self, record: dict) -> int | None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                record_id = self._upsert_on_cursor(cur, record)
            conn.commit()
            return record_id
        finally:
            self.pool.putconn(conn)

    def _row_to_registration(self, event_type: str, row) -> dict:
        columns = ANSWER_COLUMNS[event_type]
        data = dict(row)
        answers = {}
        for field_id in columns:
            value = data.pop(field_id, None)
            if value not in (None, ""):
                answers[field_id] = value
        payment = data.get("payment") or UNPAID
        current_index = int(data.get("current_index") or 0)
        total = len(columns)
        if payment in {PAID, NO_PAYMENT}:
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
            "record_id": data.get("id"),
        }

    def get_registration(self, user_id: int, event_type: str) -> dict | None:
        table = TABLE_BY_EVENT[event_type]
        columns = ANSWER_COLUMNS[event_type]
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                select_head = "user_id, username, full_name"
                if event_type == "kids":
                    select_head = "id, " + select_head + ", kids_role"
                cur.execute(
                    f"""
                    SELECT {select_head}, payment, current_index,
                           created_at, updated_at, {", ".join(columns)}
                    FROM {table}
                    WHERE user_id = %s
                    ORDER BY
                        CASE
                            WHEN current_index < %s THEN 0
                            WHEN COALESCE(payment, '') NOT IN (%s, %s) THEN 1
                            ELSE 2
                        END,
                        updated_at DESC
                    LIMIT 1
                    """,
                    (user_id, len(columns), PAID, NO_PAYMENT),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = self._row_to_registration(event_type, row)
                if event_type == "kids":
                    cur.execute(
                        """
                        SELECT child_fio FROM kids_signups
                        WHERE user_id = %s
                          AND kids_role = 'parent'
                          AND payment IN (%s, %s)
                          AND child_fio IS NOT NULL AND child_fio <> ''
                        ORDER BY updated_at
                        """,
                        (user_id, PAID, NO_PAYMENT),
                    )
                    result["registered_children"] = [
                        item["child_fio"] for item in cur.fetchall()
                    ]
                    cur.execute(
                        """
                        SELECT child_fio FROM kids_signups
                        WHERE user_id = %s
                          AND kids_role = 'child'
                          AND payment IN (%s, %s)
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (user_id, PAID, NO_PAYMENT),
                    )
                    self_row = cur.fetchone()
                    result["self_registered"] = self_row is not None
                    result["self_child_fio"] = (
                        self_row["child_fio"] if self_row else None
                    )
                return result
        finally:
            self.pool.putconn(conn)

    def list_registrations(self, event_type: str) -> list[dict]:
        table = TABLE_BY_EVENT[event_type]
        columns = ANSWER_COLUMNS[event_type]
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                select_head = "user_id, username, full_name"
                if event_type == "kids":
                    select_head = "id, " + select_head + ", kids_role"
                cur.execute(
                    f"""
                    SELECT {select_head}, payment, current_index,
                           created_at, updated_at, {", ".join(columns)}
                    FROM {table}
                    ORDER BY updated_at
                    """
                )
                return [
                    self._row_to_registration(event_type, row)
                    for row in cur.fetchall()
                ]
        finally:
            self.pool.putconn(conn)
