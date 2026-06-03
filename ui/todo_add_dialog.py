from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QVBoxLayout,
)


class TodoAddDialog(QDialog):
    def __init__(self, store, day: str, current_subject_id: int | None, subject_color_map: dict, parent=None):
        super().__init__(parent)
        self.store = store
        self.day = day
        self.selected_subject_id = current_subject_id
        self.subject_color_map = subject_color_map
        self.setWindowTitle("오늘 할 일 추가")
        self.setModal(True)
        self.setMinimumSize(480, 440)
        self.setObjectName("SubjectDialog")
        self._build()
        self._refresh_subjects()
        self._refresh_todos()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(16)

        title = QLabel("오늘 할 일 추가")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        body = QLabel("과목을 선택하고 할 일을 입력한 뒤 추가하세요.")
        body.setObjectName("DialogBody")
        body.setWordWrap(True)
        root.addWidget(body)

        # 과목 선택 행
        subject_row = QHBoxLayout()
        subject_row.setSpacing(10)
        subject_lbl = QLabel("과목")
        subject_lbl.setFixedWidth(36)
        self.subject_button = QPushButton("과목 선택")
        self.subject_button.setObjectName("SubjectButton")
        self.subject_button.setMinimumHeight(42)
        self.subject_menu = QMenu(self)
        self.subject_button.setMenu(self.subject_menu)
        subject_row.addWidget(subject_lbl)
        subject_row.addWidget(self.subject_button, 1)
        root.addLayout(subject_row)

        # 할 일 입력 행
        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.todo_input = QLineEdit()
        self.todo_input.setPlaceholderText("오늘 할 일 입력 후 Enter 또는 추가 클릭")
        self.todo_input.returnPressed.connect(self._add_todo)
        add_btn = QPushButton("추가")
        add_btn.setObjectName("PrimaryButton")
        add_btn.setFixedWidth(72)
        add_btn.clicked.connect(self._add_todo)
        input_row.addWidget(self.todo_input, 1)
        input_row.addWidget(add_btn)
        root.addLayout(input_row)

        # 추가된 할 일 목록
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget::item { border-radius: 8px; padding: 6px 8px; margin: 2px; }
            QListWidget::item:selected, QListWidget::item:selected:active {
                background: #dbeafe; color: #1f5fcf; border-radius: 8px;
            }
            QListWidget::item:hover { background: #f0f6ff; border-radius: 8px; }
        """)
        root.addWidget(self.list_widget, 1)

        # 하단 버튼
        actions = QHBoxLayout()
        done_btn = QPushButton("완료")
        done_btn.setObjectName("PrimaryButton")
        done_btn.clicked.connect(self.accept)
        actions.addStretch(1)
        actions.addWidget(done_btn)
        root.addLayout(actions)

    def _refresh_subjects(self) -> None:
        subjects = self.store.subjects(include_other=True)
        if not subjects:
            return

        if self.selected_subject_id is None or not any(s.id == self.selected_subject_id for s in subjects):
            self.selected_subject_id = subjects[0].id

        self.subject_menu.clear()
        selected_subj = subjects[0]
        for s in subjects:
            if s.id == self.selected_subject_id:
                selected_subj = s
            action = self.subject_menu.addAction(s.name)
            action.setCheckable(True)
            action.setChecked(s.id == self.selected_subject_id)
            action.triggered.connect(lambda _=False, sid=s.id: self._select_subject(sid))

        color = self.subject_color_map.get(selected_subj.id, {})
        self.subject_button.setText(selected_subj.name)
        if color:
            self.subject_button.setStyleSheet(
                f"background-color: {color['bg']}; border: 1px solid {color['border']}; color: {color['text']};"
            )

    def _select_subject(self, subject_id: int) -> None:
        self.selected_subject_id = subject_id
        self._refresh_subjects()

    def _add_todo(self) -> None:
        title = self.todo_input.text().strip()
        if not title or self.selected_subject_id is None:
            return
        self.store.add_todo(self.day, title, self.selected_subject_id)
        self.todo_input.clear()
        self.todo_input.setFocus()
        self._refresh_todos()

    def _refresh_todos(self) -> None:
        todos = self.store.todos_for_day(self.day)
        self.list_widget.clear()
        for t in reversed(todos):
            self.list_widget.addItem(f"{t.subject_name}  ·  {t.title}")

