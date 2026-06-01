from datetime import datetime

from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtCore import QPoint, Qt, QRectF, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QWidget,
    QVBoxLayout,
)


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(77, 95, 133, 28))
        self.setGraphicsEffect(shadow)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(22, 20, 22, 20)
        self.layout.setSpacing(14)

        if title:
            heading = QLabel(title)
            heading.setObjectName("CardTitle")
            self.layout.addWidget(heading)
        if subtitle:
            caption = QLabel(subtitle)
            caption.setObjectName("CardSubtitle")
            caption.setWordWrap(True)
            self.layout.addWidget(caption)


class Pill(QLabel):
    def __init__(self, text: str, tone: str = "blue", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setMinimumHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setProperty("tone", tone)
        self.setObjectName("Pill")


class TimelineHeader(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TimelineHeader")
        self.setMinimumHeight(30)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 17, -2, -6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#e8f1ff"))
        painter.drawRoundedRect(QRectF(rect), 5, 5)

        font = QFont(self.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        for minute in range(0, 61, 10):
            x = rect.left() + (rect.width() * minute / 60)
            painter.setPen(QPen(QColor("#b6c7df"), 1))
            painter.drawLine(int(x), rect.top() - 4, int(x), rect.bottom())
            painter.setPen(QColor("#93a0b4"))
            label = f"{minute:02d}"
            painter.drawText(QRectF(x - 16, 0, 32, 16), Qt.AlignCenter, label)


class TimeGridWidget(QWidget):
    def __init__(self, day_provider, parent=None):
        super().__init__(parent)
        self.day_provider = day_provider
        self.block_buttons = {}
        self.timer_segments = []
        self.overlay = TimeMarkerOverlay(self)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.overlay.raise_()

        self.marker_timer = QTimer(self)
        self.marker_timer.timeout.connect(self.overlay.update)
        self.marker_timer.start(1000)

    def set_block_buttons(self, block_buttons: dict) -> None:
        self.block_buttons = block_buttons
        self.overlay.update()

    def set_timer_segments(self, segments: list[dict]) -> None:
        self.timer_segments = segments
        self.overlay.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()

    def is_today(self) -> bool:
        return self.day_provider() == datetime.now().date().isoformat()


class TimeMarkerOverlay(QWidget):
    def paintEvent(self, event) -> None:
        grid = self.parent()
        if not grid or not grid.is_today():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self.draw_timer_segments(painter, grid)

        now = datetime.now()
        first = grid.block_buttons.get(f"{now.hour:02d}:00")
        last = grid.block_buttons.get(f"{now.hour:02d}:50")
        if not first or not last:
            return

        left = first.x()
        right = last.x() + last.width()
        progress = ((now.minute * 60) + now.second) / 3600
        x = left + (right - left) * progress
        y1 = first.y()
        y2 = first.y() + first.height()

        painter.setPen(QPen(QColor("#2f7df6"), 3))
        painter.drawLine(int(x), y1, int(x), y2)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2f7df6"))
        painter.drawEllipse(QRectF(x - 5, y1 - 5, 10, 10))

        font = QFont(self.font())
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        label = now.strftime("%H:%M")
        bubble = QRectF(max(0, x - 24), max(0, y1 - 25), 48, 18)
        painter.drawRoundedRect(bubble, 8, 8)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(bubble, Qt.AlignCenter, label)

    def draw_timer_segments(self, painter: QPainter, grid: TimeGridWidget) -> None:
        for segment in grid.timer_segments:
            started = datetime.fromtimestamp(segment["start"])
            ended = datetime.fromtimestamp(segment["end"])
            if started.date().isoformat() != grid.day_provider():
                continue

            if segment["mode"] == "focus":
                color = QColor("#34c759")
            elif segment["mode"] == "break":
                color = QColor("#f5c542")
            else:
                color = QColor("#ff5b5b")
            color.setAlpha(92)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)

            first_hour = max(0, started.hour)
            last_hour = min(23, ended.hour)
            for hour in range(first_hour, last_hour + 1):
                first = grid.block_buttons.get(f"{hour:02d}:00")
                last = grid.block_buttons.get(f"{hour:02d}:50")
                if not first or not last:
                    continue

                hour_start_seconds = 0 if hour > started.hour else started.minute * 60 + started.second
                hour_end_seconds = 3600 if hour < ended.hour else ended.minute * 60 + ended.second
                if hour_end_seconds <= hour_start_seconds:
                    continue

                left = first.x()
                right = last.x() + last.width()
                x1 = left + (right - left) * (hour_start_seconds / 3600)
                x2 = left + (right - left) * (hour_end_seconds / 3600)
                rect = QRectF(x1, first.y(), max(4, x2 - x1), first.height())
                painter.drawRect(rect)


class TimeBlockButton(QPushButton):
    pressed_block = Signal(str)
    entered_block = Signal(str)
    moved_block = Signal(QPoint)
    released_block = Signal(str)

    def __init__(self, block_key: str, parent=None):
        super().__init__("", parent)
        self.block_key = block_key
        self.task_text = ""
        self.setMouseTracking(True)
        self.setObjectName("TimeBlock")
        self.setProperty("filled", False)
        self.setMinimumHeight(42)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_task_text(self, text: str) -> None:
        self.task_text = text
        self.setText("")
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        self.style().drawControl(QStyle.CE_PushButton, option, painter, self)

        if not self.task_text:
            return

        rect = self.rect().adjusted(7, 3, -7, -3)
        painter.setFont(self.scaled_font_for_text(self.task_text))
        painter.setPen(QColor(self.text_color()))
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap, self.task_text)

    def text_color(self) -> str:
        if self.property("life"):
            return "#477d37"
        if self.property("filled"):
            return "#1f5fcf"
        return "#647086"

    def scaled_font_for_text(self, text: str) -> QFont:
        font = QFont(self.font())
        compact_length = len(text.replace("\n", ""))
        line_count = max(1, text.count("\n") + 1)
        available_height = max(22, self.height() - 6)

        if not text:
            point_size = 10
        elif compact_length > 52 or line_count > 3 or available_height < 28:
            point_size = 6
        elif compact_length > 40:
            point_size = 7
        elif compact_length > 28:
            point_size = 8
        else:
            point_size = 9

        font.setPointSize(point_size)
        font.setBold(True)
        return font

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pressed_block.emit(self.block_key)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if QApplication.mouseButtons() & Qt.LeftButton:
            self.entered_block.emit(self.block_key)
        super().enterEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.moved_block.emit(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.released_block.emit(self.block_key)
        super().mouseReleaseEvent(event)
