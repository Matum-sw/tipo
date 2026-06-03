from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class TodoEditDialog(QDialog):
    """할 일 편집 팝업 — 과목/이름/완료 여부 수정 + 삭제."""

    def __init__(self, store, todo, subject_color_map: dict, parent=None):
        super().__init__(parent)
        self.store = store
        self.todo = todo
        self.subject_color_map = subject_color_map
        self.deleted = False
        self._new_subject_id = todo.subject_id

        self.setWindowTitle("할 일 편집")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setObjectName("SubjectDialog")
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(16)

        title = QLabel("할 일 편집")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        # 과목 선택
        subject_row = QHBoxLayout()
        subject_row.setSpacing(10)
        subj_lbl = QLabel("과목")
        subj_lbl.setFixedWidth(40)
        self.subject_button = QPushButton(self.todo.subject_name)
        self.subject_button.setObjectName("SubjectButton")
        self.subject_button.setMinimumHeight(40)
        self._subject_menu = QMenu(self)
        self.subject_button.setMenu(self._subject_menu)
        self._refresh_subject_menu()
        subject_row.addWidget(subj_lbl)
        subject_row.addWidget(self.subject_button, 1)
        root.addLayout(subject_row)

        # 이름
        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        name_lbl = QLabel("이름")
        name_lbl.setFixedWidth(40)
        self.title_input = QLineEdit(self.todo.title)
        self.title_input.setMinimumHeight(40)
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.title_input, 1)
        root.addLayout(name_row)

        # 완료 상태 토글
        self._status = self.todo.status
        self.status_button = QPushButton(self._status_label())
        self.status_button.setObjectName(self._status_obj_name())
        self.status_button.clicked.connect(self._toggle_status)
        root.addWidget(self.status_button)

        root.addSpacing(8)

        # 하단: 삭제 / 취소·저장
        actions = QHBoxLayout()
        delete_btn = QPushButton("삭제")
        delete_btn.setObjectName("DangerButton")
        delete_btn.clicked.connect(self._delete)
        cancel_btn = QPushButton("취소")
        cancel_btn.setObjectName("GhostButton")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save)
        actions.addWidget(delete_btn)
        actions.addStretch(1)
        actions.addWidget(cancel_btn)
        actions.addWidget(save_btn)
        root.addLayout(actions)

    def _refresh_subject_menu(self) -> None:
        self._subject_menu.clear()
        subjects = self.store.subjects(include_other=True)
        for s in subjects:
            action = self._subject_menu.addAction(s.name)
            action.setCheckable(True)
            action.setChecked(s.id == self._new_subject_id)
            action.triggered.connect(lambda _=False, sid=s.id, sname=s.name: self._select_subject(sid, sname))

    def _select_subject(self, subject_id: int, name: str) -> None:
        self._new_subject_id = subject_id
        self.subject_button.setText(name)
        color = self.subject_color_map.get(subject_id, {})
        if color:
            self.subject_button.setStyleSheet(
                f"background-color: {color['bg']}; border: 1px solid {color['border']}; color: {color['text']};"
            )
        self._refresh_subject_menu()

    def _status_label(self) -> str:
        return "✓ 완료됨  (클릭하여 미완료)" if self._status == "done" else "○ 미완료  (클릭하여 완료)"

    def _status_obj_name(self) -> str:
        return "CompleteButton" if self._status == "done" else "SoftButton"

    def _toggle_status(self) -> None:
        self._status = "open" if self._status == "done" else "done"
        self.status_button.setText(self._status_label())
        self.status_button.setObjectName(self._status_obj_name())
        self.status_button.style().unpolish(self.status_button)
        self.status_button.style().polish(self.status_button)

    def _save(self) -> None:
        new_title = self.title_input.text().strip()
        if not new_title:
            self.title_input.setFocus()
            return
        # 이름 변경
        if new_title != self.todo.title or self._new_subject_id != self.todo.subject_id:
            self.store.connection.execute(
                "UPDATE todos SET title = ?, subject_id = ? WHERE id = ?",
                (new_title, self._new_subject_id, self.todo.id),
            )
            self.store.connection.commit()
        # 상태 변경
        if self._status != self.todo.status:
            self.store.set_todo_status(self.todo.id, self._status)
        self.accept()

    def _delete(self) -> None:
        reply = QMessageBox.question(
            self, "할 일 삭제",
            f"'{self.todo.title}'을(를) 삭제하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.deleted = True
        self.accept()
