from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class SubjectDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("학기 과목 등록")
        self.setModal(True)
        self.setMinimumSize(480, 500)
        self.setObjectName("SubjectDialog")
        self.build()
        self.refresh()

    def build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        title = QLabel("이번 학기 과목을 등록해요")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        body = QLabel("할 일과 타이머 기록은 과목에 연결됩니다. 생활 일정은 자동 생성된 '기타'에 넣을 수 있어요.")
        body.setObjectName("DialogBody")
        body.setWordWrap(True)
        root.addWidget(body)

        form = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("예: 자료구조")
        self.name_input.returnPressed.connect(self.add_subject)
        self.add_button = QPushButton("추가")
        self.add_button.setObjectName("PrimaryButton")
        self.add_button.clicked.connect(self.add_subject)
        form.addWidget(self.name_input, 1)
        form.addWidget(self.add_button)
        root.addLayout(form)

        self.list_widget = QListWidget()
        root.addWidget(self.list_widget, 1)

        actions = QHBoxLayout()
        self.delete_button = QPushButton("선택 삭제")
        self.delete_button.setObjectName("DangerButton")
        self.delete_button.clicked.connect(self.delete_selected)
        self.start_button = QPushButton("플래너 시작")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.accept_if_ready)
        actions.addWidget(self.delete_button)
        actions.addStretch(1)
        actions.addWidget(self.start_button)
        root.addLayout(actions)

    def refresh(self) -> None:
        self.list_widget.clear()
        for subject in self.store.subjects(include_other=False):
            self.list_widget.addItem(subject.name)

    def add_subject(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            return
        self.store.add_subject(name)
        self.name_input.clear()
        self.refresh()

    def delete_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        subjects = self.store.subjects(include_other=False)
        if row >= len(subjects):
            return
        subject = subjects[row]
        todos = self.store.todos_for_subject(subject.id)
        if todos:
            msg = (
                f"'{subject.name}' 과목에 할 일이 {len(todos)}개 있습니다.\n"
                "과목을 삭제하면 연결된 모든 할 일과 타이머 기록도 함께 삭제됩니다.\n"
                "계속하시겠습니까?"
            )
        else:
            msg = f"'{subject.name}' 과목을 삭제하시겠습니까?"
        reply = QMessageBox.question(self, "과목 삭제", msg, QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        self.store.delete_subject(subject.id)
        self.refresh()

    def accept_if_ready(self) -> None:
        if self.store.has_real_subjects():
            self.accept()
        else:
            self.name_input.setFocus(Qt.OtherFocusReason)
