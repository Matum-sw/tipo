from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class DateDialog(QDialog):
    def __init__(self, selected_date: QDate, parent=None):
        super().__init__(parent)
        self.setWindowTitle("날짜 선택")
        self.setModal(True)
        self.setMinimumSize(460, 430)
        self.setObjectName("DateDialog")
        self.build(selected_date)

    def build(self, selected_date: QDate) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        title = QLabel("날짜를 선택하세요")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        body = QLabel("선택한 날짜의 To Do, Time Plan, Brain Dump 기록을 불러옵니다.")
        body.setObjectName("DialogBody")
        body.setWordWrap(True)
        root.addWidget(body)

        self.calendar = QCalendarWidget()
        self.calendar.setObjectName("DateCalendar")
        self.calendar.setGridVisible(False)
        self.calendar.setSelectedDate(selected_date)
        self.calendar.activated.connect(self.accept)
        root.addWidget(self.calendar, 1)

        actions = QHBoxLayout()
        cancel_button = QPushButton("취소")
        cancel_button.clicked.connect(self.reject)
        today_button = QPushButton("오늘")
        today_button.setObjectName("GhostButton")
        today_button.clicked.connect(self.select_today)
        apply_button = QPushButton("적용")
        apply_button.setObjectName("PrimaryButton")
        apply_button.clicked.connect(self.accept)
        actions.addWidget(cancel_button)
        actions.addStretch(1)
        actions.addWidget(today_button)
        actions.addWidget(apply_button)
        root.addLayout(actions)

    def select_today(self) -> None:
        self.calendar.setSelectedDate(QDate.currentDate())

    def selected_date(self) -> QDate:
        return self.calendar.selectedDate()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.parentWidget():
            parent_rect = self.parentWidget().frameGeometry()
            self.move(parent_rect.center() - self.rect().center())
