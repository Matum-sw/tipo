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
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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
from ui.todo_add_dialog import TodoAddDialog
from ui.widgets import Card, Pill, TimeBlockButton, TimeGridWidget, TimelineHeader


HOURS = list(range(24))
MINUTES = (0, 10, 20, 30, 40, 50)
POMODORO_FOCUS_SECONDS = 25 * 60
POMODORO_BREAK_SECONDS = 5 * 60
ALARM_FILE = ROOT_DIR / "assets" / "alarm.wav"

ALL_BLOCK_KEYS = [f"{h:02d}:{m:02d}" for h in HOURS for m in MINUTES]
BLOCK_KEY_INDEX = {k: i for i, k in enumerate(ALL_BLOCK_KEYS)}

SUBJECT_COLORS = [
    {"bg": "#eaf3ff", "border": "#b9d4ff", "text": "#1f5fcf"},  # 0: blue
    {"bg": "#f3eaff", "border": "#c9b9ff", "text": "#5c1fcf"},  # 1: purple
    {"bg": "#fff0ea", "border": "#ffd0b9", "text": "#a84800"},  # 2: orange
    {"bg": "#ffeaf5", "border": "#ffb9d9", "text": "#b8006b"},  # 3: pink
    {"bg": "#eafaf5", "border": "#b9e8d4", "text": "#006b4c"},  # 4: teal
    {"bg": "#fafaea", "border": "#e8e4b9", "text": "#7a7a00"},  # 5: yellow-green
    {"bg": "#ffeaea", "border": "#ffb9b9", "text": "#c00000"},  # 6: red
]
SUBJECT_COLOR_OTHER = {"bg": "#eff8ed", "border": "#cfeac9", "text": "#477d37"}


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
        self.subject_color_map = {}
        self.subject_color_idx_map = {}
        self.drag_todo_id = None
        self.drag_visited_blocks = set()
        self.drag_is_painting = False
        self.drag_last_block_key = None
        self.drag_start_block_key = None
        self.drag_existing_blocks = {}
        self.delete_mode = False
        self.running = None
        self.pomodoro_history = []
        self.tick = QTimer(self)
        self.tick.timeout.connect(self.update_timer)
        self.current_time_scroll_timer = QTimer(self)
        self.current_time_scroll_timer.timeout.connect(self.center_current_time_in_plan)
        self.current_time_scroll_timer.start(60_000)
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
        self.date_button.setMinimumWidth(148)
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
        card = Card("")  # 제목은 아래 헤더 행에서 직접 구성
        parent.addWidget(card, 3)

        # 제목 + 추가/삭제 버튼을 같은 행에 배치
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        title_lbl = QLabel("To Do List")
        title_lbl.setObjectName("CardTitle")
        self.add_button = QPushButton("+")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.setFixedSize(34, 34)
        self.add_button.setToolTip("할 일 추가")
        self.add_button.clicked.connect(self.open_add_todo_dialog)
        self.delete_todo_button = QPushButton("−")
        self.delete_todo_button.setObjectName("DangerButton")
        self.delete_todo_button.setFixedSize(34, 34)
        self.delete_todo_button.setToolTip("선택 항목 삭제")
        self.delete_todo_button.clicked.connect(self.delete_selected_todo)
        header.addWidget(title_lbl, 1)
        header.addWidget(self.add_button)
        header.addWidget(self.delete_todo_button)
        card.layout.addLayout(header)

        self.selected_todo_label = QLabel("선택된 할 일 없음")
        self.selected_todo_label.setObjectName("SelectedTodoLabel")
        self.selected_todo_label.setWordWrap(True)
        card.layout.addWidget(self.selected_todo_label)

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
        card = Card(
            "Time Plan",
            "To Do를 선택하고 시간 블록을 클릭하거나 드래그하면 배치됩니다.",
        )
        parent.addWidget(card, 1)

        plan_actions = QHBoxLayout()
        self.selected_block_label = QLabel("선택된 블록 없음")
        self.selected_block_label.setObjectName("MutedText")
        self.delete_mode_button = QPushButton("수정 모드")
        self.delete_mode_button.setObjectName("SoftButton")
        self.delete_mode_button.setCheckable(True)
        self.delete_mode_button.setFixedHeight(30)
        self.delete_mode_button.clicked.connect(self.toggle_delete_mode)
        clear_all_button = QPushButton("전체 삭제")
        clear_all_button.setObjectName("DangerButton")
        clear_all_button.setFixedHeight(30)
        clear_all_button.clicked.connect(self.clear_all_blocks)
        plan_actions.addWidget(self.selected_block_label, 1)
        plan_actions.addWidget(self.delete_mode_button)
        plan_actions.addWidget(clear_all_button)
        card.layout.addLayout(plan_actions)

        self.plan_scroll = QScrollArea()
        self.plan_scroll.setWidgetResizable(True)
        self.plan_scroll.setObjectName("PlanScroll")
        self.plan_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.plan_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.time_grid_widget = TimeGridWidget(lambda: self.day)
        self.time_grid_widget.setObjectName("TimeGrid")
        self.time_grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.time_grid = QGridLayout(self.time_grid_widget)
        self.time_grid.setHorizontalSpacing(0)
        self.time_grid.setVerticalSpacing(0)
        self.time_grid.setContentsMargins(4, 4, 4, 4)

        self.time_grid.addWidget(QLabel(""), 0, 0)
        self.time_grid.addWidget(TimelineHeader(), 0, 1, 1, len(MINUTES))
        self.time_grid.setRowMinimumHeight(0, 38)

        for row, hour in enumerate(HOURS, start=1):
            hour_label = QLabel(f"{hour:02d}")
            hour_label.setObjectName("HourLabel")
            hour_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
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

        end_label = QLabel("24")
        end_label.setObjectName("HourLabel")
        end_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.time_grid.addWidget(end_label, len(HOURS) + 1, 0)

        self.time_grid.setColumnStretch(0, 0)
        self.time_grid.setColumnMinimumWidth(0, 26)
        for column in range(1, len(MINUTES) + 1):
            self.time_grid.setColumnStretch(column, 1)
        self.time_grid.setRowStretch(0, 0)
        for row in range(1, len(HOURS) + 1):
            self.time_grid.setRowStretch(row, 1)
        self.time_grid.setRowStretch(len(HOURS) + 1, 0)

        self.plan_scroll.setWidget(self.time_grid_widget)
        self.time_grid_widget.set_block_buttons(self.block_buttons)
        card.layout.addWidget(self.plan_scroll, 1)
        QTimer.singleShot(0, self.center_current_time_in_plan)

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

    def open_add_todo_dialog(self) -> None:
        dialog = TodoAddDialog(self.store, self.day, self.selected_subject_id, self.subject_color_map, self)
        dialog.exec()
        self.selected_subject_id = dialog.selected_subject_id
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
        if self.delete_mode:
            self.drag_is_painting = True
            self.drag_visited_blocks = set()
            self.erase_block(block_key)
            return

        self.set_selected_block(block_key)
        if self.selected_todo_id:
            self.drag_todo_id = self.selected_todo_id
            self.drag_start_block_key = block_key
            self.drag_visited_blocks = set()
            self.drag_existing_blocks = dict(self.store.blocks_for_day(self.day))
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
        if not self.drag_is_painting:
            return
        if self.delete_mode:
            self.erase_block(block_key)
        elif self.drag_todo_id:
            self.paint_todo_to_block(block_key)

    def on_block_moved(self, global_pos) -> None:
        if not self.drag_is_painting:
            return
        widget = QApplication.widgetAt(global_pos)
        while widget and not isinstance(widget, TimeBlockButton):
            widget = widget.parentWidget()
        if isinstance(widget, TimeBlockButton):
            if self.delete_mode:
                self.erase_block(widget.block_key)
            elif self.drag_todo_id:
                self.paint_todo_to_block(widget.block_key)

    def on_block_released(self, block_key: str) -> None:
        if not self.drag_is_painting:
            return

        visited_count = len(self.drag_visited_blocks)
        todo_id = self.drag_todo_id
        last_block_key = self.drag_last_block_key or block_key
        was_delete_mode = self.delete_mode
        self.drag_todo_id = None
        self.drag_is_painting = False
        self.drag_last_block_key = None
        self.drag_start_block_key = None
        self.drag_existing_blocks = {}
        self.drag_visited_blocks = set()

        if was_delete_mode:
            return

        self.refresh_blocks()

        if visited_count == 1 and todo_id:
            self.selected_todo_id = todo_id
            self.set_selected_block(last_block_key)
            self.refresh_todos()

    def paint_todo_to_block(self, block_key: str) -> None:
        if not self.drag_todo_id:
            return

        if self.drag_last_block_key and self.drag_last_block_key != block_key:
            last_idx = BLOCK_KEY_INDEX.get(self.drag_last_block_key, 0)
            curr_idx = BLOCK_KEY_INDEX.get(block_key, 0)
            lo, hi = min(last_idx, curr_idx), max(last_idx, curr_idx)
            keys_to_paint = ALL_BLOCK_KEYS[lo : hi + 1]
        else:
            keys_to_paint = [block_key]

        for key in keys_to_paint:
            if key in self.drag_visited_blocks:
                continue
            existing = self.drag_existing_blocks.get(key)
            if existing and existing != self.drag_todo_id:
                continue  # 다른 할 일이 배치된 블록은 덮어쓰지 않음
            self.store.assign_block(self.day, key, self.drag_todo_id)
            self.drag_visited_blocks.add(key)
            self.drag_last_block_key = key
            self.refresh_single_block(key, self.drag_todo_id)

        self.set_selected_block(block_key)

    def erase_block(self, block_key: str) -> None:
        if block_key in self.drag_visited_blocks:
            return
        self.drag_visited_blocks.add(block_key)
        # 타이머가 작동한 블록은 삭제 불가
        if self.store.block_has_timer_records(self.day, block_key):
            return
        self.store.delete_block(self.day, block_key)
        button = self.block_buttons.get(block_key)
        if button:
            button.set_task_text("")
            button.set_subject_color(None)
            button.setProperty("filled", False)
            button.setProperty("life", False)
            button.setProperty("color_idx", "")
            button.setProperty("selected", False)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def toggle_delete_mode(self) -> None:
        self.delete_mode = self.delete_mode_button.isChecked()
        if self.delete_mode:
            self.delete_mode_button.setText("삭제 모드")
            self.delete_mode_button.setObjectName("DangerButton")
        else:
            self.delete_mode_button.setText("수정 모드")
            self.delete_mode_button.setObjectName("SoftButton")
        self.repolish(self.delete_mode_button)

    def clear_all_blocks(self) -> None:
        reply = QMessageBox.question(
            self,
            "계획 전체 삭제",
            "오늘의 모든 시간 계획을 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.store.clear_unprotected_blocks_for_day(self.day)
            if self.running:
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
        if self.running and self.running["mode"] in {"focus", "break", "paused"}:
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
            "visual_alert_mode": None,
            "visual_alert_started_at": None,
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
            self.running["segment_started_at"] = time.time()
            self.pause_button.setText("실행")
            self.pause_button.setObjectName("PrimaryButton")
            self.repolish(self.pause_button)
            self.update_timer()
            return

        self.start_timer_segment(self.next_pomodoro_mode())

    def current_running_task(self) -> tuple[str | None, int | None]:
        now = datetime.now()
        block_key = f"{now.hour:02d}:{(now.minute // 10) * 10:02d}"
        return block_key, self.store.blocks_for_day(self.day).get(block_key)

    def start_timer_segment(self, mode: str) -> None:
        if not self.running:
            return
        if self.running["mode"] == "paused":
            self.finish_current_timer_segment()
        self.running["mode"] = mode
        self.running["segment_started_at"] = time.time()
        self.tick.start(1000)
        if mode == "focus":
            self.pause_button.setText("일시정지")
        else:
            self.pause_button.setText("휴식 일시정지")
        self.pause_button.setObjectName("DangerButton")
        self.repolish(self.pause_button)
        self.update_timer()

    def finish_current_timer_segment(self) -> None:
        if not self.running or self.running["mode"] not in {"focus", "break", "paused"}:
            return
        ended = time.time()
        started = self.running["segment_started_at"]
        if started is None:
            return
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

    def show_timer_alert(self, title: str, message: str, visual_mode: str | None = None) -> None:
        if visual_mode and self.running:
            self.running["visual_alert_mode"] = visual_mode
            self.running["visual_alert_started_at"] = time.time()
            self.refresh_timer_visual()
            QApplication.processEvents()
        QMessageBox.information(self, title, message)
        if self.running:
            self.running["visual_alert_mode"] = None
            self.running["visual_alert_started_at"] = None

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
        elapsed = sum(max(1, int(segment["end"] - segment["start"])) for segment in self.running["segments"] if segment["mode"] == mode)
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
            self.show_timer_alert("집중 시간 종료", "25분 집중 시간이 끝났습니다. 확인을 누르면 5분 휴식이 시작됩니다.", "break")
            self.finish_current_timer_segment()
            self.start_timer_segment("break")
        elif self.running["mode"] == "break" and self.segment_elapsed_seconds("break") >= POMODORO_BREAK_SECONDS:
            if self.running["break_alert_shown"]:
                return
            self.running["break_alert_shown"] = True
            self.refresh_timer_visual()
            QApplication.processEvents()
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
        if self.running["mode"] in {"focus", "break", "paused"}:
            segments.append({"mode": self.running["mode"], "start": self.running["segment_started_at"], "end": time.time()})
        if self.running.get("visual_alert_mode") and self.running.get("visual_alert_started_at"):
            segments.append(
                {
                    "mode": self.running["visual_alert_mode"],
                    "start": self.running["visual_alert_started_at"],
                    "end": time.time(),
                }
            )
        return segments

    def refresh_timer_visual(self) -> None:
        if hasattr(self, "time_grid_widget"):
            self.time_grid_widget.set_timer_segments(self.active_timer_segments())

    def center_current_time_in_plan(self) -> None:
        if self.day != datetime.now().date().isoformat() or not hasattr(self, "plan_scroll"):
            return

        now = datetime.now()
        block = self.block_buttons.get(f"{now.hour:02d}:{(now.minute // 10) * 10:02d}")
        if not block:
            return

        scroll_bar = self.plan_scroll.verticalScrollBar()
        viewport_height = self.plan_scroll.viewport().height()
        target = block.y() + (block.height() // 2) - (viewport_height // 2)
        target = max(scroll_bar.minimum(), min(target, scroll_bar.maximum()))
        scroll_bar.setValue(target)

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
        if self.running["mode"] in {"focus", "break", "paused"}:
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
            self.store.save_brain_dump("global", self.brain_dump.toPlainText())

    def change_date(self, qdate: QDate) -> None:
        if self.running:
            self.cancel_timer_session()
        self.day = qdate.toString("yyyy-MM-dd")
        self.selected_todo_id = None
        self.pomodoro_history = []
        self.update_date_button()
        self.set_selected_block(None)
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
        QTimer.singleShot(0, self.center_current_time_in_plan)

    def refresh_subjects(self) -> None:
        subjects = self.store.subjects(include_other=True)
        if not subjects:
            return
        if self.selected_subject_id is None or not any(subject.id == self.selected_subject_id for subject in subjects):
            self.selected_subject_id = subjects[0].id

        # Build subject color maps
        self.subject_color_map = {}
        self.subject_color_idx_map = {}
        color_idx = 0
        for subject in subjects:
            if subject.kind == "other":
                self.subject_color_map[subject.id] = SUBJECT_COLOR_OTHER
                self.subject_color_idx_map[subject.id] = -1
            else:
                self.subject_color_map[subject.id] = SUBJECT_COLORS[color_idx % len(SUBJECT_COLORS)]
                self.subject_color_idx_map[subject.id] = color_idx % len(SUBJECT_COLORS)
                color_idx += 1

        # selected_subject_id 유효성 보장
        if not any(s.id == self.selected_subject_id for s in subjects):
            self.selected_subject_id = subjects[0].id

    def select_subject(self, subject_id: int) -> None:
        self.selected_subject_id = subject_id

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

        if hasattr(self, "selected_todo_label"):
            if self.selected_todo_id and self.selected_todo_id in self.todo_lookup:
                todo = self.todo_lookup[self.selected_todo_id]
                color = self.subject_color_map.get(todo.subject_id, SUBJECT_COLORS[0])
                self.selected_todo_label.setText(f"▶  {todo.subject_name}  |  {todo.title}")
                self.selected_todo_label.setStyleSheet(
                    f"color: {color['text']}; font-weight: 800; font-size: 13px;"
                )
            else:
                self.selected_todo_label.setText("선택된 할 일 없음")
                self.selected_todo_label.setStyleSheet("")

    def todo_item_height(self, todo) -> int:
        title_lines = max(1, (len(todo.title) + 20) // 21)
        meta_lines = max(1, (len(todo.subject_name) + len(todo.status) + 16) // 30)
        return min(150, 52 + title_lines * 22 + meta_lines * 18)

    def create_todo_item_widget(self, todo) -> QWidget:
        color = self.subject_color_map.get(todo.subject_id, SUBJECT_COLORS[0])
        is_selected = todo.id == self.selected_todo_id

        frame = QFrame()
        frame.setObjectName("TodoItemWidget")
        frame.setAttribute(Qt.WA_TransparentForMouseEvents)
        if is_selected:
            frame.setStyleSheet(
                f"background-color: {color['bg']}; border-radius: 10px;"
            )
        else:
            frame.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 10, 12)
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
        content = self.store.brain_dump("global")
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
                button.set_subject_color(None)
                button.setProperty("filled", False)
                button.setProperty("life", False)
                button.setProperty("color_idx", "")
            else:
                color = self.subject_color_map.get(todo.subject_id)
                cidx = self.subject_color_idx_map.get(todo.subject_id, -1)
                button.set_task_text(f"{todo.subject_name}\n{todo.title}")
                button.set_subject_color(color)
                button.setProperty("filled", True)
                button.setProperty("life", todo.subject_kind == "other")
                button.setProperty("color_idx", str(cidx) if cidx >= 0 else "")
            button.setProperty("selected", key == self.selected_block_key)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def refresh_single_block(self, block_key: str, todo_id: int) -> None:
        button = self.block_buttons.get(block_key)
        todo = self.todo_lookup.get(todo_id)
        if not button or not todo:
            return
        color = self.subject_color_map.get(todo.subject_id)
        cidx = self.subject_color_idx_map.get(todo.subject_id, -1)
        button.set_task_text(f"{todo.subject_name}\n{todo.title}")
        button.set_subject_color(color)
        button.setProperty("filled", True)
        button.setProperty("life", todo.subject_kind == "other")
        button.setProperty("color_idx", str(cidx) if cidx >= 0 else "")
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
