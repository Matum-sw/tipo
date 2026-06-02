import sqlite3
from datetime import date, datetime

from core.models import Subject, Todo
from core.paths import DATA_DIR, DB_FILE


class SQLiteStore:
    def __init__(self, path=DB_FILE):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.migrate()
        self.ensure_other_category()

    def migrate(self) -> None:
        cursor = self.connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                difficulty TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'subject',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                title TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                FOREIGN KEY(subject_id) REFERENCES subjects(id)
            );

            CREATE TABLE IF NOT EXISTS brain_dumps (
                day TEXT PRIMARY KEY,
                content TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS time_blocks (
                day TEXT NOT NULL,
                block_key TEXT NOT NULL,
                todo_id INTEGER NOT NULL,
                PRIMARY KEY(day, block_key),
                FOREIGN KEY(todo_id) REFERENCES todos(id)
            );

            CREATE TABLE IF NOT EXISTS timer_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                todo_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                block_key TEXT,
                event_type TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                seconds INTEGER NOT NULL DEFAULT 0,
                memo TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(todo_id) REFERENCES todos(id),
                FOREIGN KEY(subject_id) REFERENCES subjects(id)
            );
            """
        )
        self.connection.commit()

    def now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def ensure_other_category(self) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO subjects(name, difficulty, kind, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("기타", "카테고리", "other", self.now()),
        )
        self.connection.commit()

    def has_real_subjects(self) -> bool:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM subjects WHERE kind = 'subject'").fetchone()
        return row["count"] > 0

    def add_subject(self, name: str, difficulty: str) -> None:
        self.connection.execute(
            "INSERT INTO subjects(name, difficulty, kind, created_at) VALUES (?, ?, 'subject', ?)",
            (name, difficulty, self.now()),
        )
        self.connection.commit()

    def delete_subject(self, subject_id: int) -> None:
        self.connection.execute("DELETE FROM subjects WHERE id = ? AND kind = 'subject'", (subject_id,))
        self.connection.commit()

    def subjects(self, include_other: bool = True) -> list[Subject]:
        sql = "SELECT id, name, difficulty, kind FROM subjects"
        if not include_other:
            sql += " WHERE kind = 'subject'"
        sql += " ORDER BY kind DESC, name ASC"
        return [Subject(**dict(row)) for row in self.connection.execute(sql).fetchall()]

    def add_todo(self, day: str, title: str, subject_id: int) -> None:
        self.connection.execute(
            "INSERT INTO todos(day, title, subject_id, status, created_at) VALUES (?, ?, ?, 'open', ?)",
            (day, title, subject_id, self.now()),
        )
        self.connection.commit()

    def set_todo_status(self, todo_id: int, status: str) -> None:
        self.connection.execute("UPDATE todos SET status = ? WHERE id = ?", (status, todo_id))
        self.connection.commit()

    def delete_todo(self, todo_id: int) -> None:
        self.connection.execute("DELETE FROM time_blocks WHERE todo_id = ?", (todo_id,))
        self.connection.execute("DELETE FROM timer_records WHERE todo_id = ?", (todo_id,))
        self.connection.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self.connection.commit()

    def todos_for_day(self, day: str) -> list[Todo]:
        rows = self.connection.execute(
            """
            SELECT todos.id, todos.day, todos.title, todos.subject_id, todos.status,
                   subjects.name AS subject_name, subjects.kind AS subject_kind
            FROM todos
            JOIN subjects ON subjects.id = todos.subject_id
            WHERE todos.day = ?
            ORDER BY todos.id DESC
            """,
            (day,),
        ).fetchall()
        return [Todo(**dict(row)) for row in rows]

    def save_brain_dump(self, day: str, content: str) -> None:
        self.connection.execute(
            """
            INSERT INTO brain_dumps(day, content, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(day) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at
            """,
            (day, content, self.now()),
        )
        self.connection.commit()

    def brain_dump(self, day: str) -> str:
        row = self.connection.execute("SELECT content FROM brain_dumps WHERE day = ?", (day,)).fetchone()
        return row["content"] if row else ""

    def assign_block(self, day: str, block_key: str, todo_id: int) -> None:
        self.connection.execute(
            """
            INSERT INTO time_blocks(day, block_key, todo_id)
            VALUES (?, ?, ?)
            ON CONFLICT(day, block_key) DO UPDATE SET todo_id = excluded.todo_id
            """,
            (day, block_key, todo_id),
        )
        self.connection.commit()

    def delete_block(self, day: str, block_key: str) -> None:
        self.connection.execute("DELETE FROM time_blocks WHERE day = ? AND block_key = ?", (day, block_key))
        self.connection.commit()

    def clear_blocks_for_day(self, day: str) -> None:
        self.connection.execute("DELETE FROM time_blocks WHERE day = ?", (day,))
        self.connection.commit()

    def clear_unprotected_blocks_for_day(self, day: str) -> None:
        """타이머 기록이 없는 블록만 삭제 (타이머 작동 블록은 보호)."""
        self.connection.execute(
            """
            DELETE FROM time_blocks
            WHERE day = ?
            AND NOT EXISTS (
                SELECT 1 FROM timer_records tr
                WHERE tr.todo_id = time_blocks.todo_id
                AND tr.day = time_blocks.day
                AND tr.event_type IN ('focus', 'break', 'completed')
            )
            """,
            (day,),
        )
        self.connection.commit()

    def block_has_timer_records(self, day: str, block_key: str) -> bool:
        """해당 블록의 할 일에 타이머 기록이 있는지 확인."""
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM time_blocks tb
            INNER JOIN timer_records tr ON tr.todo_id = tb.todo_id AND tr.day = tb.day
            WHERE tb.day = ? AND tb.block_key = ?
            AND tr.event_type IN ('focus', 'break', 'completed')
            """,
            (day, block_key),
        ).fetchone()
        return row["count"] > 0

    def blocks_for_day(self, day: str) -> dict[str, int]:
        rows = self.connection.execute("SELECT block_key, todo_id FROM time_blocks WHERE day = ?", (day,)).fetchall()
        return {row["block_key"]: row["todo_id"] for row in rows}

    def add_timer_record(
        self,
        day: str,
        todo_id: int,
        subject_id: int,
        block_key: str | None,
        event_type: str,
        seconds: int = 0,
        started_at: str | None = None,
        ended_at: str | None = None,
        memo: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO timer_records(day, todo_id, subject_id, block_key, event_type, started_at, ended_at, seconds, memo, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (day, todo_id, subject_id, block_key, event_type, started_at, ended_at, seconds, memo, self.now()),
        )
        self.connection.commit()

    def delete_timer_records_by_memo(self, memo: str) -> None:
        self.connection.execute("DELETE FROM timer_records WHERE memo = ?", (memo,))
        self.connection.commit()

    def timer_records_for_day(self, day: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT timer_records.*, todos.title AS todo_title, subjects.name AS subject_name, subjects.kind AS subject_kind
            FROM timer_records
            JOIN todos ON todos.id = timer_records.todo_id
            JOIN subjects ON subjects.id = timer_records.subject_id
            WHERE timer_records.day = ?
            ORDER BY timer_records.id DESC
            """,
            (day,),
        ).fetchall()
        return [dict(row) for row in rows]

    def today(self) -> str:
        return date.today().isoformat()
