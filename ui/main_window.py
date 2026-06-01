from collections import defaultdict
from datetime import datetime
import time
from uuid import uuid4

from PySide6.QtCore import QDate, QTimer, Qt, QUrl, QSize
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.openai_feedback import AIFeedbackService
from core.paths import ROOT_DIR
from core.reporting import build_markdown_report, save_markdown_report
from ui.date_dialog import DateDialog
from ui.subject_dialog import SubjectDialog
from ui.widgets import Card, Pill, TimeBlockButton, TimeGridWidget, TimelineHeader


HOURS = list(range(4, 25))
MINUTES = (0, 10, 20, 30, 40, 50)
POMODORO_FOCUS_SECONDS = 25 * 60
POMODORO_BREAK_SECONDS = 5 * 60
ALARM_FILE = ROOT_DIR / "assets" / "alarm.wav"


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.ai = AIFeedbackService()
        self.day = self.store.today()
        self.selected_todo_id = None
        self.selected_subject_id = None
        self.selected_block_key = None
        self.todo_lookup = {}
        self.block_buttons = {}
        self.drag_todo_id = None
        self.drag_visited_blocks = set()
        self.drag_is_painting = False
        self.drag_last_block_key = None
        self.running = None
        self.pomodoro_history = []
        self.tick = QTimer(self)
        self.tick.timeout.connect(self.update_timer)
        self.alarm = QSoundEffect(self)
        self.alarm.setVolume(0.8)
        if ALARM_FILE.exists():
            self.alarm.setSource(QUrl.fromLocalFile(str(ALARM_FILE)))

        self.setWindowTitle("Daily Time Box Planner")
        self.resize(1360, 900)
        self.setMinimumSize(1180, 760)

        if not self.store.has_real_subjects():
            SubjectDialog(self.store, self).exec()

        self.build()
        self.refresh_all()

    def build(self) -> None:
        page = QWidget()
        page.setObjectName("AppRoot")
        self.setCentralWidget(page)

        root = QVBoxLayout(page)
        root.setContentsMargins(34, 24, 34, 30)
        root.setSpacing(18)

        self.date_button = QPushButton()
        self.date_button.setObjectName("DateButton")
        self.date_button.clicked.connect(self.open_date_dialog)
        self.update_date_button()

        board = QHBoxLayout()
        board.setSpacing(22)
        root.addLayout(board, 1)

        left = QVBoxLayout()
        left.setSpacing(18)
        board.addLayout(left, 3)

        middle = QVBoxLayout()
        middle.setSpacing(18)
        board.addLayout(middle, 5)

        right = QVBoxLayout()
        right.setSpacing(18)
        board.addLayout(right, 2)

        self.build_todo_card(left)
        self.build_brain_card(left)
        self.build_plan_card(middle)
        self.build_top_controls(right)
        self.build_timer_card(right)
        self.build_stats_card(right)

    def build_top_controls(self, parent) -> None:
        controls = QFrame()
        controls.setObjectName("TopControls")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(10)

        subject_button = QPushButton("과목 관리")
        subject_button.clicked.connect(self.open_subjects)
        subject_button.setObjectName("GhostButton")

        controls_layout.addWidget(self.date_button, 1)
        controls_layout.addWidget(subject_button, 1)
        parent.addWidget(controls)

    def build_todo_card(self, parent) -> None:
        card = Card("To Do List")
        parent.addWidget(card, 3)

        self.todo_input = QLineEdit()
        self.todo_input.setPlaceholderText("오늘 할 일 입력")
        self.todo_input.returnPressed.connect(self.add_todo)
        card.layout.addWidget(self.todo_input)

        actions = QHBoxLayout()
        self.subject_button = QPushButton("과목")
        self.subject_button.setObjectName("SubjectButton")
        self.subject_button.setToolTip("과목 선택")
        self.subject_button.setFixedWidth(104)
        self.subject_menu = QMenu(self)
        self.subject_button.setMenu(self.subject_menu)
        self.add_button = QPushButton("추가")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.setFixedWidth(92)
        self.add_button.clicked.connect(self.add_todo)
        self.delete_todo_button = QPushButton("삭제")
        self.delete_todo_button.setObjectName("DangerButton")
        self.delete_todo_button.setFixedWidth(92)
        self.delete_todo_button.clicked.connect(self.delete_selected_todo)
        actions.addWidget(self.subject_button)
        actions.addWidget(self.add_button)
        actions.addWidget(self.delete_todo_button)
        actions.addStretch(1)
        card.layout.addLayout(actions)

        self.todo_list = QListWidget()
        self.todo_list.setWordWrap(True)
        self.todo_list.itemClicked.connect(self.select_todo)
        card.layout.addWidget(self.todo_list, 1)

    def build_brain_card(self, parent) -> None:
        card = Card("Brain Dump", "떠오르는 일을 빠르게 비워두는 공간.")
        parent.addWidget(card, 2)
        self.brain_dump = QTextEdit()
        self.brain_dump.setPlaceholderText("걱정, 아이디어, 나중에 정리할 일...")
        self.brain_dump.textChanged.connect(self.save_brain_dump)
        card.layout.addWidget(self.brain_dump, 1)

    def build_plan_card(self, parent) -> None:
        card = Card("Time Plan", "To Do를 선택하고 시간 블록을 클릭하거나 드래그하면 배치됩니다.")
        parent.addWidget(card, 1)

        plan_actions = QHBoxLayout()
        self.selected_block_label = QLabel("선택된 블록 없음")
        self.selected_block_label.setObjectName("MutedText")
        self.delete_block_button = QPushButton("선택 블록 삭제")
        self.delete_block_button.setObjectName("SoftButton")
        self.delete_block_button.clicked.connect(self.delete_selected_block)
        plan_actions.addWidget(self.selected_block_label, 1)
        plan_actions.addWidget(self.delete_block_button)
        card.layout.addLayout(plan_actions)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("PlanScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.time_grid_widget = TimeGridWidget(lambda: self.day)
        self.time_grid_widget.setObjectName("TimeGrid")
        self.time_grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.time_grid = QGridLayout(self.time_grid_widget)
        self.time_grid.setHorizontalSpacing(0)
        self.time_grid.setVerticalSpacing(8)
        self.time_grid.setContentsMargins(4, 4, 4, 4)

        self.time_grid.addWidget(QLabel(""), 0, 0)
        self.time_grid.addWidget(TimelineHeader(), 0, 1, 1, len(MINUTES))

        for row, hour in enumerate(HOURS, start=1):
            hour_label = QLabel(str(hour))
            hour_label.setObjectName("HourLabel")
            hour_label.setAlignment(Qt.AlignCenter)
            self.time_grid.addWidget(hour_label, row, 0)
            for column, minute in enumerate(MINUTES, start=1):
                key = f"{hour:02d}:{minute:02d}"
                button = TimeBlockButton(key)
                if column == 1:
                    button.setProperty("segment", "first")
                elif column == len(MINUTES):
                    button.setProperty("segment", "last")
                else:
                    button.setProperty("segment", "middle")
                button.pressed_block.connect(self.on_block_pressed)
                button.entered_block.connect(self.on_block_entered)
                button.moved_block.connect(self.on_block_moved)
                button.released_block.connect(self.on_block_released)
                self.block_buttons[key] = button
                self.time_grid.addWidget(button, row, column)

        self.time_grid.setColumnStretch(0, 0)
        self.time_grid.setColumnMinimumWidth(0, 26)
        for column in range(1, len(MINUTES) + 1):
            self.time_grid.setColumnStretch(column, 1)
        self.time_grid.setRowStretch(0, 0)
        for row in range(1, len(HOURS) + 1):
            self.time_grid.setRowStretch(row, 1)

        scroll.setWidget(self.time_grid_widget)
        self.time_grid_widget.set_block_buttons(self.block_buttons)
        card.layout.addWidget(scroll, 1)

    def build_timer_card(self, parent) -> None:
        card = Card("Timer")
        parent.addWidget(card)
        self.pomodoro_status = QLabel("Pomodoro 1세트 · 집중 25:00")
        self.pomodoro_status.setObjectName("PomodoroStatus")
        self.pomodoro_status.setWordWrap(True)
        self.timer_value = QLabel("00:00:00")
        self.timer_value.setObjectName("TimerValue")
        self.timer_value.setAlignment(Qt.AlignCenter)
        self.timer_value.setMinimumHeight(76)
        self.pomodoro_visual = QLabel("세트 기록 없음")
        self.pomodoro_visual.setObjectName("PomodoroVisual")
        self.pomodoro_visual.setWordWrap(True)
        card.layout.addWidget(self.pomodoro_status)
        card.layout.addWidget(self.timer_value)
        card.layout.addWidget(self.pomodoro_visual)

        actions = QHBoxLayout()
        self.cancel_button = QPushButton("취소")
        self.cancel_button.setObjectName("DangerButton")
        self.cancel_button.clicked.connect(self.cancel_timer_session)
        self.pause_button = QPushButton("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.pause_button.clicked.connect(self.toggle_timer)
        self.complete_button = QPushButton("완료")
        self.complete_button.setObjectName("SoftButton")
        self.complete_button.clicked.connect(self.complete_timer_session)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.complete_button)
        card.layout.addLayout(actions)

    def build_stats_card(self, parent) -> None:
        card = Card("Study Stats")
        parent.addWidget(card, 1)

        stats_scroll = QScrollArea()
        stats_scroll.setWidgetResizable(True)
        stats_scroll.setObjectName("StatsScroll")
        stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        stats_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        stats_widget = QWidget()
        stats_widget.setObjectName("StatsList")
        self.stats_container = QVBoxLayout()
        self.stats_container.setContentsMargins(0, 0, 0, 0)
        self.stats_container.setSpacing(10)
        stats_widget.setLayout(self.stats_container)
        stats_scroll.setWidget(stats_widget)
        card.layout.addWidget(stats_scroll, 1)

        report_actions = QHBoxLayout()
        report_button = QPushButton("Markdown 리포트")
        report_button.setObjectName("PrimaryButton")
        report_button.clicked.connect(self.generate_report)
        ai_button = QPushButton("AI 피드백")
        ai_button.setObjectName("GhostButton")
        ai_button.clicked.connect(self.show_ai_feedback)
        report_actions.addWidget(report_button)
        report_actions.addWidget(ai_button)
        card.layout.addLayout(report_actions)

    def add_todo(self) -> None:
        title = self.todo_input.text().strip()
        if title:
            self.store.add_todo(self.day, title, self.selected_subject_id)
            self.todo_input.clear()
            self.refresh_todos()

    def select_todo(self, item: QListWidgetItem) -> None:
        self.selected_todo_id = item.data(Qt.UserRole)
        self.refresh_todos()

    def delete_selected_todo(self) -> None:
        if not self.selected_todo_id:
            QMessageBox.information(self, "To Do 선택", "삭제할 To Do를 먼저 선택하세요.")
            return
        if self.running and self.running["todo_id"] == self.selected_todo_id:
            self.cancel_timer_session()
        self.store.delete_todo(self.selected_todo_id)
        self.selected_todo_id = None
        self.selected_block_key = None
        self.refresh_all()

    def on_block_pressed(self, block_key: str) -> None:
        self.set_selected_block(block_key)
        if self.selected_todo_id:
            self.drag_todo_id = self.selected_todo_id
            self.drag_visited_blocks = set()
            self.drag_is_painting = True
            self.paint_todo_to_block(block_key)
            return

        todo_id = self.store.blocks_for_day(self.day).get(block_key)
        if todo_id:
            self.selected_todo_id = todo_id
            self.refresh_todos()
            return
        QMessageBox.information(self, "To Do 선택", "먼저 To Do 카드를 선택한 뒤 시간 블록을 클릭하세요.")

    def on_block_entered(self, block_key: str) -> None:
        if self.drag_is_painting and self.drag_todo_id:
            self.paint_todo_to_block(block_key)

    def on_block_moved(self, global_pos) -> None:
        if not self.drag_is_painting or not self.drag_todo_id:
            return
        widget = QApplication.widgetAt(global_pos)
        while widget and not isinstance(widget, TimeBlockButton):
            widget = widget.parentWidget()
        if isinstance(widget, TimeBlockButton):
            self.paint_todo_to_block(widget.block_key)

    def on_block_released(self, block_key: str) -> None:
        if not self.drag_is_painting:
            return

        visited_count = len(self.drag_visited_blocks)
        todo_id = self.drag_todo_id
        last_block_key = self.drag_last_block_key or block_key
        self.drag_todo_id = None
        self.drag_is_painting = False
        self.drag_last_block_key = None
        self.drag_visited_blocks = set()
        self.refresh_blocks()

        if visited_count == 1 and todo_id:
            self.selected_todo_id = todo_id
            self.set_selected_block(last_block_key)
            self.refresh_todos()

    def paint_todo_to_block(self, block_key: str) -> None:
        if self.drag_todo_id and block_key not in self.drag_visited_blocks:
            self.store.assign_block(self.day, block_key, self.drag_todo_id)
            self.set_selected_block(block_key)
            self.drag_visited_blocks.add(block_key)
            self.drag_last_block_key = block_key
            self.refresh_single_block(block_key, self.drag_todo_id)

    def delete_selected_block(self) -> None:
        if not self.selected_block_key:
            QMessageBox.information(self, "블록 선택", "삭제할 Time Plan 블록을 먼저 선택하세요.")
            return
        self.store.delete_block(self.day, self.selected_block_key)
        if self.running and self.running["block_key"] == self.selected_block_key:
            self.cancel_timer_session()
        self.selected_block_key = None
        self.update_selected_block_label()
        self.refresh_blocks()

    def set_selected_block(self, block_key: str | None) -> None:
        previous = self.selected_block_key
        self.selected_block_key = block_key
        for key in {previous, block_key}:
            if key and key in self.block_buttons:
                button = self.block_buttons[key]
                button.setProperty("selected", key == block_key)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
        self.update_selected_block_label()

    def update_selected_block_label(self) -> None:
        if hasattr(self, "selected_block_label"):
            text = f"선택된 블록 {self.selected_block_key}" if self.selected_block_key else "선택된 블록 없음"
            self.selected_block_label.setText(text)

    def prepare_timer(self, todo_id: int, block_key: str | None = None) -> None:
        if self.running and self.running["mode"] in {"focus", "break"}:
            self.finish_current_timer_segment()
        todo = self.todo_lookup[todo_id]
        self.running = {
            "session_id": f"timer-session:{uuid4().hex}",
            "block_key": block_key,
            "todo_id": todo_id,
            "subject_id": todo.subject_id,
            "prepared_at": time.time(),
            "mode": "idle",
            "segment_started_at": None,
            "segments": [],
            "title": todo.title,
            "subject": todo.subject_name,
            "set_number": 1,
            "focus_alert_shown": False,
            "break_alert_shown": False,
        }
        self.pause_button.setText("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.repolish(self.pause_button)
        self.update_timer()

    def toggle_timer(self) -> None:
        if not self.running:
            block_key, todo_id = self.current_running_task()
            if not todo_id:
                QMessageBox.information(self, "현재 테스크 없음", "현재 시간에 걸쳐 있는 Time Plan 테스크가 없습니다.")
                return
            self.selected_todo_id = todo_id
            self.set_selected_block(block_key)
            self.refresh_todos()
            self.prepare_timer(todo_id, block_key)

        if self.running["mode"] in {"focus", "break"}:
            self.finish_current_timer_segment()
            self.running["mode"] = "paused"
            self.tick.stop()
            self.pause_button.setText("실행")
            self.pause_button.setObjectName("PrimaryButton")
            self.repolish(self.pause_button)
            self.update_timer()
            return

        self.start_timer_segment(self.next_pomodoro_mode())

    def current_running_task(self) -> tuple[str | None, int | None]:
        now = datetime.now()
        if now.hour not in HOURS:
            return None, None
        block_key = f"{now.hour:02d}:{(now.minute // 10) * 10:02d}"
        return block_key, self.store.blocks_for_day(self.day).get(block_key)

    def start_timer_segment(self, mode: str) -> None:
        if not self.running:
            return
        self.running["mode"] = mode
        self.running["segment_started_at"] = time.time()
        self.tick.start(1000)
        self.pause_button.setText("중단" if mode == "focus" else "휴식 중단")
        self.pause_button.setObjectName("DangerButton")
        self.repolish(self.pause_button)
        self.update_timer()

    def finish_current_timer_segment(self) -> None:
        if not self.running or self.running["mode"] not in {"focus", "break"}:
            return
        ended = time.time()
        started = self.running["segment_started_at"]
        mode = self.running["mode"]
        seconds = max(1, int(ended - started))
        self.running["segments"].append({"mode": mode, "start": started, "end": ended})
        self.store.add_timer_record(
            self.day,
            self.running["todo_id"],
            self.running["subject_id"],
            self.running["block_key"],
            mode,
            seconds,
            datetime.fromtimestamp(started).isoformat(timespec="seconds"),
            datetime.fromtimestamp(ended).isoformat(timespec="seconds"),
            self.running["session_id"],
        )
        self.running["segment_started_at"] = ended
        self.refresh_stats()
        self.refresh_timer_visual()

    def update_timer(self) -> None:
        if not self.running:
            self.timer_value.setText("00:00:00")
            self.pomodoro_status.setText("Pomodoro 1세트 · 집중 25:00")
            self.refresh_pomodoro_visual()
            self.refresh_timer_visual()
            return
        self.advance_pomodoro_if_needed()
        remaining = self.timer_remaining_seconds()
        hours, remainder = divmod(remaining, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.timer_value.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        self.pomodoro_status.setText(self.pomodoro_status_text())
        self.refresh_pomodoro_visual()
        self.refresh_timer_visual()

    def segment_elapsed_seconds(self, mode: str) -> int:
        if not self.running:
            return 0
        elapsed = sum(
            max(1, int(segment["end"] - segment["start"]))
            for segment in self.running["segments"]
            if segment["mode"] == mode
        )
        if self.running["mode"] == mode:
            elapsed += max(0, int(time.time() - self.running["segment_started_at"]))
        return elapsed

    def next_pomodoro_mode(self) -> str:
        if self.segment_elapsed_seconds("focus") < POMODORO_FOCUS_SECONDS:
            return "focus"
        if self.segment_elapsed_seconds("break") < POMODORO_BREAK_SECONDS:
            return "break"
        self.record_completed_pomodoro_set()
        return "focus"

    def timer_remaining_seconds(self) -> int:
        if not self.running:
            return 0
        if self.running["mode"] == "break":
            return max(0, POMODORO_BREAK_SECONDS - self.segment_elapsed_seconds("break"))
        return max(0, POMODORO_FOCUS_SECONDS - self.segment_elapsed_seconds("focus"))

    def advance_pomodoro_if_needed(self) -> None:
        if not self.running:
            return
        if self.running["mode"] == "focus" and self.segment_elapsed_seconds("focus") >= POMODORO_FOCUS_SECONDS:
            if self.running["focus_alert_shown"]:
                return
            self.running["focus_alert_shown"] = True
            self.play_alarm()
            QMessageBox.information(self, "집중 시간 종료", "25분 집중 시간이 끝났습니다. 확인을 누르면 5분 휴식이 시작됩니다.")
            self.finish_current_timer_segment()
            self.start_timer_segment("break")
        elif self.running["mode"] == "break" and self.segment_elapsed_seconds("break") >= POMODORO_BREAK_SECONDS:
            if self.running["break_alert_shown"]:
                return
            self.running["break_alert_shown"] = True
            self.play_alarm()
            QMessageBox.information(self, "휴식 시간 종료", "5분 휴식 시간이 끝났습니다.")
            self.finish_current_timer_segment()
            self.record_completed_pomodoro_set()
            self.running["mode"] = "idle"
            self.tick.stop()
            self.pause_button.setText("실행")
            self.pause_button.setObjectName("PrimaryButton")
            self.repolish(self.pause_button)

    def play_alarm(self) -> None:
        if ALARM_FILE.exists() and not self.alarm.source().isEmpty():
            self.alarm.play()

    def pomodoro_status_text(self) -> str:
        if not self.running:
            return "Pomodoro 1세트 · 집중 25:00"
        set_number = self.running["set_number"]
        if self.running["mode"] == "break":
            return f"Pomodoro {set_number}세트 · 휴식 05:00"
        if self.running["mode"] == "paused":
            return f"Pomodoro {set_number}세트 · 일시정지"
        if self.segment_elapsed_seconds("focus") >= POMODORO_FOCUS_SECONDS:
            return f"Pomodoro {set_number}세트 · 휴식 준비"
        return f"Pomodoro {set_number}세트 · 집중 25:00"

    def record_completed_pomodoro_set(self) -> None:
        if not self.running:
            return
        focus_seconds = self.segment_elapsed_seconds("focus")
        break_seconds = self.segment_elapsed_seconds("break")
        if focus_seconds == 0 and break_seconds == 0:
            return
        self.pomodoro_history.append(
            {
                "title": self.running["title"],
                "focus_seconds": focus_seconds,
                "break_seconds": break_seconds,
                "completed": focus_seconds >= POMODORO_FOCUS_SECONDS and break_seconds >= POMODORO_BREAK_SECONDS,
            }
        )
        self.running["segments"] = []
        self.running["set_number"] += 1
        self.running["focus_alert_shown"] = False
        self.running["break_alert_shown"] = False

    def refresh_pomodoro_visual(self) -> None:
        lines = []
        if self.running:
            focus_minutes = self.segment_elapsed_seconds("focus") // 60
            break_minutes = self.segment_elapsed_seconds("break") // 60
            lines.append(f"현재 세트: 집중 {focus_minutes}/25분 · 휴식 {break_minutes}/5분")
        for index, record in enumerate(self.pomodoro_history[-3:], start=max(1, len(self.pomodoro_history) - 2)):
            mark = "완료" if record["completed"] else "진행 기록"
            lines.append(f"{index}세트 {mark}: 집중 {record['focus_seconds'] // 60}분 · 휴식 {record['break_seconds'] // 60}분")
        self.pomodoro_visual.setText("\n".join(lines) if lines else "세트 기록 없음")

    def active_timer_segments(self) -> list[dict]:
        if not self.running:
            return []
        segments = list(self.running["segments"])
        if self.running["mode"] in {"focus", "break"}:
            segments.append({"mode": self.running["mode"], "start": self.running["segment_started_at"], "end": time.time()})
        return segments

    def refresh_timer_visual(self) -> None:
        if hasattr(self, "time_grid_widget"):
            self.time_grid_widget.set_timer_segments(self.active_timer_segments())

    def cancel_timer_session(self) -> None:
        if not self.running:
            return
        self.tick.stop()
        self.store.delete_timer_records_by_memo(self.running["session_id"])
        self.running = None
        self.pause_button.setText("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.repolish(self.pause_button)
        self.update_timer()
        self.refresh_stats()

    def complete_timer_session(self) -> None:
        if not self.running:
            if self.selected_todo_id:
                self.store.set_todo_status(self.selected_todo_id, "done")
                self.refresh_all()
            return
        if self.running["mode"] in {"focus", "break"}:
            self.finish_current_timer_segment()
        self.tick.stop()
        self.store.set_todo_status(self.running["todo_id"], "done")
        self.record_completed_pomodoro_set()
        self.running = None
        self.pause_button.setText("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.repolish(self.pause_button)
        self.update_timer()
        self.refresh_all()

    def repolish(self, widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def save_brain_dump(self) -> None:
        if hasattr(self, "brain_dump"):
            self.store.save_brain_dump(self.day, self.brain_dump.toPlainText())

    def change_date(self, qdate: QDate) -> None:
        if self.running:
            self.cancel_timer_session()
        self.day = qdate.toString("yyyy-MM-dd")
        self.selected_todo_id = None
        self.pomodoro_history = []
        self.set_selected_block(None)
        self.update_date_button()
        self.refresh_all()

    def open_date_dialog(self) -> None:
        dialog = DateDialog(QDate.fromString(self.day, "yyyy-MM-dd"), self)
        if dialog.exec() == DateDialog.Accepted:
            self.change_date(dialog.selected_date())

    def update_date_button(self) -> None:
        if hasattr(self, "date_button"):
            self.date_button.setText(QDate.fromString(self.day, "yyyy-MM-dd").toString("yyyy-MM-dd"))

    def open_subjects(self) -> None:
        SubjectDialog(self.store, self).exec()
        self.refresh_subjects()

    def refresh_all(self) -> None:
        self.refresh_subjects()
        self.refresh_todos()
        self.refresh_brain_dump()
        self.refresh_blocks()
        self.refresh_stats()

    def refresh_subjects(self) -> None:
        subjects = self.store.subjects(include_other=True)
        if not subjects:
            return
        if self.selected_subject_id is None or not any(subject.id == self.selected_subject_id for subject in subjects):
            self.selected_subject_id = subjects[0].id

        self.subject_menu.clear()
        selected_subject = subjects[0]
        for subject in subjects:
            if subject.id == self.selected_subject_id:
                selected_subject = subject
            action = self.subject_menu.addAction(subject.name)
            action.setCheckable(True)
            action.setChecked(subject.id == self.selected_subject_id)
            action.triggered.connect(lambda _checked=False, subject_id=subject.id: self.select_subject(subject_id))
        self.subject_button.setText("과목")
        self.subject_button.setToolTip(f"선택된 과목: {selected_subject.name}")

    def select_subject(self, subject_id: int) -> None:
        self.selected_subject_id = subject_id
        self.refresh_subjects()

    def refresh_todos(self) -> None:
        self.todo_list.clear()
        self.todo_lookup = {todo.id: todo for todo in self.store.todos_for_day(self.day)}
        for todo in self.todo_lookup.values():
            item = QListWidgetItem()
            item.setData(Qt.UserRole, todo.id)
            item.setSizeHint(QSize(0, self.todo_item_height(todo)))
            item.setSelected(todo.id == self.selected_todo_id)
            self.todo_list.addItem(item)
            self.todo_list.setItemWidget(item, self.create_todo_item_widget(todo))

    def todo_item_height(self, todo) -> int:
        title_lines = max(1, (len(todo.title) + 20) // 21)
        meta_lines = max(1, (len(todo.subject_name) + len(todo.status) + 16) // 30)
        return min(150, 52 + title_lines * 22 + meta_lines * 18)

    def create_todo_item_widget(self, todo) -> QWidget:
        frame = QFrame()
        frame.setObjectName("TodoItemWidget")
        frame.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title = QLabel(todo.title)
        title.setObjectName("TodoItemTitle")
        title.setWordWrap(True)
        title.setMinimumHeight(24)
        title.setTextInteractionFlags(Qt.NoTextInteraction)
        title_row.addWidget(title, 1)
        if todo.status == "done":
            check = QLabel("✓")
            check.setObjectName("TodoDoneCheck")
            check.setAlignment(Qt.AlignCenter)
            check.setFixedWidth(24)
            title_row.addWidget(check)

        meta = QLabel(f"{todo.subject_name} · {self.status_label(todo.status)}")
        meta.setObjectName("TodoItemMeta")
        meta.setWordWrap(True)
        meta.setMinimumHeight(22)

        layout.addLayout(title_row)
        layout.addWidget(meta)
        return frame

    def refresh_brain_dump(self) -> None:
        content = self.store.brain_dump(self.day)
        if self.brain_dump.toPlainText() != content:
            self.brain_dump.blockSignals(True)
            self.brain_dump.setPlainText(content)
            self.brain_dump.blockSignals(False)

    def refresh_blocks(self) -> None:
        blocks = self.store.blocks_for_day(self.day)
        for key, button in self.block_buttons.items():
            todo = self.todo_lookup.get(blocks.get(key))
            if not todo:
                button.set_task_text("")
                button.setProperty("filled", False)
                button.setProperty("life", False)
            else:
                button.set_task_text(f"{todo.subject_name}\n{todo.title}")
                button.setProperty("filled", True)
                button.setProperty("life", todo.subject_kind == "other")
            button.setProperty("selected", key == self.selected_block_key)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def refresh_single_block(self, block_key: str, todo_id: int) -> None:
        button = self.block_buttons.get(block_key)
        todo = self.todo_lookup.get(todo_id)
        if not button or not todo:
            return
        button.set_task_text(f"{todo.subject_name}\n{todo.title}")
        button.setProperty("filled", True)
        button.setProperty("life", todo.subject_kind == "other")
        button.setProperty("selected", block_key == self.selected_block_key)
        button.style().unpolish(button)
        button.style().polish(button)

    def refresh_stats(self) -> None:
        self.clear_layout(self.stats_container)
        records = self.store.timer_records_for_day(self.day)
        totals = defaultdict(int)
        life_total = 0
        paused_count = 0
        for record in records:
            if record["event_type"] in {"distracted", "paused", "deferred"}:
                paused_count += 1
                continue
            if record["event_type"] not in {"focus", "completed"}:
                continue
            if record["subject_kind"] == "other":
                life_total += record["seconds"]
            else:
                totals[record["subject_name"]] += record["seconds"]

        if not totals:
            empty = QLabel("오늘 저장된 공부 시간이 아직 없습니다.")
            empty.setObjectName("MutedText")
            empty.setWordWrap(True)
            self.stats_container.addWidget(empty)
        else:
            for subject, seconds in sorted(totals.items(), key=lambda item: item[1], reverse=True):
                self.stats_container.addWidget(Pill(f"{subject} · {round(seconds / 60)}분", "blue"))

        self.stats_container.addWidget(Pill(f"생활 일정 {round(life_total / 60)}분", "green"))
        self.stats_container.addWidget(Pill(f"중단/미룸 {paused_count}회", "orange"))

    def generate_report(self) -> str:
        markdown = build_markdown_report(
            self.day,
            self.store.todos_for_day(self.day),
            self.store.timer_records_for_day(self.day),
            self.store.brain_dump(self.day),
        )
        path = save_markdown_report(self.day, markdown)
        QMessageBox.information(self, "리포트 생성", f"Markdown 리포트를 생성했습니다.\n{path}")
        return markdown

    def show_ai_feedback(self) -> None:
        markdown = build_markdown_report(
            self.day,
            self.store.todos_for_day(self.day),
            self.store.timer_records_for_day(self.day),
            self.store.brain_dump(self.day),
        )
        QMessageBox.information(self, "AI 피드백", self.ai.generate_feedback(markdown))

    def status_label(self, status: str) -> str:
        return {"open": "진행 전", "done": "완료", "deferred": "미룸"}.get(status, status)

    def clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
