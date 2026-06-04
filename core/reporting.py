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


def _minutes(seconds: int) -> int:
    return max(0, round(seconds / 60))


def _status_counts(todos: list) -> dict[str, int]:
    counts = defaultdict(int)
    for todo in todos:
        counts[todo.status] += 1
    return dict(counts)


def _record_totals(records: list[dict]) -> dict[str, int]:
    totals = defaultdict(int)
    for record in records:
        totals[record["event_type"]] += int(record["seconds"] or 0)
    return dict(totals)


def _subject_focus_totals(records: list[dict]) -> dict[str, int]:
    totals = defaultdict(int)
    for record in records:
        if record["event_type"] == "focus":
            totals[record["subject_name"]] += int(record["seconds"] or 0)
    return dict(totals)


def _time_bucket(started_at: str | None) -> str:
    if not started_at:
        return "시간 미상"
    try:
        hour = datetime.fromisoformat(started_at).hour
    except ValueError:
        return "시간 미상"
    if 5 <= hour < 12:
        return "오전"
    if 12 <= hour < 18:
        return "오후"
    if 18 <= hour < 24:
        return "저녁"
    return "새벽"


def _time_bucket_focus_totals(records: list[dict]) -> dict[str, int]:
    totals = defaultdict(int)
    for record in records:
        if record["event_type"] == "focus":
            totals[_time_bucket(record["started_at"])] += int(record["seconds"] or 0)
    return dict(totals)


def _format_minutes_map(values: dict[str, int], empty: str = "기록 없음") -> str:
    if not values:
        return empty
    parts = [
        f"{key} {_minutes(seconds)}분"
        for key, seconds in sorted(values.items(), key=lambda item: item[1], reverse=True)
    ]
    return ", ".join(parts)


def _format_status_counts(counts: dict[str, int]) -> str:
    labels = {"open": "진행 전", "done": "완료", "deferred": "미룸"}
    if not counts:
        return "할 일 없음"
    return ", ".join(f"{labels.get(status, status)} {count}개" for status, count in sorted(counts.items()))


def _event_counts(events: list[dict]) -> dict[str, int]:
    counts = defaultdict(int)
    for event in events:
        counts[event["event_type"]] += 1
    return dict(counts)


def _format_event_counts(counts: dict[str, int]) -> str:
    labels = {
        "todo_add_opened": "할 일 추가 열기",
        "todo_selected": "할 일 선택",
        "todo_edit_opened": "할 일 편집 열기",
        "todo_deleted": "할 일 삭제",
        "block_assigned": "계획 블록 배치",
        "block_erased": "계획 블록 삭제",
        "blocks_cleared": "계획 전체 삭제",
        "delete_mode_toggled": "삭제 모드 전환",
        "timer_prepared": "타이머 준비",
        "timer_started": "타이머 시작/재개",
        "timer_paused": "타이머 일시정지",
        "break_skipped": "휴식 건너뛰기",
        "timer_stopped": "타이머 종료",
        "timer_cancelled": "타이머 취소",
        "todo_completed": "할 일 완료",
        "report_generated": "Markdown 리포트 생성",
        "ai_feedback_clicked": "AI 피드백 클릭",
        "date_changed": "날짜 변경",
    }
    if not counts:
        return "행동 로그 없음"
    return ", ".join(
        f"{labels.get(event_type, event_type)} {count}회"
        for event_type, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    )


def _summarize_blocks(blocks: dict[str, int], todos_by_id: dict[int, object]) -> list[str]:
    if not blocks:
        return ["- 계획 블록 없음"]

    lines = []
    current_todo_id = None
    start_key = None
    previous_key = None
    sorted_keys = sorted(blocks)

    for key in sorted_keys + [None]:
        todo_id = blocks.get(key) if key is not None else None
        if todo_id != current_todo_id:
            if current_todo_id is not None and start_key is not None and previous_key is not None:
                todo = todos_by_id.get(current_todo_id)
                title = todo.title if todo else f"todo_id={current_todo_id}"
                subject = todo.subject_name if todo else "과목 미상"
                lines.append(f"- {start_key}~{previous_key}: {subject} / {title}")
            current_todo_id = todo_id
            start_key = key
        previous_key = key

    return lines


def _burnout_signals(records: list[dict], totals: dict[str, int]) -> list[str]:
    signals = []
    focus_minutes = _minutes(totals.get("focus", 0))
    break_minutes = _minutes(totals.get("break", 0) + totals.get("long_break", 0))
    interruptions = sum(1 for record in records if record["event_type"] in {"paused", "distracted", "deferred"})

    if focus_minutes >= 180 and break_minutes < max(20, focus_minutes // 8):
        signals.append("집중 시간 대비 휴식 시간이 부족할 수 있음")
    if interruptions >= 3:
        signals.append("중단/미룸/산만 기록이 반복됨")
    if focus_minutes == 0:
        signals.append("실제 집중 기록이 없음")
    if not signals:
        signals.append("뚜렷한 번아웃 신호 없음")
    return signals


def build_ai_coaching_prompt(day: str, snapshots: list[dict]) -> str:
    current = next((snapshot for snapshot in snapshots if snapshot["day"] == day), snapshots[0])
    current_todos = current["todos"]
    current_records = current["records"]
    current_blocks = current["blocks"]
    current_notes = current["notes"].strip()

    all_todos = [todo for snapshot in snapshots for todo in snapshot["todos"]]
    all_records = [record for snapshot in snapshots for record in snapshot["records"]]
    all_events = [event for snapshot in snapshots for event in snapshot.get("events", [])]

    current_totals = _record_totals(current_records)
    all_totals = _record_totals(all_records)
    current_subject_totals = _subject_focus_totals(current_records)
    all_subject_totals = _subject_focus_totals(all_records)
    time_bucket_totals = _time_bucket_focus_totals(all_records)
    todos_by_id = {todo.id: todo for todo in current_todos}

    current_planned_minutes = len(current_blocks) * 10
    current_focus_minutes = _minutes(current_totals.get("focus", 0))
    all_focus_minutes = _minutes(all_totals.get("focus", 0))
    all_break_minutes = _minutes(all_totals.get("break", 0) + all_totals.get("long_break", 0))
    completed = sum(1 for todo in all_todos if todo.status == "done")
    deferred = sum(1 for todo in all_todos if todo.status == "deferred")
    open_count = sum(1 for todo in all_todos if todo.status == "open")

    lines = [
        "# 개인화 AI 피드백 요청 프롬프트",
        "",
        "아래 데이터는 내 로컬 플래너에서 Markdown 버튼으로 복사한 사용 기록입니다.",
        "개인정보를 추정하거나 없는 사실을 만들지 말고, 제공된 데이터만 근거로 한국어로 답해주세요.",
        "",
        "## AI에게 요청할 일",
        "- 오늘의 강점 1개, 병목 1개, 바로 할 다음 행동 1개를 제안해주세요.",
        "- 최근 사용 패턴을 기준으로 현재 시간 이후 계획표를 어떻게 조정하면 좋을지 제안해주세요.",
        "- 쉬는 시간 부족, 과도한 연속 공부, 번아웃 가능성을 고려해주세요.",
        "- 계획표를 수정한다면 '현재 시간 이전 기록은 보존'하고, 이후 블록만 바꾸는 방식으로 제안해주세요.",
        "- 답변은 짧고 실행 가능하게 작성해주세요.",
        "",
        f"## 기준 날짜",
        f"- {day}",
        "",
        "## 오늘 요약",
        f"- 계획된 Time Plan: {current_planned_minutes}분 ({len(current_blocks)}개 블록)",
        f"- 실제 집중: {current_focus_minutes}분",
        f"- 휴식/긴 휴식: {_minutes(current_totals.get('break', 0) + current_totals.get('long_break', 0))}분",
        f"- To Do 상태: {_format_status_counts(_status_counts(current_todos))}",
        f"- 과목별 집중: {_format_minutes_map(current_subject_totals)}",
        f"- 번아웃 신호: {', '.join(_burnout_signals(current_records, current_totals))}",
        "",
        "## 오늘 To Do",
    ]

    if current_todos:
        for todo in current_todos:
            lines.append(f"- [{todo.status}] {todo.subject_name}: {todo.title}")
    else:
        lines.append("- 할 일 없음")

    lines.extend(["", "## 오늘 계획표 블록"])
    lines.extend(_summarize_blocks(current_blocks, todos_by_id))

    lines.extend(
        [
            "",
            "## 오늘 Brain Dump",
            current_notes if current_notes else "작성된 Brain Dump 없음",
            "",
            "## 최근 사용 패턴 요약",
            f"- 분석 기간: 최근 {len(snapshots)}일",
            f"- 전체 집중 시간: {all_focus_minutes}분",
            f"- 전체 휴식/긴 휴식 시간: {all_break_minutes}분",
            f"- 전체 To Do: 완료 {completed}개, 미룸 {deferred}개, 진행 전 {open_count}개",
            f"- 과목별 누적 집중: {_format_minutes_map(all_subject_totals)}",
            f"- 시간대별 누적 집중: {_format_minutes_map(time_bucket_totals)}",
            f"- 최근 행동/버튼 요약: {_format_event_counts(_event_counts(all_events))}",
            "",
            "## 날짜별 요약",
        ]
    )

    for snapshot in snapshots:
        totals = _record_totals(snapshot["records"])
        subject_totals = _subject_focus_totals(snapshot["records"])
        event_counts = _event_counts(snapshot.get("events", []))
        lines.append(
            f"- {snapshot['day']}: 계획 {len(snapshot['blocks']) * 10}분, "
            f"집중 {_minutes(totals.get('focus', 0))}분, "
            f"휴식 {_minutes(totals.get('break', 0) + totals.get('long_break', 0))}분, "
            f"To Do {_format_status_counts(_status_counts(snapshot['todos']))}, "
            f"과목 {_format_minutes_map(subject_totals)}, "
            f"행동 {_format_event_counts(event_counts)}"
        )

    lines.extend(
        [
            "",
            "## 출력 형식",
            "1. 오늘의 한 줄 진단",
            "2. 내 패턴에서 보이는 강점",
            "3. 병목/번아웃 위험",
            "4. 현재 시간 이후 계획표 수정안",
            "5. 바로 실행할 다음 행동 1개",
        ]
    )
    return "\n".join(lines)


def save_markdown_report(day: str, markdown: str) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{day}_report.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)
