from collections import defaultdict
from datetime import datetime

from core.paths import REPORT_DIR


def seconds_to_minutes(seconds: int) -> int:
    return max(0, round(seconds / 60))


def build_markdown_report(day: str, todos: list, records: list, notes: str = "") -> str:
    study_totals = defaultdict(int)
    life_total = 0
    paused = []

    for record in records:
        if record["event_type"] in {"distracted", "paused", "deferred"}:
            paused.append(record)
            continue
        if record["event_type"] not in {"focus", "completed"}:
            continue
        if record["subject_kind"] == "other":
            life_total += record["seconds"]
        else:
            study_totals[record["subject_name"]] += record["seconds"]

    lines = [
        f"# Daily Time Box Report - {day}",
        "",
        "## Study Time",
    ]

    if study_totals:
        for subject, seconds in sorted(study_totals.items(), key=lambda item: item[1], reverse=True):
            lines.append(f"- {subject}: {seconds_to_minutes(seconds)}분")
    else:
        lines.append("- 공부 기록 없음")

    lines.extend(
        [
            "",
            "## Life Schedule",
            f"- 기타 일정: {seconds_to_minutes(life_total)}분",
            "",
            "## To Do",
        ]
    )
    lines.extend(f"- [{ 'x' if todo.status == 'done' else ' ' }] {todo.title} ({todo.subject_name})" for todo in todos)

    lines.extend(["", "## Paused / Deferred"])
    if paused:
        for record in paused:
            lines.append(f"- {record['todo_title']} · {record['event_type']} · {record['memo'] or '메모 없음'}")
    else:
        lines.append("- 중단/미룸 기록 없음")

    if notes:
        lines.extend(["", "## Brain Dump", notes])

    lines.extend(["", f"_Generated at {datetime.now().isoformat(timespec='seconds')}_"])
    return "\n".join(lines)


def save_markdown_report(day: str, markdown: str) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{day}_report.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)
