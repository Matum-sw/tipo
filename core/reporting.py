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


def _app_context_for_prompt() -> list[str]:
    return [
        "## 프로그램 핵심 구조와 화면 설명",
        "- 이 앱은 PySide6 기반 데일리 타임박싱 플래너입니다.",
        "- 화면은 크게 To Do List, Brain Dump, Time Plan, Timer, Study Stats 영역으로 구성됩니다.",
        "- To Do List: 공부할 일이나 생활 일정을 과목별로 등록하고 선택하는 영역입니다.",
        "- Brain Dump: 걱정, 아이디어, 나중에 정리할 일을 자유롭게 적는 메모 영역입니다.",
        "- Time Plan: 하루 24시간을 10분 단위 블록으로 나눈 계획표입니다.",
        "- Timer: 현재 시간에 해당하는 Time Plan 블록의 할 일을 찾아 뽀모도로 타이머를 실행합니다.",
        "- Study Stats: 타이머로 실제 기록된 집중/휴식 시간을 집계합니다.",
        "",
        "## Time Plan 그리드 규칙",
        "- 블록 키는 `HH:MM` 형식입니다. 예: `10:20`은 10:20~10:30 블록입니다.",
        "- 한 블록은 10분입니다.",
        "- 같은 할 일이 연속된 블록에 배치되면 하나의 작업 구간으로 해석합니다.",
        "- 현재 시간 이전 블록과 실제 타이머 기록이 있는 블록은 보존해야 합니다.",
        "- 계획 수정 제안은 현재 시간 이후 블록에 대해서만 해주세요.",
        "- 빈 시간이 부족하면 무리해서 밀어 넣지 말고 미룸/축소/분할을 제안해주세요.",
        "",
        "## 버튼과 행동 의미",
        "- `추가`: 새 To Do를 만듭니다.",
        "- To Do 클릭: 해당 To Do를 선택합니다.",
        "- Time Plan 블록 클릭/드래그: 선택한 To Do를 해당 10분 블록들에 배치합니다.",
        "- `추가 모드`: 블록을 채우는 기본 모드입니다.",
        "- `삭제 모드`: 타이머 기록이 없는 계획 블록을 지우는 모드입니다.",
        "- `전체 삭제`: 오늘 계획 중 실제 타이머 기록이 없는 블록만 삭제합니다.",
        "- Timer `실행`: 현재 시간에 걸친 Time Plan 할 일을 찾아 집중 타이머를 시작하거나 재개합니다.",
        "- Timer `일시정지`: 집중 중인 타이머를 멈춥니다.",
        "- Timer `건너뛰기`: 휴식/긴 휴식 중 남은 휴식을 건너뜁니다.",
        "- Timer `종료`: 현재 세션을 저장하고 타이머를 종료합니다.",
        "- Timer `완료`: 현재 또는 선택된 To Do를 완료 처리합니다.",
        "- `Markdown`: 아래 데이터를 바탕으로 GPT에 붙여넣을 개인화 피드백 프롬프트를 복사합니다.",
        "- `AI 피드백`: 현재 코드에서는 실제 API 호출 없이 안내/placeholder 용도로 쓰입니다.",
        "",
        "## 타이머와 휴식 규칙",
        "- 기본 집중 시간은 설정값 기준이며 보통 25분입니다.",
        "- 기본 휴식 시간은 설정값 기준이며 보통 5분입니다.",
        "- 여러 스프린트 후 긴 휴식이 들어갈 수 있습니다.",
        "- 휴식을 자주 건너뛰거나 긴 연속 집중이 반복되면 번아웃 위험 신호로 해석해주세요.",
        "- 실제 집중 기록은 계획표보다 중요합니다. 계획은 많지만 실행이 적으면 계획 과부하로 판단해주세요.",
        "",
        "## GPT가 제안해야 하는 계획표 수정 방식",
        "- 추상적인 조언만 하지 말고, 가능한 경우 구체적인 블록 수정안을 제안해주세요.",
        "- 수정안은 `HH:MM~HH:MM | 과목 | 할 일 | 이유` 형식을 사용해주세요.",
        "- 답변은 긴 문단보다 표와 짧은 bullet 위주로 작성해주세요.",
        "- 계획표 수정안은 반드시 Markdown 표로 보여주세요.",
        "- 표는 시간순으로 정렬하고, 한눈에 볼 수 있게 시간/과목/할 일/조정 유형/이유를 분리해주세요.",
        "- 휴식도 계획에 포함해주세요. 예: `11:20~11:30 | 휴식 | 짧은 휴식 | 집중 40분 뒤 회복`.",
        "- 어려운 과목은 너무 긴 연속 블록으로 제안하지 말고 분할 배치해주세요.",
        "- Brain Dump에 불안/잡생각이 많으면 짧은 정리 시간이나 쉬운 작업을 먼저 제안해주세요.",
        "- 사용자의 최근 성공 시간대와 과목별 실제 집중 패턴을 우선 반영해주세요.",
    ]


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


def _format_current_context(context: dict | None) -> list[str]:
    if not context:
        return [
            "## 현재 상황과 재분배 기준",
            "- 현재 실행 상황 정보 없음: 아래 계획표/기록만 근거로 현재 시간 이후 재분배를 제안해주세요.",
        ]

    lines = [
        "## 현재 상황과 재분배 기준",
        f"- 현재 시각: {context.get('now', '알 수 없음')}",
        f"- 현재 10분 블록: {context.get('current_block_key', '알 수 없음')}",
        f"- 현재 타이머 상태: {context.get('timer_mode', '실행 중 아님')}",
        f"- 현재/해당 블록 작업: {context.get('current_task', '현재 시간에 배치된 작업 없음')}",
        f"- 현재 작업 원래 계획 구간: {context.get('current_task_planned_ranges', '계획 구간 없음')}",
        f"- 현재 작업 원래 계획 시간: {context.get('current_task_planned_minutes', 0)}분",
        f"- 현재 작업 실제 집중 시간: {context.get('current_task_actual_focus_minutes', 0)}분",
        f"- 현재 작업 계획 대비 초과/부족: {context.get('current_task_delta_minutes', 0)}분",
        f"- 현재 이후 수정 가능 범위: {context.get('editable_range', '현재 시간 이후, 타이머 기록 없는 블록')}",
        f"- 현재 이후 남은 계획 블록: {context.get('remaining_planned_minutes', 0)}분",
        f"- 현재 이후 빈 블록: {context.get('remaining_empty_minutes', 0)}분",
        f"- 오늘 남은 미완료 To Do: {context.get('remaining_open_todos', '미완료 To Do 없음')}",
    ]

    protected = context.get("protected_blocks", "")
    if protected:
        lines.append(f"- 수정 금지 블록: {protected}")

    lines.extend(
        [
            "",
            "### 재분배 판단 방법",
            "- 현재 작업이 계획보다 초과 중이면, 뒤 작업을 무조건 밀어붙이지 말고 다음 세 가지를 비교해주세요.",
            "- 1) 현재 작업을 짧게 마무리하고 뒤 작업 유지",
            "- 2) 뒤 작업 시간을 줄이고 핵심만 남김",
            "- 3) 뒤 작업 일부를 미룸 처리하고 휴식/회복 시간을 확보",
            "- 오늘 안에 끝내야 하는 일이 많으면, 모든 작업을 균등하게 줄이지 말고 중요도와 최근 성공 패턴을 기준으로 줄여주세요.",
            "- `현재 이후 빈 블록`과 `현재 이후 남은 계획 블록`을 합쳐서 현실적인 재배치안을 만드세요.",
            "- 계획 대비 초과 시간이 크면 최소 10분 휴식을 먼저 넣는 선택지도 검토하세요.",
        ]
    )
    return lines


def build_ai_coaching_prompt(day: str, snapshots: list[dict], current_context: dict | None = None) -> str:
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
        *_app_context_for_prompt(),
        "",
        *_format_current_context(current_context),
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
            "2. 핵심 요약 표: 강점/병목/번아웃 위험/우선순위",
            "3. 현재 시간 이후 계획표 수정안: Markdown 표로 작성",
            "   - 표 컬럼: `시간`, `과목`, `할 일`, `조정 유형`, `이유`",
            "   - 조정 유형 예시: 유지, 축소, 이동, 분할, 휴식 추가, 미룸",
            "4. 변경 전후 비교 표: 기존 계획과 추천 계획의 차이",
            "5. 바로 실행할 다음 행동 1개",
        ]
    )
    return "\n".join(lines)


def save_markdown_report(day: str, markdown: str) -> str:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{day}_report.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)
