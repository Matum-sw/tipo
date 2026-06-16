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
    QInputDialog,
    QLabel,
    QLineEdit,
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
from core.paths import APP_NAME, ROOT_DIR
from core.reporting import build_ai_coaching_prompt, build_markdown_report, save_markdown_report
from ui.date_dialog import DateDialog
from ui.settings_dialog import SettingsDialog
from ui.stats_dialog import SubjectStatsDialog
from ui.subject_dialog import SubjectDialog
from ui.todo_add_dialog import TodoAddDialog
from ui.todo_edit_dialog import TodoEditDialog
from ui.widgets import Card, DonutChartWidget, TimeBlockButton, TimeGridWidget, TimelineHeader


HOURS = list(range(24))
MINUTES = (0, 10, 20, 30, 40, 50)
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

# 다크 모드 전용 과목 색상 (배경 어둡게, 텍스트 밝게)
SUBJECT_COLORS_DARK = [
    {"bg": "#1a2c4a", "border": "#2a4880", "text": "#7baeff"},  # 0: blue
    {"bg": "#261a4a", "border": "#432880", "text": "#c07aff"},  # 1: purple
    {"bg": "#3a2010", "border": "#603818", "text": "#ff9050"},  # 2: orange
    {"bg": "#3a1230", "border": "#602050", "text": "#ff7ab0"},  # 3: pink
    {"bg": "#102a20", "border": "#1a4838", "text": "#50cc80"},  # 4: teal
    {"bg": "#2a2a10", "border": "#484818", "text": "#cccc40"},  # 5: yellow-green
    {"bg": "#3a1010", "border": "#601818", "text": "#ff6060"},  # 6: red
]
SUBJECT_COLOR_OTHER_DARK = {"bg": "#162810", "border": "#2a4820", "text": "#60c870"}


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.ai = AIFeedbackService(self.store.get_setting("openai_api_key", ""))
        self.day = self.store.today()

        # 설정값 로드 (분 단위 → 초 단위로 변환)
        self._load_timer_config()

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
        self._db_segments_cache: list[dict] = []
        self._db_segments_dirty = True

        self.tick = QTimer(self)
        self.tick.timeout.connect(self.update_timer)
        self.current_time_scroll_timer = QTimer(self)
        self.current_time_scroll_timer.timeout.connect(self.center_current_time_in_plan)
        self.current_time_scroll_timer.start(60_000)
        self.alarm = QSoundEffect(self)
        self._apply_alarm_volume()
        if ALARM_FILE.exists():
            self.alarm.setSource(QUrl.fromLocalFile(str(ALARM_FILE)))

        self.setWindowTitle(APP_NAME)
        self.resize(1360, 900)
        self.setMinimumSize(1180, 760)

        if not self.store.has_real_subjects():
            SubjectDialog(self.store, self).exec()

        self.build()
        self.refresh_all()

    # ── 설정 ──────────────────────────────────────────────────────────────────

    def _load_timer_config(self) -> None:
        def gi(key, default):
            return int(self.store.get_setting(key, str(default)))
        self.focus_seconds = gi("focus_minutes", 25) * 60
        self.break_seconds = gi("break_minutes", 5) * 60
        self.long_break_seconds = gi("long_break_minutes", 15) * 60
        self.sprint_count = gi("sprint_count", 4)

    def _apply_alarm_volume(self) -> None:
        vol = int(self.store.get_setting("alarm_volume", "80"))
        self.alarm.setVolume(vol / 100.0)

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.store, self.day, self.refresh_all, self)
        if dlg.exec():
            self._load_timer_config()
            self._apply_alarm_volume()
            self._apply_theme()
            # 테마 전환 후 과목 색상 맵 및 UI 즉시 재빌드
            self.refresh_subjects()
            self.refresh_todos()
            self.refresh_blocks()
        self.ai.set_api_key(self.store.get_setting("openai_api_key", ""))
        if dlg.data_reset:
            self.store.reset_all_data()
            self._db_segments_dirty = True
            self.selected_todo_id = None
            self.selected_block_key = None
            self.pomodoro_history = []
            if self.running:
                self.tick.stop()
                self.running = None
            self.refresh_all()
            if not self.store.has_real_subjects():
                SubjectDialog(self.store, self).exec()
                self.refresh_all()

    def _is_dark_mode(self) -> bool:
        return self.store.get_setting("dark_mode", "0") == "1"

    def _apply_theme(self) -> None:
        dark_mode = self.store.get_setting("dark_mode", "0") == "1"
        dark_file = ROOT_DIR / "styles" / "dark.qss"
        light_file = ROOT_DIR / "styles" / "styles.qss"
        qss_file = dark_file if dark_mode and dark_file.exists() else light_file
        app = QApplication.instance()
        if app and qss_file.exists():
            app.setStyleSheet(qss_file.read_text(encoding="utf-8"))

    # ── UI 빌드 ───────────────────────────────────────────────────────────────

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
        controls_layout.setSpacing(8)

        subject_button = QPushButton("과목 관리")
        subject_button.clicked.connect(self.open_subjects)
        subject_button.setObjectName("GhostButton")
        subject_button.setStyleSheet("padding: 6px 10px; min-height: 0;")

        settings_button = QPushButton("설정")
        settings_button.clicked.connect(self.open_settings)
        settings_button.setObjectName("GhostButton")
        settings_button.setStyleSheet("padding: 6px 10px; min-height: 0;")

        controls_layout.addWidget(self.date_button, 1)
        controls_layout.addWidget(subject_button)
        controls_layout.addWidget(settings_button)
        parent.addWidget(controls)

    def build_todo_card(self, parent) -> None:
        card = Card("")
        parent.addWidget(card, 3)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        title_lbl = QLabel("To Do List")
        title_lbl.setObjectName("CardTitle")
        self.add_button = QPushButton("추가")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.setStyleSheet("padding: 4px 12px; min-height: 0; border-radius: 8px;")
        self.add_button.setToolTip("할 일 추가 (더블클릭으로 편집)")
        self.add_button.clicked.connect(self.open_add_todo_dialog)
        header.addWidget(title_lbl, 1)
        header.addWidget(self.add_button)
        card.layout.addLayout(header)

        self.selected_todo_label = QLabel("선택된 할 일 없음")
        self.selected_todo_label.setObjectName("SelectedTodoLabel")
        self.selected_todo_label.setWordWrap(True)
        card.layout.addWidget(self.selected_todo_label)

        self.todo_list = QListWidget()
        self.todo_list.setWordWrap(True)
        self.todo_list.itemClicked.connect(self.select_todo)
        self.todo_list.viewport().installEventFilter(self)
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
        self.delete_mode_button = QPushButton("추가 모드")
        self.delete_mode_button.setObjectName("SoftButton")
        self.delete_mode_button.setCheckable(True)
        self.delete_mode_button.setStyleSheet("padding: 4px 10px; min-height: 0; font-size: 13px; border-radius: 8px;")
        self.delete_mode_button.clicked.connect(self.toggle_delete_mode)
        clear_all_button = QPushButton("전체 삭제")
        clear_all_button.setObjectName("DangerButton")
        clear_all_button.setStyleSheet("padding: 4px 10px; min-height: 0; font-size: 13px; border-radius: 8px;")
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
        self.time_grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.time_grid = QGridLayout(self.time_grid_widget)
        _ROW_H = 52      # 1시간 행 높이: 한 행 안에 10분 블록 6개를 가로로 배치
        _V_GAP  = 3      # 시간 행 사이에 보이는 간격

        self.time_grid.setHorizontalSpacing(0)
        self.time_grid.setVerticalSpacing(_V_GAP)
        self.time_grid.setContentsMargins(4, 4, 4, 4)

        self.time_grid.addWidget(QLabel(""), 0, 0)
        self.time_grid.addWidget(TimelineHeader(), 0, 1, 1, len(MINUTES))
        self.time_grid.setRowMinimumHeight(0, 38)

        for row, hour in enumerate(HOURS, start=1):
            hour_label = QLabel(f"{hour:02d}")
            hour_label.setObjectName("HourLabel")
            hour_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            self.time_grid.addWidget(hour_label, row, 0)
            self.time_grid.setRowMinimumHeight(row, _ROW_H)
            for column, minute in enumerate(MINUTES, start=1):
                key = f"{hour:02d}:{minute:02d}"
                button = TimeBlockButton(key)
                button.setFixedHeight(_ROW_H)
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
        end_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.time_grid.addWidget(end_label, len(HOURS) + 1, 0)
        self.time_grid.setRowMinimumHeight(len(HOURS) + 1, 22)

        self.time_grid.setColumnStretch(0, 0)
        self.time_grid.setColumnMinimumWidth(0, 26)
        for column in range(1, len(MINUTES) + 1):
            self.time_grid.setColumnStretch(column, 1)
            self.time_grid.setColumnMinimumWidth(column, 0)

        # 고정 높이: 상하 여백(8) + 헤더(38) + 데이터행(24×ROW_H) + 말미행(22)
        #           + 행 간격 25개 (26개 행 사이 25개 간격)
        _NUM_ROWS = 1 + len(HOURS) + 1  # header + data + end = 26
        _grid_fixed_h = 8 + 38 + len(HOURS) * _ROW_H + 22 + (_NUM_ROWS - 1) * _V_GAP
        self.time_grid_widget.setFixedHeight(_grid_fixed_h)

        self.plan_scroll.setWidget(self.time_grid_widget)
        self.time_grid_widget.set_block_buttons(self.block_buttons)
        card.layout.addWidget(self.plan_scroll, 1)
        QTimer.singleShot(0, self.center_current_time_in_plan)

    def build_timer_card(self, parent) -> None:
        card = Card("Timer")
        parent.addWidget(card)
        self.pomodoro_status = QLabel(self.pomodoro_status_text())
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
        self.exit_button = QPushButton("종료")
        self.exit_button.setObjectName("GhostButton")
        self.exit_button.clicked.connect(self.exit_timer_session)
        self.pause_button = QPushButton("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.pause_button.clicked.connect(self.toggle_timer)
        self.complete_button = QPushButton("완료")
        self.complete_button.setObjectName("CompleteButton")
        self.complete_button.clicked.connect(self.complete_timer_session)
        actions.addWidget(self.exit_button)
        actions.addWidget(self.pause_button)
        actions.addWidget(self.complete_button)
        card.layout.addLayout(actions)

    def build_stats_card(self, parent) -> None:
        card = Card("Study Stats")
        parent.addWidget(card, 1)

        # 도넛 + 시간 정보 가로 배치
        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        self.donut_chart = DonutChartWidget()
        self.donut_chart.setFixedSize(130, 130)
        top_row.addWidget(self.donut_chart)

        # 오른쪽: 타이머 작동 시간 (위), 공부 시간 (아래)
        time_col = QVBoxLayout()
        time_col.setSpacing(8)
        time_col.addStretch(1)

        active_title = QLabel("타이머 작동 시간")
        active_title.setStyleSheet("color: #738095; font-size: 11px; font-weight: 700;")
        self.active_time_label = QLabel("—")
        self.active_time_label.setStyleSheet("color: #3f7df1; font-size: 17px; font-weight: 800;")

        focus_title = QLabel("계획 시간")
        focus_title.setStyleSheet("color: #738095; font-size: 11px; font-weight: 700;")
        self.focus_time_label = QLabel("—")
        self.focus_time_label.setStyleSheet("color: #4a7bd8; font-size: 17px; font-weight: 800;")

        time_col.addWidget(active_title)
        time_col.addWidget(self.active_time_label)
        time_col.addSpacing(6)
        time_col.addWidget(focus_title)
        time_col.addWidget(self.focus_time_label)
        time_col.addStretch(1)
        top_row.addLayout(time_col, 1)
        card.layout.addLayout(top_row)

        # 범례: 공부 먼저, 타이머, 24h
        legend_row = QHBoxLayout()
        legend_row.setSpacing(12)
        dot1 = QLabel("● 계획")
        dot1.setStyleSheet("color: #93c5fd; font-size: 11px; font-weight: 700;")
        dot2 = QLabel("● 타이머")
        dot2.setStyleSheet("color: #3f7df1; font-size: 11px; font-weight: 700;")
        dot3 = QLabel("● 24h")
        dot3.setStyleSheet("color: #c8d0de; font-size: 11px; font-weight: 700;")
        legend_row.addStretch(1)
        legend_row.addWidget(dot1)
        legend_row.addWidget(dot2)
        legend_row.addWidget(dot3)
        legend_row.addStretch(1)
        card.layout.addLayout(legend_row)

        card.layout.addStretch(1)

        report_actions = QHBoxLayout()
        subject_stats_btn = QPushButton("과목별 공부시간")
        subject_stats_btn.setObjectName("StatsSoftButton")
        subject_stats_btn.clicked.connect(self.show_subject_stats)
        adjust_button = QPushButton("AI 시간표 재조정")
        adjust_button.setObjectName("StatsPrimaryButton")
        adjust_button.clicked.connect(self.show_schedule_adjustment_choices)
        report_actions.addWidget(subject_stats_btn)
        report_actions.addWidget(adjust_button)
        card.layout.addLayout(report_actions)

    # ── Todo ──────────────────────────────────────────────────────────────────

    def open_add_todo_dialog(self) -> None:
        self.log_event("todo_add_opened", subject_id=self.selected_subject_id)
        dialog = TodoAddDialog(self.store, self.day, self.selected_subject_id, self.subject_color_map, self)
        dialog.exec()
        self.selected_subject_id = dialog.selected_subject_id
        self.refresh_todos()

    def select_todo(self, item: QListWidgetItem) -> None:
        self.selected_todo_id = item.data(Qt.UserRole)
        todo = self.todo_lookup.get(self.selected_todo_id)
        self.log_event(
            "todo_selected",
            todo_id=self.selected_todo_id,
            subject_id=todo.subject_id if todo else None,
        )
        self.refresh_todos()

    def open_todo_edit_dialog(self, item: QListWidgetItem) -> None:
        todo_id = item.data(Qt.UserRole)
        todo = self.todo_lookup.get(todo_id)
        if not todo:
            return
        self.log_event("todo_edit_opened", todo_id=todo.id, subject_id=todo.subject_id)
        dlg = TodoEditDialog(self.store, todo, self.subject_color_map, self)
        dlg.exec()
        if dlg.deleted:
            if self.running and self.running["todo_id"] == todo_id:
                reply = QMessageBox.question(
                    self, "타이머 실행 중",
                    "이 할 일의 타이머가 실행 중입니다. 취소하고 삭제하시겠습니까?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
                self._force_cancel_timer()
            self.store.delete_todo(todo_id)
            self.log_event("todo_deleted", todo_id=todo_id, subject_id=todo.subject_id)
            if self.selected_todo_id == todo_id:
                self.selected_todo_id = None
        self.refresh_all()

    def delete_selected_todo(self) -> None:
        if not self.selected_todo_id:
            QMessageBox.information(self, "To Do 선택", "삭제할 To Do를 먼저 선택하세요.")
            return
        if self.running and self.running["todo_id"] == self.selected_todo_id:
            reply = QMessageBox.question(
                self,
                "타이머 실행 중",
                "이 할 일의 타이머가 실행 중입니다. 타이머를 중단하고 삭제하시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self._force_cancel_timer()
        todo = self.todo_lookup.get(self.selected_todo_id)
        self.store.delete_todo(self.selected_todo_id)
        self.log_event(
            "todo_deleted",
            todo_id=self.selected_todo_id,
            subject_id=todo.subject_id if todo else None,
        )
        self.selected_todo_id = None
        self.selected_block_key = None
        self.refresh_all()

    # ── Time Plan ─────────────────────────────────────────────────────────────

    def is_block_in_past(self, block_key: str) -> bool:
        """self.day의 block_key가 가리키는 시간이 이미 지나간 시간인지 여부."""
        today = datetime.now().date().isoformat()
        if self.day < today:
            return True
        if self.day > today:
            return False
        now = datetime.now()
        current_block_minutes = (now.hour * 60 + now.minute) // 10 * 10
        return self.block_start_minutes(block_key) < current_block_minutes

    def on_block_pressed(self, block_key: str) -> None:
        if self.delete_mode:
            self.drag_is_painting = True
            self.drag_visited_blocks = set()
            self.erase_block(block_key)
            return

        self.set_selected_block(block_key)
        blocks = dict(self.store.blocks_for_day(self.day))
        if self.selected_todo_id:
            if self.is_block_in_past(block_key):
                QMessageBox.information(self, "배치 불가", "이미 지나간 시간에는 일정을 추가할 수 없습니다.")
                return
            self.drag_todo_id = self.selected_todo_id
            self.drag_start_block_key = block_key
            self.drag_visited_blocks = set()
            self.drag_existing_blocks = blocks
            self.drag_is_painting = True
            self.paint_todo_to_block(block_key)
            return

        todo_id = blocks.get(block_key)
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
            self.log_event("block_erased", block_key=last_block_key, metadata={"block_count": visited_count})
            self.refresh_todos()
            self.refresh_stats()
            return

        self.refresh_blocks()
        self.refresh_todos()
        self.refresh_stats()

        if visited_count == 1 and todo_id:
            self.selected_todo_id = todo_id
            self.set_selected_block(last_block_key)
            self.refresh_todos()
        if todo_id:
            todo = self.todo_lookup.get(todo_id)
            self.log_event(
                "block_assigned",
                todo_id=todo_id,
                subject_id=todo.subject_id if todo else None,
                block_key=last_block_key,
                metadata={"block_count": visited_count},
            )

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
            if self.is_block_in_past(key):
                continue
            existing = self.drag_existing_blocks.get(key)
            if existing and existing != self.drag_todo_id:
                continue
            self.store.assign_block(self.day, key, self.drag_todo_id)
            self.drag_visited_blocks.add(key)
            self.drag_last_block_key = key
            self.refresh_single_block(key, self.drag_todo_id)

        self.set_selected_block(block_key)

    def erase_block(self, block_key: str) -> None:
        if block_key in self.drag_visited_blocks:
            return
        self.drag_visited_blocks.add(block_key)
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
        self.log_event("delete_mode_toggled", metadata={"enabled": self.delete_mode})
        if self.delete_mode:
            self.delete_mode_button.setText("삭제 모드")
            self.delete_mode_button.setObjectName("DangerButton")
        else:
            self.delete_mode_button.setText("추가 모드")
            self.delete_mode_button.setObjectName("SoftButton")
        self.repolish(self.delete_mode_button)

    def clear_all_blocks(self) -> None:
        reply = QMessageBox.question(
            self,
            "계획 전체 삭제",
            "오늘의 모든 시간 계획을 삭제하시겠습니까?\n(타이머가 실제로 작동한 블록은 보호됩니다)",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self.running:
                self._force_stop_timer()
            self.store.clear_unprotected_blocks_for_day(self.day)
            self.log_event("blocks_cleared")
            self.selected_block_key = None
            self.update_selected_block_label()
            self.refresh_blocks()
            self.refresh_todos()
            self.refresh_stats()

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

    # ── Timer ─────────────────────────────────────────────────────────────────

    def prepare_timer(self, todo_id: int, block_key: str | None = None) -> None:
        if self.running and self.running["mode"] in {"focus", "break", "long_break", "paused"}:
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
            "sprint_in_set": 1,
            "focus_alert_shown": False,
            "break_alert_shown": False,
            "long_break_alert_shown": False,
            "paused_from": None,
            "visual_alert_mode": None,
            "visual_alert_started_at": None,
        }
        self.pause_button.setText("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.repolish(self.pause_button)
        self.log_event("timer_prepared", todo_id=todo_id, subject_id=todo.subject_id, block_key=block_key)
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

        mode = self.running["mode"]
        if mode in {"break", "long_break"}:
            # 휴식 건너뛰기
            self.skip_break()
            return

        if mode == "focus":
            # 집중 일시정지
            self.finish_current_timer_segment()
            self.running["mode"] = "paused"
            self.running["paused_from"] = "focus"
            self.running["segment_started_at"] = time.time()
            self.log_event(
                "timer_paused",
                todo_id=self.running["todo_id"],
                subject_id=self.running["subject_id"],
                block_key=self.running["block_key"],
            )
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
        else:  # break / long_break
            self.pause_button.setText("건너뛰기")
        self.pause_button.setObjectName("DangerButton")
        self.repolish(self.pause_button)
        self.log_event(
            "timer_started",
            todo_id=self.running["todo_id"],
            subject_id=self.running["subject_id"],
            block_key=self.running["block_key"],
            metadata={"mode": mode},
        )
        self.update_timer()

    def finish_current_timer_segment(self) -> None:
        if not self.running or self.running["mode"] not in {"focus", "break", "long_break", "paused"}:
            return
        ended = time.time()
        started = self.running["segment_started_at"]
        if started is None:
            return
        mode = self.running["mode"]
        seconds = max(1, int(ended - started))
        self.running["segments"].append({"mode": mode, "start": started, "end": ended})
        if mode != "paused":
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
            self._db_segments_dirty = True
        self.running["segment_started_at"] = ended
        self.refresh_stats()
        self.refresh_timer_visual()

    def _maybe_checkpoint_save(self) -> None:
        """매 60초마다 현재 세그먼트를 저장하여 실시간 기록 보존."""
        if not self.running or self.running["mode"] not in {"focus", "break", "long_break"}:
            return
        started = self.running.get("segment_started_at")
        if started and time.time() - started >= 60:
            self.finish_current_timer_segment()

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
            self.pomodoro_status.setText(self.pomodoro_status_text())
            self.refresh_pomodoro_visual()
            self.refresh_timer_visual()
            return
        self.advance_pomodoro_if_needed()
        self._maybe_checkpoint_save()
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
            max(1, int(seg["end"] - seg["start"]))
            for seg in self.running["segments"]
            if seg["mode"] == mode
        )
        if self.running["mode"] == mode and self.running["segment_started_at"]:
            elapsed += max(0, int(time.time() - self.running["segment_started_at"]))
        return elapsed

    def next_pomodoro_mode(self) -> str:
        if self.running and self.running["mode"] == "paused":
            paused_from = self.running.get("paused_from", "focus")
            if paused_from == "focus" and self.segment_elapsed_seconds("focus") < self.focus_seconds:
                return "focus"
            if paused_from == "break" and self.segment_elapsed_seconds("break") < self.break_seconds:
                return "break"
            if paused_from == "long_break" and self.segment_elapsed_seconds("long_break") < self.long_break_seconds:
                return "long_break"
        return "focus"

    def timer_remaining_seconds(self) -> int:
        if not self.running:
            return 0
        mode = self.running["mode"]
        if mode == "break":
            return max(0, self.break_seconds - self.segment_elapsed_seconds("break"))
        if mode == "long_break":
            return max(0, self.long_break_seconds - self.segment_elapsed_seconds("long_break"))
        return max(0, self.focus_seconds - self.segment_elapsed_seconds("focus"))

    def advance_pomodoro_if_needed(self) -> None:
        if not self.running:
            return
        mode = self.running["mode"]

        if mode == "focus" and self.segment_elapsed_seconds("focus") >= self.focus_seconds:
            if self.running["focus_alert_shown"]:
                return
            self.running["focus_alert_shown"] = True
            self.finish_current_timer_segment()
            self.play_alarm()
            # 마지막 스프린트면 5분 휴식 없이 바로 긴 휴식
            if self.running["sprint_in_set"] >= self.sprint_count:
                self.record_completed_sprint()
                self.start_timer_segment("long_break")
            else:
                self.start_timer_segment("break")

        elif mode == "break" and self.segment_elapsed_seconds("break") >= self.break_seconds:
            if self.running["break_alert_shown"]:
                return
            self.running["break_alert_shown"] = True
            self.finish_current_timer_segment()
            self.play_alarm()
            self.record_completed_sprint()
            # 다음 스프린트 대기
            self.running["mode"] = "idle"
            self.tick.stop()
            self.pause_button.setText("실행")
            self.pause_button.setObjectName("PrimaryButton")
            self.repolish(self.pause_button)

        elif mode == "long_break" and self.segment_elapsed_seconds("long_break") >= self.long_break_seconds:
            if self.running.get("long_break_alert_shown"):
                return
            self.running["long_break_alert_shown"] = True
            self.finish_current_timer_segment()
            self.play_alarm()
            self.record_completed_set()
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
            return f"Pomodoro 1세트 · 스프린트 1/{self.sprint_count} · 집중 {self.focus_seconds // 60}:00"
        set_num = self.running["set_number"]
        sprint = self.running["sprint_in_set"]
        mode = self.running["mode"]
        if mode == "break":
            return f"Pomodoro {set_num}세트 · 스프린트 {sprint}/{self.sprint_count} · 휴식 {self.break_seconds // 60:02d}:00"
        if mode == "long_break":
            return f"Pomodoro {set_num}세트 완료 · 긴 휴식 {self.long_break_seconds // 60}:00"
        if mode == "paused":
            return f"Pomodoro {set_num}세트 · 스프린트 {sprint}/{self.sprint_count} · 일시정지"
        return f"Pomodoro {set_num}세트 · 스프린트 {sprint}/{self.sprint_count} · 집중 {self.focus_seconds // 60}:00"

    def record_completed_sprint(self) -> None:
        if not self.running:
            return
        focus_s = self.segment_elapsed_seconds("focus")
        break_s = self.segment_elapsed_seconds("break")
        if focus_s == 0:
            return
        self.pomodoro_history.append({
            "title": self.running["title"],
            "set": self.running["set_number"],
            "sprint": self.running["sprint_in_set"],
            "focus_seconds": focus_s,
            "break_seconds": break_s,
            "completed": focus_s >= self.focus_seconds and break_s >= self.break_seconds,
        })
        self.running["segments"] = []
        self.running["sprint_in_set"] += 1
        self.running["focus_alert_shown"] = False
        self.running["break_alert_shown"] = False

    def record_completed_set(self) -> None:
        if not self.running:
            return
        self.running["set_number"] += 1
        self.running["sprint_in_set"] = 1
        self.running["long_break_alert_shown"] = False

    def refresh_pomodoro_visual(self) -> None:
        lines = []
        if self.running:
            mode = self.running["mode"]
            if mode == "long_break":
                lb_min = self.segment_elapsed_seconds("long_break") // 60
                lines.append(f"긴 휴식 중: {lb_min}/{self.long_break_seconds // 60}분")
            else:
                focus_min = self.segment_elapsed_seconds("focus") // 60
                break_min = self.segment_elapsed_seconds("break") // 60
                sprint = self.running["sprint_in_set"]
                lines.append(
                    f"스프린트 {sprint}/{self.sprint_count}: "
                    f"집중 {focus_min}/{self.focus_seconds // 60}분 · 휴식 {break_min}/{self.break_seconds // 60}분"
                )
        for record in self.pomodoro_history[-4:]:
            mark = "완료" if record["completed"] else "진행"
            lines.append(f"{record['set']}세트 {record['sprint']}번: {mark} 집중 {record['focus_seconds'] // 60}분")
        self.pomodoro_visual.setText("\n".join(lines) if lines else "세트 기록 없음")

    def active_timer_segments(self) -> list[dict]:
        if not self.running:
            return []
        result = []
        if self.running["mode"] in {"focus", "break", "long_break", "paused"} and self.running["segment_started_at"]:
            result.append({
                "mode": self.running["mode"],
                "start": self.running["segment_started_at"],
                "end": time.time(),
            })
        if self.running.get("visual_alert_mode") and self.running.get("visual_alert_started_at"):
            result.append({
                "mode": self.running["visual_alert_mode"],
                "start": self.running["visual_alert_started_at"],
                "end": time.time(),
            })
        return result

    def db_timer_segments_for_today(self) -> list[dict]:
        if not self._db_segments_dirty:
            return self._db_segments_cache
        records = self.store.timer_records_for_day(self.day)
        segments = []
        for record in records:
            if record["event_type"] not in {"focus", "break", "long_break"}:
                continue
            if not record["started_at"] or not record["ended_at"]:
                continue
            try:
                start = datetime.fromisoformat(record["started_at"]).timestamp()
                end = datetime.fromisoformat(record["ended_at"]).timestamp()
                segments.append({"mode": record["event_type"], "start": start, "end": end})
            except (ValueError, AttributeError):
                continue
        self._db_segments_cache = segments
        self._db_segments_dirty = False
        return segments

    def refresh_timer_visual(self) -> None:
        if hasattr(self, "time_grid_widget"):
            saved = self.db_timer_segments_for_today()
            active = self.active_timer_segments()
            self.time_grid_widget.set_timer_segments(saved + active)

    def skip_break(self) -> None:
        """휴식(break/long_break) 건너뛰기 - 기록 저장 후 idle로 전환."""
        if not self.running:
            return
        mode = self.running["mode"]
        if mode not in {"break", "long_break"}:
            return
        self.finish_current_timer_segment()
        if mode == "break":
            self.record_completed_sprint()
        else:
            self.record_completed_set()
        self.running["mode"] = "idle"
        self.tick.stop()
        self.pause_button.setText("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.repolish(self.pause_button)
        self.log_event(
            "break_skipped",
            todo_id=self.running["todo_id"],
            subject_id=self.running["subject_id"],
            block_key=self.running["block_key"],
            metadata={"mode": mode},
        )
        self.update_timer()

    def exit_timer_session(self) -> None:
        """종료: 지금까지 기록 저장 후 타이머 초기화."""
        if not self.running:
            return
        reply = QMessageBox.question(
            self,
            "종료 확인",
            "타이머를 종료하시겠습니까?\n지금까지의 기록은 저장됩니다.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._force_stop_timer()

    def cancel_timer_session(self) -> None:
        """내부 사용 전용 (확인 팝업 포함 취소)."""
        if not self.running:
            return
        reply = QMessageBox.question(
            self,
            "취소 확인",
            "타이머를 취소하시겠습니까?\n취소 시 현재 세션의 기록이 삭제됩니다.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._force_cancel_timer()

    def _force_cancel_timer(self) -> None:
        if not self.running:
            return
        self.log_event(
            "timer_cancelled",
            todo_id=self.running["todo_id"],
            subject_id=self.running["subject_id"],
            block_key=self.running["block_key"],
            metadata={"mode": self.running["mode"]},
        )
        self.tick.stop()
        self.store.delete_timer_records_by_memo(self.running["session_id"])
        self._db_segments_dirty = True
        self.running = None
        self.pause_button.setText("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.repolish(self.pause_button)
        self.update_timer()
        self.refresh_stats()
        self.refresh_timer_visual()

    def complete_timer_session(self) -> None:
        """완료: 기록 저장 + 할 일 완료 처리."""
        if not self.running:
            if self.selected_todo_id:
                todo = self.todo_lookup.get(self.selected_todo_id)
                self.store.set_todo_status(self.selected_todo_id, "done")
                self.log_event(
                    "todo_completed",
                    todo_id=self.selected_todo_id,
                    subject_id=todo.subject_id if todo else None,
                )
                self.refresh_todos()
            return
        self._force_stop_timer()
        if self.selected_todo_id:
            todo = self.todo_lookup.get(self.selected_todo_id)
            self.store.set_todo_status(self.selected_todo_id, "done")
            self.log_event(
                "todo_completed",
                todo_id=self.selected_todo_id,
                subject_id=todo.subject_id if todo else None,
            )
        self.refresh_all()

    def _force_stop_timer(self) -> None:
        if not self.running:
            return
        self.log_event(
            "timer_stopped",
            todo_id=self.running["todo_id"],
            subject_id=self.running["subject_id"],
            block_key=self.running["block_key"],
            metadata={"mode": self.running["mode"]},
        )
        if self.running["mode"] in {"focus", "break", "long_break", "paused"}:
            self.finish_current_timer_segment()
        self.tick.stop()
        todo_id = self.running["todo_id"]
        self.running = None
        self.selected_todo_id = todo_id
        self.pause_button.setText("실행")
        self.pause_button.setObjectName("PrimaryButton")
        self.repolish(self.pause_button)
        self.update_timer()
        self.refresh_stats()
        self.refresh_timer_visual()

    # ── 앱 공통 ───────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self.running:
            self._force_stop_timer()
        event.accept()

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        if obj is self.todo_list.viewport() and event.type() == QEvent.MouseButtonDblClick:
            if event.button() == Qt.LeftButton:
                item = self.todo_list.itemAt(event.position().toPoint())
                if item:
                    self.open_todo_edit_dialog(item)
            return True
        return super().eventFilter(obj, event)

    def repolish(self, widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def log_event(
        self,
        event_type: str,
        todo_id: int | None = None,
        subject_id: int | None = None,
        block_key: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        try:
            self.store.add_event_log(self.day, event_type, todo_id, subject_id, block_key, metadata)
        except Exception:
            pass

    def save_brain_dump(self) -> None:
        if hasattr(self, "brain_dump"):
            self.store.save_brain_dump(self.day, self.brain_dump.toPlainText())

    @staticmethod
    def block_start_minutes(block_key: str) -> int:
        hour, minute = map(int, block_key.split(":"))
        return hour * 60 + minute

    @staticmethod
    def block_end_label(block_key: str) -> str:
        total = MainWindow.block_start_minutes(block_key) + 10
        hour, minute = divmod(total, 60)
        return f"{hour:02d}:{minute:02d}"

    def summarize_todo_ranges(self, todo_id: int, blocks: dict[str, int]) -> str:
        keys = [key for key in ALL_BLOCK_KEYS if blocks.get(key) == todo_id]
        if not keys:
            return "계획 구간 없음"

        ranges = []
        start = keys[0]
        previous = keys[0]
        previous_idx = BLOCK_KEY_INDEX[previous]

        for key in keys[1:]:
            idx = BLOCK_KEY_INDEX[key]
            if idx == previous_idx + 1:
                previous = key
                previous_idx = idx
                continue
            ranges.append(f"{start}~{self.block_end_label(previous)}")
            start = previous = key
            previous_idx = idx

        ranges.append(f"{start}~{self.block_end_label(previous)}")
        return ", ".join(ranges)

    def current_prompt_context(self) -> dict:
        now = datetime.now()
        current_block_key = f"{now.hour:02d}:{(now.minute // 10) * 10:02d}"
        blocks = self.store.blocks_for_day(self.day)
        todos = {todo.id: todo for todo in self.store.todos_for_day(self.day)}
        records = self.store.timer_records_for_day(self.day)

        current_todo_id = self.running["todo_id"] if self.running else blocks.get(current_block_key)
        current_todo = todos.get(current_todo_id) if current_todo_id else None

        planned_minutes = 0
        actual_focus_seconds = 0
        planned_ranges = "계획 구간 없음"
        current_task = "현재 시간에 배치된 작업 없음"

        if current_todo:
            planned_minutes = sum(1 for todo_id in blocks.values() if todo_id == current_todo.id) * 10
            planned_ranges = self.summarize_todo_ranges(current_todo.id, blocks)
            current_task = f"{current_todo.subject_name} / {current_todo.title}"
            actual_focus_seconds = sum(
                int(record["seconds"] or 0)
                for record in records
                if record["todo_id"] == current_todo.id and record["event_type"] == "focus"
            )

        if self.running and self.running.get("mode") == "focus" and self.running.get("segment_started_at"):
            actual_focus_seconds += max(0, int(time.time() - self.running["segment_started_at"]))

        current_minutes = self.block_start_minutes(current_block_key)
        remaining_block_keys = [key for key in ALL_BLOCK_KEYS if self.block_start_minutes(key) >= current_minutes]
        remaining_planned_blocks = [key for key in remaining_block_keys if blocks.get(key)]
        remaining_empty_blocks = [key for key in remaining_block_keys if not blocks.get(key)]
        protected_blocks = [
            key
            for key in remaining_block_keys
            if blocks.get(key) and self.store.block_has_timer_records(self.day, key)
        ]

        remaining_open_todos = []
        for todo in todos.values():
            if todo.status == "done":
                continue
            todo_planned_after_now = sum(
                1
                for key in remaining_block_keys
                if blocks.get(key) == todo.id
            ) * 10
            remaining_open_todos.append(f"{todo.subject_name} / {todo.title} ({todo.status}, 이후 계획 {todo_planned_after_now}분)")

        editable_start = self.block_end_label(current_block_key) if now.minute % 10 or now.second else current_block_key
        editable_range = f"{editable_start} 이후, 실제 타이머 기록이 없는 블록"
        actual_focus_minutes = round(actual_focus_seconds / 60)

        return {
            "now": now.strftime("%Y-%m-%d %H:%M"),
            "current_block_key": current_block_key,
            "timer_mode": self.running["mode"] if self.running else "실행 중 아님",
            "current_task": current_task,
            "current_task_planned_ranges": planned_ranges,
            "current_task_planned_minutes": planned_minutes,
            "current_task_actual_focus_minutes": actual_focus_minutes,
            "current_task_delta_minutes": actual_focus_minutes - planned_minutes,
            "editable_range": editable_range,
            "remaining_planned_minutes": len(remaining_planned_blocks) * 10,
            "remaining_empty_minutes": len(remaining_empty_blocks) * 10,
            "remaining_open_todos": "; ".join(remaining_open_todos) if remaining_open_todos else "미완료 To Do 없음",
            "protected_blocks": ", ".join(protected_blocks[:20]),
        }

    def ensure_openai_api_key(self) -> bool:
        if self.ai.is_configured():
            return True

        api_key, ok = QInputDialog.getText(
            self,
            "AI API 키",
            "AI 재조정을 실행할 API 키를 입력하세요.\n\n"
            "지원 API:\n"
            "- OpenAI (sk-...)\n"
            "- Gemini (AIza...)\n"
            "- Hugging Face (hf_...)\n\n"
            "키는 이 PC의 앱 설정 DB에 저장됩니다.",
            QLineEdit.Password,
        )

        if not ok or not api_key.strip():
            return False

        api_key = api_key.strip()
        self.store.set_setting("openai_api_key", api_key)
        self.ai.set_api_key(api_key)
        return True

    def realistic_schedule_context(self) -> dict:
        now = datetime.now()
        current_block_key = f"{now.hour:02d}:{(now.minute // 10) * 10:02d}"
        current_minutes = self.block_start_minutes(current_block_key)
        editable_start_minutes = current_minutes
        if now.minute % 10 or now.second:
            editable_start_minutes += 10

        todos = self.store.todos_for_day(self.day)
        blocks = self.store.blocks_for_day(self.day)
        records = self.store.timer_records_for_day(self.day)
        protected_block_keys = [
            key
            for key in ALL_BLOCK_KEYS
            if self.block_start_minutes(key) >= editable_start_minutes
            and self.store.block_has_timer_records(self.day, key)
        ]
        editable_block_keys = [
            key
            for key in ALL_BLOCK_KEYS
            if self.block_start_minutes(key) >= editable_start_minutes
            and key not in protected_block_keys
        ]

        days = self.store.activity_days(limit=14)
        if self.day not in days:
            days.insert(0, self.day)
        events = self.store.event_logs_for_days(days)
        events_by_day = defaultdict(list)
        for event in events:
            events_by_day[event["day"]].append(event)

        recent_days = []
        for day in days:
            day_records = self.store.timer_records_for_day(day)
            day_events = events_by_day.get(day, [])
            recent_days.append(
                {
                    "day": day,
                    "timer": self.summarize_timer_records(day_records),
                    "events": self.summarize_events(day_events),
                    "todo_status": self.summarize_todo_status(self.store.todos_for_day(day)),
                    "planned_minutes": len(self.store.blocks_for_day(day)) * 10,
                }
            )

        return {
            "day": self.day,
            "now": now.strftime("%Y-%m-%d %H:%M"),
            "current_block_key": current_block_key,
            "editable_block_keys": editable_block_keys,
            "protected_block_keys": protected_block_keys,
            "rules": [
                "현재 시간 이전 블록은 수정하지 않는다.",
                "protected_block_keys는 수정하지 않는다.",
                "todo_id 0은 휴식, 완충, 비워두기를 의미한다.",
                "최근 실제 집중 패턴상 불가능하면 일부 작업만 배치한다.",
                "같은 어려운 작업을 무리하게 길게 이어 붙이지 않는다.",
            ],
            "todos": [
                {
                    "id": todo.id,
                    "title": todo.title,
                    "subject": todo.subject_name,
                    "status": todo.status,
                    "planned_after_now_minutes": sum(
                        10 for key in editable_block_keys if blocks.get(key) == todo.id
                    ),
                }
                for todo in todos
            ],
            "current_blocks": [
                {
                    "block_key": key,
                    "todo_id": blocks.get(key, 0),
                    "editable": key in editable_block_keys,
                    "protected": key in protected_block_keys,
                }
                for key in ALL_BLOCK_KEYS
                if blocks.get(key) or key in editable_block_keys or key in protected_block_keys
            ],
            "today_timer": self.summarize_timer_records(records),
            "today_events": self.summarize_events(events_by_day.get(self.day, [])),
            "brain_dump": self.store.brain_dump(self.day),
            "recent_days": recent_days,
        }

    def summarize_timer_records(self, records: list[dict]) -> dict:
        by_type = defaultdict(int)
        by_todo = defaultdict(int)
        by_subject = defaultdict(int)
        for record in records:
            seconds = int(record.get("seconds") or 0)
            event_type = record.get("event_type") or "unknown"
            by_type[event_type] += seconds
            if event_type == "focus":
                by_todo[str(record.get("todo_id"))] += seconds
                by_subject[record.get("subject_name") or "unknown"] += seconds
        return {
            "minutes_by_type": {key: round(value / 60) for key, value in by_type.items()},
            "focus_minutes_by_todo_id": {key: round(value / 60) for key, value in by_todo.items()},
            "focus_minutes_by_subject": {key: round(value / 60) for key, value in by_subject.items()},
        }

    def summarize_events(self, events: list[dict]) -> dict:
        counts = defaultdict(int)
        for event in events:
            counts[event.get("event_type") or "unknown"] += 1
        return dict(counts)

    def summarize_todo_status(self, todos: list) -> dict:
        counts = defaultdict(int)
        for todo in todos:
            counts[todo.status] += 1
        return dict(counts)

    def change_date(self, qdate: QDate) -> None:
        if self.running:
            self._force_stop_timer()
        previous_day = self.day
        self.day = qdate.toString("yyyy-MM-dd")
        self.selected_todo_id = None
        self.pomodoro_history = []
        self._db_segments_dirty = True
        self.log_event("date_changed", metadata={"from": previous_day, "to": self.day})
        self.update_date_button()
        self.set_selected_block(None)
        self.refresh_all()

    def open_date_dialog(self) -> None:
        dialog = DateDialog(QDate.fromString(self.day, "yyyy-MM-dd"), self, self._is_dark_mode())
        if dialog.exec() == DateDialog.Accepted:
            self.change_date(dialog.selected_date())

    def update_date_button(self) -> None:
        if hasattr(self, "date_button"):
            self.date_button.setText(QDate.fromString(self.day, "yyyy-MM-dd").toString("yyyy-MM-dd"))

    def open_subjects(self) -> None:
        SubjectDialog(self.store, self).exec()
        self.refresh_subjects()
        self.refresh_todos()
        self.refresh_blocks()

    def center_current_time_in_plan(self) -> None:
        self.refresh_past_block_styles()
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

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh_all(self) -> None:
        self._db_segments_dirty = True
        self.refresh_subjects()
        self.refresh_todos()
        self.refresh_brain_dump()
        self.refresh_blocks()
        self.refresh_stats()
        self.refresh_timer_visual()
        QTimer.singleShot(0, self.center_current_time_in_plan)

    def refresh_subjects(self) -> None:
        subjects = self.store.subjects(include_other=True)
        if not subjects:
            return
        if self.selected_subject_id is None or not any(s.id == self.selected_subject_id for s in subjects):
            self.selected_subject_id = subjects[0].id

        dark = self._is_dark_mode()
        colors = SUBJECT_COLORS_DARK if dark else SUBJECT_COLORS
        color_other = SUBJECT_COLOR_OTHER_DARK if dark else SUBJECT_COLOR_OTHER

        self.subject_color_map = {}
        self.subject_color_idx_map = {}
        color_idx = 0
        for subject in subjects:
            if subject.kind == "other":
                self.subject_color_map[subject.id] = color_other
                self.subject_color_idx_map[subject.id] = -1
            else:
                self.subject_color_map[subject.id] = colors[color_idx % len(colors)]
                self.subject_color_idx_map[subject.id] = color_idx % len(colors)
                color_idx += 1

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
        meta_length = len(todo.subject_name) + len(todo.status) + 16
        if todo.planned_minutes:
            meta_length += len(str(todo.planned_minutes)) + 8
        meta_lines = max(1, meta_length // 30)
        return min(150, 52 + title_lines * 22 + meta_lines * 18)

    def create_todo_item_widget(self, todo) -> QWidget:
        color = self.subject_color_map.get(todo.subject_id, SUBJECT_COLORS[0])
        is_selected = todo.id == self.selected_todo_id

        frame = QFrame()
        frame.setObjectName("TodoItemWidget")
        frame.setAttribute(Qt.WA_TransparentForMouseEvents)
        if is_selected:
            frame.setStyleSheet(f"background-color: {color['bg']}; border-radius: 10px;")
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

        meta_text = f"{todo.subject_name} · {self.status_label(todo.status)}"
        if todo.planned_minutes:
            meta_text += f" · 계획 {todo.planned_minutes}분"
        meta = QLabel(meta_text)
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
            button.setProperty("past", self.is_block_in_past(key))
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
        button.setProperty("past", self.is_block_in_past(block_key))
        button.style().unpolish(button)
        button.style().polish(button)

    def refresh_past_block_styles(self) -> None:
        """10분 블록 경계를 넘어갈 때 과거 시간 표시(빗살무늬)를 갱신한다."""
        for key, button in self.block_buttons.items():
            is_past = self.is_block_in_past(key)
            if button.property("past") == is_past:
                continue
            button.setProperty("past", is_past)
            button.update()

    def refresh_stats(self) -> None:
        records = self.store.timer_records_for_day(self.day)
        active_total = 0

        for record in records:
            et = record["event_type"]
            if et in {"focus", "break", "long_break"}:
                active_total += record["seconds"]

        scheduled_total = sum(todo.planned_minutes for todo in self.todo_lookup.values()) * 60

        # 도넛 그래프 업데이트
        if hasattr(self, "donut_chart"):
            self.donut_chart.set_data(scheduled_total, active_total)

        def fmt(s: int) -> str:
            h, m = divmod(s // 60, 60)
            return f"{h}h {m}m" if h else f"{m}분"

        # 시간 레이블 업데이트
        if hasattr(self, "active_time_label"):
            self.active_time_label.setText(fmt(active_total) if active_total else "—")
        if hasattr(self, "focus_time_label"):
            self.focus_time_label.setText(fmt(scheduled_total) if scheduled_total else "—")


    def show_subject_stats(self) -> None:
        records = self.store.timer_records_for_day(self.day)
        todos = self.store.todos_for_day(self.day)
        dlg = SubjectStatsDialog(
            records,
            todos,
            self.subject_color_map,
            self.subject_color_idx_map,
            SUBJECT_COLORS,
            SUBJECT_COLOR_OTHER,
            self,
        )
        dlg.exec()

    def generate_report(self) -> str:
        self.log_event("report_generated")
        todos = self.store.todos_for_day(self.day)
        records = self.store.timer_records_for_day(self.day)
        notes = self.store.brain_dump(self.day)
        markdown = build_markdown_report(
            self.day,
            todos,
            records,
            notes,
        )
        path = save_markdown_report(self.day, markdown)

        days = self.store.activity_days(limit=14)
        if self.day not in days:
            days.insert(0, self.day)
        events = self.store.event_logs_for_days(days)
        events_by_day = defaultdict(list)
        for event in events:
            events_by_day[event["day"]].append(event)
        snapshots = [
            {
                "day": day,
                "todos": self.store.todos_for_day(day),
                "records": self.store.timer_records_for_day(day),
                "blocks": self.store.blocks_for_day(day),
                "notes": self.store.brain_dump(day),
                "events": events_by_day.get(day, []),
            }
            for day in days
        ]
        prompt = build_ai_coaching_prompt(self.day, snapshots, self.current_prompt_context())
        QApplication.clipboard().setText(prompt)

        QMessageBox.information(
            self,
            "직접 재조정",
            "Markdown 리포트를 생성하고, GPT 붙여넣기용 개인화 재조정 프롬프트를 복사했습니다.\n"
            f"{path}",
        )
        return markdown

    def show_schedule_adjustment_choices(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("AI 시간표 재조정")
        box.setText("시간표 재조정 방식을 선택하세요.")
        box.setInformativeText("직접 재조정은 Markdown 프롬프트를 복사하고, 자동 재조정은 OpenAI API로 바로 제안합니다.")
        manual_button = box.addButton("직접 재조정", QMessageBox.AcceptRole)
        auto_button = box.addButton("자동 재조정", QMessageBox.ActionRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked == manual_button:
            self.generate_report()
        elif clicked == auto_button:
            self.show_realistic_schedule()

    def show_realistic_schedule(self) -> None:
        self.log_event("realistic_schedule_clicked")
        if not self.ensure_openai_api_key():
            return

        context = self.realistic_schedule_context()
        if not context["editable_block_keys"]:
            QMessageBox.information(
                self,
                "시간표 현실화",
                "현재 시간 이후에 수정 가능한 블록이 없습니다.",
            )
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            proposal = self.ai.generate_realistic_schedule(context)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "시간표 현실화 실패",
                f"AI 재조정안을 만들지 못했습니다.\n\n{exc}",
            )
            return
        finally:
            QApplication.restoreOverrideCursor()

        if self.confirm_realistic_schedule(proposal):
            changed = self.apply_realistic_schedule(proposal, context)
            self.log_event("realistic_schedule_applied", metadata={"changed_blocks": changed})
            self.refresh_blocks()
            self.refresh_todos()
            self.refresh_stats()
            QMessageBox.information(
                self,
                "적용 완료",
                f"현재 시간 이후 시간표를 현실적으로 재조정했습니다.\n변경된 블록: {changed}개",
            )

    def confirm_realistic_schedule(self, proposal: dict) -> bool:
        schedule = proposal.get("schedule", [])
        preview_lines = []
        for item in schedule[:60]:
            block_key = item.get("block_key", "")
            todo_id = int(item.get("todo_id") or 0)
            label = item.get("label") or ("비워두기" if todo_id == 0 else f"todo_id={todo_id}")
            reason = item.get("reason", "")
            preview_lines.append(f"{block_key} | {label} | {reason}")
        if len(schedule) > 60:
            preview_lines.append(f"... 외 {len(schedule) - 60}개 블록")

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("시간표 현실화")
        box.setText(proposal.get("summary", "현실적으로 지킬 수 있는 시간표를 제안했습니다."))
        box.setInformativeText(proposal.get("realistic_reason", "최근 사용 패턴과 남은 시간을 기준으로 조정했습니다."))
        box.setDetailedText("\n".join(preview_lines) if preview_lines else "제안된 변경 사항이 없습니다.")
        apply_button = box.addButton("적용", QMessageBox.AcceptRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() == apply_button

    def apply_realistic_schedule(self, proposal: dict, context: dict) -> int:
        editable = set(context.get("editable_block_keys", []))
        protected = set(context.get("protected_block_keys", []))
        valid_todo_ids = {todo.id for todo in self.store.todos_for_day(self.day)}
        changed = 0

        for key in editable:
            if key not in protected:
                self.store.delete_block(self.day, key)

        for item in proposal.get("schedule", []):
            block_key = item.get("block_key")
            try:
                todo_id = int(item.get("todo_id") or 0)
            except (TypeError, ValueError):
                continue
            if block_key not in editable or block_key in protected:
                continue
            if todo_id <= 0:
                changed += 1
                continue
            if todo_id not in valid_todo_ids:
                continue
            self.store.assign_block(self.day, block_key, todo_id)
            changed += 1

        return changed

    def status_label(self, status: str) -> str:
        return {"open": "진행 전", "done": "완료", "deferred": "미룸"}.get(status, status)

    def clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
