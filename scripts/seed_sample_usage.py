import json
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "planner.sqlite3"
START_DAY = "2026-06-10"
END_DAY = "2026-06-14"

SUBJECTS = [
    "선형대수학",
    "시스템 프로그래밍",
    "컴퓨터 프로그래밍",
    "컴퓨터 프로그래밍 응용",
    "현실속 수학",
    "토익1",
    "오픈소스",
]

DIFFICULTY = {
    "선형대수학": "상",
    "시스템 프로그래밍": "상",
    "컴퓨터 프로그래밍": "중",
    "컴퓨터 프로그래밍 응용": "중상",
    "현실속 수학": "중",
    "토익1": "하",
    "오픈소스": "중",
}

TASKS_BY_DAY = {
    "2026-06-10": [
        ("선형대수학", "시험공부", "done"),
        ("시스템 프로그래밍", "온라인강의", "done"),
        ("토익1", "과제", "open"),
    ],
    "2026-06-11": [
        ("컴퓨터 프로그래밍", "과제", "done"),
        ("현실속 수학", "온라인강의", "done"),
        ("오픈소스", "시험공부", "deferred"),
        ("토익1", "온라인강의", "open"),
    ],
    "2026-06-12": [
        ("시스템 프로그래밍", "과제", "open"),
        ("컴퓨터 프로그래밍 응용", "시험공부", "done"),
        ("선형대수학", "온라인강의", "deferred"),
    ],
    "2026-06-13": [
        ("오픈소스", "과제", "done"),
        ("컴퓨터 프로그래밍", "시험공부", "done"),
        ("현실속 수학", "과제", "open"),
        ("토익1", "시험공부", "done"),
    ],
    "2026-06-14": [
        ("선형대수학", "과제", "open"),
        ("시스템 프로그래밍", "시험공부", "deferred"),
        ("컴퓨터 프로그래밍 응용", "온라인강의", "done"),
        ("오픈소스", "온라인강의", "open"),
    ],
}

PLAN_BY_DAY = {
    "2026-06-10": [("09:00", 5, 0), ("10:10", 4, 1), ("11:00", 3, 2), ("14:00", 4, 0)],
    "2026-06-11": [("08:50", 4, 0), ("09:40", 3, 1), ("10:30", 4, 2), ("13:30", 3, 3)],
    "2026-06-12": [("09:20", 6, 0), ("11:00", 4, 1), ("14:00", 4, 2)],
    "2026-06-13": [("10:00", 3, 0), ("10:40", 4, 1), ("13:00", 3, 2), ("15:00", 3, 3)],
    "2026-06-14": [("09:00", 5, 0), ("10:20", 5, 1), ("13:40", 3, 2), ("15:00", 3, 3)],
}

FOCUS_BY_DAY = {
    "2026-06-10": [(0, "09:02", 25), (0, "09:36", 18), (1, "10:12", 24), (1, "10:47", 16)],
    "2026-06-11": [(0, "08:55", 22), (1, "09:42", 26), (2, "10:35", 14)],
    "2026-06-12": [(0, "09:25", 20), (0, "10:05", 12), (1, "11:04", 27)],
    "2026-06-13": [(0, "10:03", 25), (1, "10:43", 28), (1, "11:22", 18), (3, "15:04", 24)],
    "2026-06-14": [(0, "09:08", 16), (1, "10:26", 18), (2, "13:43", 26)],
}

EVENTS_BY_DAY = {
    "2026-06-10": ["timer_paused", "break_skipped", "todo_completed", "todo_completed"],
    "2026-06-11": ["timer_paused", "timer_paused", "break_skipped", "todo_completed"],
    "2026-06-12": ["timer_paused", "timer_paused", "timer_stopped", "todo_completed"],
    "2026-06-13": ["break_skipped", "todo_completed", "todo_completed", "todo_completed"],
    "2026-06-14": ["timer_paused", "timer_paused", "break_skipped", "timer_stopped"],
}

BRAIN_DUMPS = {
    "2026-06-10": "선형대수학은 오전에 잘 됐고, 오후에는 토익 집중력이 떨어짐.",
    "2026-06-11": "오픈소스 시험공부까지 하려 했는데 생각보다 컴프 과제가 오래 걸림.",
    "2026-06-12": "시스템 프로그래밍 과제가 막혀서 일시정지가 많았음. 어려운 과목은 짧게 쪼개야 할 듯.",
    "2026-06-13": "낮 시간대가 가장 잘 맞음. 쉬운 토익을 마지막에 넣으니 완료하기 좋았음.",
    "2026-06-14": "계획을 많이 넣었지만 실제로는 2~3개 정도가 한계. 휴식 없이 몰아넣으면 멈추게 됨.",
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def time_keys(start: str, count: int) -> list[str]:
    base = datetime.strptime(start, "%H:%M")
    return [(base + timedelta(minutes=10 * i)).strftime("%H:%M") for i in range(count)]


def iso_at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00")


def ensure_subjects(conn: sqlite3.Connection) -> dict[str, int]:
    for subject in SUBJECTS:
        conn.execute(
            """
            INSERT INTO subjects(name, difficulty, kind, created_at)
            VALUES (?, ?, 'subject', ?)
            ON CONFLICT(name) DO NOTHING
            """,
            (subject, DIFFICULTY[subject], now()),
        )
    rows = conn.execute("SELECT id, name FROM subjects WHERE name IN (%s)" % ",".join("?" for _ in SUBJECTS), SUBJECTS)
    return {row["name"]: row["id"] for row in rows.fetchall()}


def clear_sample_range(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id FROM todos WHERE day BETWEEN ? AND ?",
        (START_DAY, END_DAY),
    ).fetchall()
    todo_ids = [row["id"] for row in rows]
    if todo_ids:
        placeholders = ",".join("?" for _ in todo_ids)
        conn.execute(f"DELETE FROM timer_records WHERE todo_id IN ({placeholders})", todo_ids)
        conn.execute(f"DELETE FROM time_blocks WHERE todo_id IN ({placeholders})", todo_ids)
    conn.execute("DELETE FROM todos WHERE day BETWEEN ? AND ?", (START_DAY, END_DAY))
    conn.execute("DELETE FROM brain_dumps WHERE day BETWEEN ? AND ?", (START_DAY, END_DAY))
    conn.execute("DELETE FROM event_logs WHERE day BETWEEN ? AND ?", (START_DAY, END_DAY))
    conn.execute("DELETE FROM time_blocks WHERE day BETWEEN ? AND ?", (START_DAY, END_DAY))
    conn.execute("DELETE FROM timer_records WHERE day BETWEEN ? AND ?", (START_DAY, END_DAY))


def add_timer_record(conn, day, todo_id, subject_id, block_key, event_type, start_dt, minutes, memo):
    end_dt = start_dt + timedelta(minutes=minutes)
    conn.execute(
        """
        INSERT INTO timer_records(day, todo_id, subject_id, block_key, event_type, started_at, ended_at, seconds, memo, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            day,
            todo_id,
            subject_id,
            block_key,
            event_type,
            start_dt.isoformat(timespec="seconds"),
            end_dt.isoformat(timespec="seconds"),
            minutes * 60,
            memo,
            now(),
        ),
    )


def seed() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"DB file not found: {DB_PATH}")

    backup = DB_PATH.with_suffix(f".sample-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3")
    shutil.copy2(DB_PATH, backup)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        subjects = ensure_subjects(conn)
        clear_sample_range(conn)

        for day, tasks in TASKS_BY_DAY.items():
            todo_ids = []
            for subject, title, status in tasks:
                cursor = conn.execute(
                    "INSERT INTO todos(day, title, subject_id, status, created_at) VALUES (?, ?, ?, ?, ?)",
                    (day, title, subjects[subject], status, f"{day}T07:50:00"),
                )
                todo_ids.append((cursor.lastrowid, subject, title))

            for start, block_count, todo_index in PLAN_BY_DAY[day]:
                todo_id = todo_ids[todo_index][0]
                for key in time_keys(start, block_count):
                    conn.execute(
                        """
                        INSERT INTO time_blocks(day, block_key, todo_id)
                        VALUES (?, ?, ?)
                        ON CONFLICT(day, block_key) DO UPDATE SET todo_id = excluded.todo_id
                        """,
                        (day, key, todo_id),
                    )

            memo = f"sample-{day}"
            for todo_index, start, focus_minutes in FOCUS_BY_DAY[day]:
                todo_id, subject, _title = todo_ids[todo_index]
                block_key = start[:4] + "0" if start[-1] != "0" else start
                start_dt = iso_at(day, start)
                add_timer_record(conn, day, todo_id, subjects[subject], block_key, "focus", start_dt, focus_minutes, memo)
                if focus_minutes >= 24:
                    add_timer_record(conn, day, todo_id, subjects[subject], block_key, "break", start_dt + timedelta(minutes=focus_minutes), 5, memo)

            for offset, event_type in enumerate(EVENTS_BY_DAY[day]):
                todo_id, subject, _title = todo_ids[min(offset, len(todo_ids) - 1)]
                conn.execute(
                    """
                    INSERT INTO event_logs(day, event_type, todo_id, subject_id, block_key, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        day,
                        event_type,
                        todo_id,
                        subjects[subject],
                        None,
                        json.dumps({"sample": True}, ensure_ascii=False),
                        (iso_at(day, "18:00") + timedelta(minutes=offset)).isoformat(timespec="seconds"),
                    ),
                )

            conn.execute(
                """
                INSERT INTO brain_dumps(day, content, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at
                """,
                (day, BRAIN_DUMPS[day], f"{day}T22:00:00"),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Seeded sample usage data: {START_DAY}..{END_DAY}")
    print(f"Backup created: {backup}")


if __name__ == "__main__":
    seed()
