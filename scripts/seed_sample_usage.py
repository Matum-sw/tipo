import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "planner.sqlite3"
START_DAY = "2026-06-10"
END_DAY = "2026-06-14"

SUBJECTS = {
    "자료구조": "보통",
    "선형대수학": "어려움",
    "시스템 프로그래밍": "어려움",
    "컴퓨터 프로그래밍": "보통",
    "모바일 캡스톤": "보통",
}

SAMPLE_PLANS = {
    "2026-06-10": [
        ("자료구조", "과제", "10:00", 12, "done"),
        ("선형대수학", "온라인강의", "13:00", 12, "done"),
        ("모바일 캡스톤", "발표자료 준비", "16:00", 6, "done"),
    ],
    "2026-06-11": [
        ("시스템 프로그래밍", "과제", "09:00", 8, "done"),
        ("컴퓨터 프로그래밍", "온라인강의", "11:00", 8, "done"),
        ("자료구조", "실습 문제 풀이", "13:00", 8, "done"),
        ("모바일 캡스톤", "기능 명세 정리", "15:00", 8, "open"),
    ],
    "2026-06-12": [
        ("시스템 프로그래밍", "과제", "10:00", 10, "done"),
        ("모바일 캡스톤", "발표자료 준비", "12:00", 10, "done"),
        ("선형대수학", "온라인강의", "14:00", 9, "done"),
    ],
    "2026-06-13": [
        ("컴퓨터 프로그래밍", "과제", "09:00", 8, "done"),
        ("자료구조", "온라인강의", "11:00", 8, "done"),
        ("선형대수학", "연습문제 정리", "13:00", 8, "open"),
        ("모바일 캡스톤", "회의록 정리", "15:00", 7, "done"),
    ],
    "2026-06-14": [
        ("선형대수학", "과제", "10:00", 7, "done"),
        ("시스템 프로그래밍", "실습 정리", "12:00", 7, "done"),
        ("컴퓨터 프로그래밍", "온라인강의", "14:00", 7, "done"),
        ("모바일 캡스톤", "발표자료 준비", "16:00", 7, "open"),
    ],
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def block_key(start: str, offset: int) -> str:
    hour, minute = map(int, start.split(":"))
    total = hour * 60 + minute + offset * 10
    return f"{total // 60:02d}:{total % 60:02d}"


def dt_at(day: str, hhmm: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{hhmm}:00")


def ensure_subjects(conn: sqlite3.Connection) -> dict[str, int]:
    for name, difficulty in SUBJECTS.items():
        conn.execute(
            """
            INSERT INTO subjects(name, difficulty, kind, created_at)
            VALUES (?, ?, 'subject', ?)
            ON CONFLICT(name) DO UPDATE SET difficulty = excluded.difficulty
            """,
            (name, difficulty, now()),
        )
    rows = conn.execute(
        f"SELECT id, name FROM subjects WHERE name IN ({','.join('?' for _ in SUBJECTS)})",
        tuple(SUBJECTS),
    ).fetchall()
    return {row["name"]: row["id"] for row in rows}


def clear_sample_days(conn: sqlite3.Connection) -> None:
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
    conn.execute("DELETE FROM excluded_blocks WHERE day BETWEEN ? AND ?", (START_DAY, END_DAY))


def add_focus_record(
    conn: sqlite3.Connection,
    day: str,
    todo_id: int,
    subject_id: int,
    start: str,
    block_count: int,
) -> None:
    started = dt_at(day, start)
    seconds = block_count * 10 * 60
    ended = started + timedelta(seconds=seconds)
    conn.execute(
        """
        INSERT INTO timer_records(
            day, todo_id, subject_id, block_key, event_type,
            started_at, ended_at, seconds, memo, created_at
        )
        VALUES (?, ?, ?, ?, 'focus', ?, ?, ?, ?, ?)
        """,
        (
            day,
            todo_id,
            subject_id,
            start,
            started.isoformat(timespec="seconds"),
            ended.isoformat(timespec="seconds"),
            seconds,
            "sample-history",
            now(),
        ),
    )


def recalculate_planned_minutes(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id FROM todos WHERE day BETWEEN ? AND ?", (START_DAY, END_DAY)).fetchall()
    for row in rows:
        todo_id = row["id"]
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM time_blocks WHERE todo_id = ?",
            (todo_id,),
        ).fetchone()["count"]
        conn.execute("UPDATE todos SET planned_minutes = ? WHERE id = ?", (count * 10, todo_id))


def seed_sample_usage(db_path: Path = DB_PATH, backup: bool = True) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        raise FileNotFoundError(f"DB file not found: {db_path}. Run the app once first.")

    if backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(db_path, db_path.with_name(f"planner.sample-backup-{stamp}.sqlite3"))

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        subject_ids = ensure_subjects(conn)
        clear_sample_days(conn)

        for day, items in SAMPLE_PLANS.items():
            for subject, title, start, block_count, status in items:
                cursor = conn.execute(
                    """
                    INSERT INTO todos(day, title, subject_id, status, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (day, title, subject_ids[subject], status, f"{day}T08:00:00"),
                )
                todo_id = cursor.lastrowid
                for offset in range(block_count):
                    conn.execute(
                        "INSERT INTO time_blocks(day, block_key, todo_id) VALUES (?, ?, ?)",
                        (day, block_key(start, offset), todo_id),
                    )
                if status == "done":
                    add_focus_record(conn, day, todo_id, subject_ids[subject], start, block_count)

        recalculate_planned_minutes(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed 2026-06-10..2026-06-14 sample planner history.")
    parser.add_argument("--db", type=Path, default=DB_PATH, help="Path to planner.sqlite3")
    parser.add_argument("--no-backup", action="store_true", help="Do not create a backup before seeding")
    args = parser.parse_args()

    seed_sample_usage(args.db, backup=not args.no_backup)
    print("Seeded sample usage history for 2026-06-10..2026-06-14.")
    print("Daily planned block counts: 30, 32, 29, 31, 28. Average: 30.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
