import json
import sqlite3
from datetime import date, datetime, timedelta

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
                difficulty TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'subject',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                title TEXT NOT NULL,
                subject_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                planned_minutes INTEGER NOT NULL DEFAULT 0,
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

            CREATE TABLE IF NOT EXISTS excluded_blocks (
                day TEXT NOT NULL,
                block_key TEXT NOT NULL,
                PRIMARY KEY(day, block_key)
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

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day TEXT NOT NULL,
                event_type TEXT NOT NULL,
                todo_id INTEGER,
                subject_id INTEGER,
                block_key TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()
        self._ensure_column("todos", "planned_minutes", "INTEGER NOT NULL DEFAULT 0")

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            self.connection.commit()

    def now(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.connection.execute(
            """
            INSERT INTO settings(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.connection.commit()

    # ── Subjects ──────────────────────────────────────────────────────────────

    def ensure_other_category(self) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO subjects(name, difficulty, kind, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("기타", "", "other", self.now()),
        )
        self.connection.commit()

    def has_real_subjects(self) -> bool:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM subjects WHERE kind = 'subject'"
        ).fetchone()
        return row["count"] > 0

    def add_subject(self, name: str, difficulty: str = "") -> None:
        self.connection.execute(
            "INSERT INTO subjects(name, difficulty, kind, created_at) VALUES (?, ?, 'subject', ?)",
            (name, difficulty, self.now()),
        )
        self.connection.commit()

    def delete_subject(self, subject_id: int) -> None:
        todo_ids = [
            row["id"]
            for row in self.connection.execute(
                "SELECT id FROM todos WHERE subject_id = ?", (subject_id,)
            ).fetchall()
        ]
        for todo_id in todo_ids:
            self.delete_todo(todo_id)
        self.connection.execute(
            "DELETE FROM subjects WHERE id = ? AND kind = 'subject'", (subject_id,)
        )
        self.connection.commit()

    def subjects(self, include_other: bool = True) -> list[Subject]:
        sql = "SELECT id, name, difficulty, kind FROM subjects"
        if not include_other:
            sql += " WHERE kind = 'subject'"
        sql += " ORDER BY kind DESC, name ASC"
        return [Subject(**dict(row)) for row in self.connection.execute(sql).fetchall()]

    def todos_for_subject(self, subject_id: int) -> list:
        return self.connection.execute(
            "SELECT id, title FROM todos WHERE subject_id = ?", (subject_id,)
        ).fetchall()

    # ── Todos ─────────────────────────────────────────────────────────────────

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
                   todos.planned_minutes,
                   subjects.name AS subject_name, subjects.kind AS subject_kind
            FROM todos
            JOIN subjects ON subjects.id = todos.subject_id
            WHERE todos.day = ?
            ORDER BY todos.id DESC
            """,
            (day,),
        ).fetchall()
        return [Todo(**dict(row)) for row in rows]

    # ── Brain Dump ────────────────────────────────────────────────────────────

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
        row = self.connection.execute(
            "SELECT content FROM brain_dumps WHERE day = ?", (day,)
        ).fetchone()
        return row["content"] if row else ""

    # ── Time Blocks ───────────────────────────────────────────────────────────

    def _recalculate_planned_minutes(self, todo_id: int) -> None:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM time_blocks WHERE todo_id = ?", (todo_id,)
        ).fetchone()
        self.connection.execute(
            "UPDATE todos SET planned_minutes = ? WHERE id = ?",
            (row["count"] * 10, todo_id),
        )

    def assign_block(self, day: str, block_key: str, todo_id: int) -> None:
        previous = self.connection.execute(
            "SELECT todo_id FROM time_blocks WHERE day = ? AND block_key = ?", (day, block_key)
        ).fetchone()
        previous_todo_id = previous["todo_id"] if previous else None
        self.connection.execute(
            """
            INSERT INTO time_blocks(day, block_key, todo_id)
            VALUES (?, ?, ?)
            ON CONFLICT(day, block_key) DO UPDATE SET todo_id = excluded.todo_id
            """,
            (day, block_key, todo_id),
        )
        if previous_todo_id is not None and previous_todo_id != todo_id:
            self._recalculate_planned_minutes(previous_todo_id)
        self._recalculate_planned_minutes(todo_id)
        self.connection.commit()

    def delete_block(self, day: str, block_key: str) -> None:
        previous = self.connection.execute(
            "SELECT todo_id FROM time_blocks WHERE day = ? AND block_key = ?", (day, block_key)
        ).fetchone()
        self.connection.execute(
            "DELETE FROM time_blocks WHERE day = ? AND block_key = ?", (day, block_key)
        )
        if previous:
            self._recalculate_planned_minutes(previous["todo_id"])
        self.connection.commit()

    def clear_blocks_for_day(self, day: str) -> None:
        todo_ids = [
            row["todo_id"]
            for row in self.connection.execute(
                "SELECT DISTINCT todo_id FROM time_blocks WHERE day = ?", (day,)
            ).fetchall()
        ]
        self.connection.execute("DELETE FROM time_blocks WHERE day = ?", (day,))
        for todo_id in todo_ids:
            self._recalculate_planned_minutes(todo_id)
        self.connection.commit()

    def clear_unprotected_blocks_for_day(self, day: str) -> None:
        """블록 시간대에 타이머가 실제로 작동한 블록만 보호하고 나머지 삭제."""
        blocks = self.connection.execute(
            "SELECT block_key, todo_id FROM time_blocks WHERE day = ?", (day,)
        ).fetchall()
        affected_todo_ids = set()
        for block in blocks:
            if not self.block_has_timer_records(day, block["block_key"]):
                self.connection.execute(
                    "DELETE FROM time_blocks WHERE day = ? AND block_key = ?",
                    (day, block["block_key"]),
                )
                affected_todo_ids.add(block["todo_id"])
        for todo_id in affected_todo_ids:
            self._recalculate_planned_minutes(todo_id)
        self.connection.commit()

    def block_has_timer_records(self, day: str, block_key: str) -> bool:
        """블록 시간대(10분 창)에 실제로 타이머가 작동한 기록이 있는지 확인."""
        hour, minute = map(int, block_key.split(":"))
        block_start = f"{day}T{hour:02d}:{minute:02d}:00"
        end_minute = minute + 10
        end_hour = hour + end_minute // 60
        end_minute = end_minute % 60
        block_end = f"{day}T{end_hour:02d}:{end_minute:02d}:00"
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM timer_records
            WHERE day = ?
            AND event_type IN ('focus', 'break', 'long_break')
            AND started_at < ?
            AND ended_at > ?
            """,
            (day, block_end, block_start),
        ).fetchone()
        return row["count"] > 0

    def blocks_for_day(self, day: str) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT block_key, todo_id FROM time_blocks WHERE day = ?", (day,)
        ).fetchall()
        return {row["block_key"]: row["todo_id"] for row in rows}

    # ── Excluded Blocks (제외 시간) ───────────────────────────────────────────

    def set_block_excluded(self, day: str, block_key: str, excluded: bool) -> None:
        if excluded:
            self.connection.execute(
                "INSERT OR IGNORE INTO excluded_blocks(day, block_key) VALUES (?, ?)",
                (day, block_key),
            )
        else:
            self.connection.execute(
                "DELETE FROM excluded_blocks WHERE day = ? AND block_key = ?", (day, block_key)
            )
        self.connection.commit()

    def is_block_excluded(self, day: str, block_key: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM excluded_blocks WHERE day = ? AND block_key = ?", (day, block_key)
        ).fetchone()
        return row is not None

    def excluded_blocks_for_day(self, day: str) -> set[str]:
        rows = self.connection.execute(
            "SELECT block_key FROM excluded_blocks WHERE day = ?", (day,)
        ).fetchall()
        return {row["block_key"] for row in rows}

    # ── Timer Records ─────────────────────────────────────────────────────────

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
            INSERT INTO timer_records(day, todo_id, subject_id, block_key, event_type,
                                      started_at, ended_at, seconds, memo, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day, todo_id, subject_id, block_key, event_type,
                started_at, ended_at, seconds, memo, self.now(),
            ),
        )
        self.connection.commit()

    def delete_timer_records_by_memo(self, memo: str) -> None:
        self.connection.execute("DELETE FROM timer_records WHERE memo = ?", (memo,))
        self.connection.commit()

    def timer_records_for_day(self, day: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT timer_records.*, todos.title AS todo_title,
                   subjects.name AS subject_name, subjects.kind AS subject_kind
            FROM timer_records
            JOIN todos ON todos.id = timer_records.todo_id
            JOIN subjects ON subjects.id = timer_records.subject_id
            WHERE timer_records.day = ?
            ORDER BY timer_records.id ASC
            """,
            (day,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ── Event Logs ───────────────────────────────────────────────────────────

    def add_event_log(
        self,
        day: str,
        event_type: str,
        todo_id: int | None = None,
        subject_id: int | None = None,
        block_key: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO event_logs(day, event_type, todo_id, subject_id, block_key, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                day,
                event_type,
                todo_id,
                subject_id,
                block_key,
                json.dumps(metadata or {}, ensure_ascii=False),
                self.now(),
            ),
        )
        self.connection.commit()

    def event_logs_for_days(self, days: list[str]) -> list[dict]:
        if not days:
            return []
        placeholders = ",".join("?" for _ in days)
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM event_logs
            WHERE day IN ({placeholders})
            ORDER BY id ASC
            """,
            tuple(days),
        ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            try:
                event["metadata"] = json.loads(event["metadata"] or "{}")
            except json.JSONDecodeError:
                event["metadata"] = {}
            events.append(event)
        return events

    def activity_days(self, limit: int = 14) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT day FROM todos
            UNION
            SELECT day FROM time_blocks
            UNION
            SELECT day FROM timer_records
            UNION
            SELECT day FROM brain_dumps
            UNION
            SELECT day FROM excluded_blocks
            UNION
            SELECT day FROM event_logs
            ORDER BY day DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row["day"] for row in rows]

    def reset_all_data(self) -> None:
        """모든 사용자 데이터 삭제 (과목·설정 제외, 기타 카테고리 유지)."""
        self.connection.executescript(
            """
            DELETE FROM timer_records;
            DELETE FROM time_blocks;
            DELETE FROM excluded_blocks;
            DELETE FROM brain_dumps;
            DELETE FROM todos;
            DELETE FROM subjects WHERE kind = 'subject';
            """
        )
        self.connection.commit()
        self.ensure_other_category()

    def today(self) -> str:
        return date.today().isoformat()

    # ── Sample Data ───────────────────────────────────────────────────────────

    def add_sample_data(self, day: str) -> None:
        """Study Stats(도넛/과목별 통계)·TimePlan·ToDoList 등 모든 기능을 실제 사용한 것처럼
        현재 시각 기준 완료/진행 중/예정 표본 데이터로 점검할 수 있게 추가."""
        subjects = self.subjects(include_other=False)
        if len(subjects) < 2:
            existing_names = {s.name for s in subjects}
            for name, difficulty in (("수학", "어려움"), ("영어", "보통")):
                if name not in existing_names:
                    self.add_subject(name, difficulty)
            subjects = self.subjects(include_other=False)
        subject_a, subject_b = subjects[0], subjects[1]

        self.add_todo(day, "표본 — 완료한 공부", subject_a.id)
        self.add_todo(day, "표본 — 진행 중인 공부", subject_b.id)
        self.add_todo(day, "표본 — 앞으로 할 공부", subject_a.id)

        sample_todos = {
            todo.title: todo
            for todo in self.todos_for_day(day)
            if todo.title.startswith("표본 — ")
        }
        todo_done = sample_todos["표본 — 완료한 공부"]
        todo_active = sample_todos["표본 — 진행 중인 공부"]
        todo_upcoming = sample_todos["표본 — 앞으로 할 공부"]

        # 모든 시각은 day 날짜 안쪽(0~23:50)으로 고정(clamp)한다.
        # datetime.now() 기준으로 그냥 +/- timedelta를 하면 자정 근처에서 날짜가
        # day와 달라져, TimePlan의 타이머 작동 오버레이(같은 날짜만 그림)와
        # Study Stats의 합계가 서로 어긋나는 문제가 있었다.
        day_date = date.fromisoformat(day)
        day_midnight = datetime.combine(day_date, datetime.min.time())
        now = datetime.now()
        minute_of_day = now.hour * 60 + now.minute
        current_block_minute = (minute_of_day // 10) * 10
        is_today = day == date.today().isoformat()

        def clamp_minute(m: int) -> int:
            return max(0, min(1439, m))

        def at_minute(m: int) -> datetime:
            return day_midnight + timedelta(minutes=clamp_minute(m))

        def block_key_for_minute(m: int) -> str:
            m = max(0, min(1430, (clamp_minute(m) // 10) * 10))
            return f"{m // 60:02d}:{m % 60:02d}"

        def assign_range(start_minute: int, end_minute: int, todo_id: int) -> None:
            cursor = (clamp_minute(start_minute) // 10) * 10
            end_minute = (clamp_minute(end_minute) // 10) * 10
            while cursor < end_minute:
                self.assign_block(day, block_key_for_minute(cursor), todo_id)
                cursor += 10

        # 1) 이미 끝낸 일 — 1시간 전 ~ 30분 전, 완료 처리 + 실제 타이머(focus) 기록
        done_start_m = current_block_minute - 60
        done_end_m = current_block_minute - 30
        assign_range(done_start_m, done_end_m, todo_done.id)
        self.set_todo_status(todo_done.id, "done")
        done_start, done_end = at_minute(done_start_m), at_minute(done_end_m)
        if done_end > done_start:
            self.add_timer_record(
                day, todo_done.id, subject_a.id, block_key_for_minute(done_start_m), "focus",
                int((done_end - done_start).total_seconds()),
                done_start.isoformat(timespec="seconds"), done_end.isoformat(timespec="seconds"),
                "sample-data-session",
            )

        # 2) 지금 진행 중인 일 — 현재 블록을 포함한 구간, 지금까지 경과한 실제 타이머(focus) 기록
        active_start_m = current_block_minute - 10
        active_end_m = current_block_minute + 20
        assign_range(active_start_m, active_end_m, todo_active.id)
        active_start = at_minute(active_start_m)
        # day가 오늘이 아니면 "지금"이라는 개념이 없으므로 진행 구간이 끝난 것으로 간주한다.
        active_now = now if is_today else at_minute(active_end_m)
        elapsed = max(60, int((active_now - active_start).total_seconds()))
        self.add_timer_record(
            day, todo_active.id, subject_b.id, block_key_for_minute(active_start_m), "focus",
            elapsed,
            active_start.isoformat(timespec="seconds"), active_now.isoformat(timespec="seconds"),
            "sample-data-session",
        )

        # 3) 앞으로 할 일 — 1~2시간 뒤, 계획만 존재(타이머 기록 없음)
        upcoming_start_m = current_block_minute + 60
        upcoming_end_m = current_block_minute + 120
        assign_range(upcoming_start_m, upcoming_end_m, todo_upcoming.id)
