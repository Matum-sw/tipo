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


class DonutChartWidget(QWidget):
    """총 공부시간 / 총 작동시간 도넛 그래프 (배경=24시간 회색)."""

    DAY_SECONDS = 86400

    def __init__(self, parent=None):
        super().__init__(parent)
        self.focus_seconds = 0
        self.active_seconds = 0
        self.setMinimumSize(140, 140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, focus_seconds: int, active_seconds: int) -> None:
        self.focus_seconds = max(0, focus_seconds)
        self.active_seconds = max(0, active_seconds)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        size = min(self.width(), self.height()) - 4
        cx = self.width() / 2
        cy = self.height() / 2
        ring = size * 0.18           # 링 두께
        r = (size - ring) / 2        # 중심~링 중간선

        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        pen = QPen()
        pen.setWidthF(ring)
        pen.setCapStyle(Qt.FlatCap)

        # 1. 회색 배경 (24시간)
        pen.setColor(QColor("#e4e9f2"))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # 2. 총 작동시간 (연한 파랑)
        active_angle = min(360, int(self.active_seconds / self.DAY_SECONDS * 360))
        if active_angle > 0:
            pen.setColor(QColor("#93c5fd"))
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -active_angle * 16)

        # 3. 총 공부시간 (진한 파랑), 위에 겹침
        focus_angle = min(360, int(self.focus_seconds / self.DAY_SECONDS * 360))
        if focus_angle > 0:
            pen.setColor(QColor("#3f7df1"))
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -focus_angle * 16)

        # 4. 중앙 텍스트 (공부시간)
        focus_min = self.focus_seconds // 60
        fh, fm = divmod(focus_min, 60)
        line1 = f"{fh}h {fm}m" if fh else f"{fm}분"
        active_min = self.active_seconds // 60
        ah, am = divmod(active_min, 60)
        line2 = f"/{ah}h {am}m" if ah else f"/{am}분"

        font1 = QFont(self.font())
        font1.setPointSize(11)
        font1.setBold(True)
        painter.setFont(font1)
        painter.setPen(QColor("#1d2738"))
        painter.drawText(QRectF(cx - r, cy - r * 0.5, r * 2, r * 0.9), Qt.AlignCenter, line1)

        font2 = QFont(self.font())
        font2.setPointSize(8)
        painter.setFont(font2)
        painter.setPen(QColor("#738095"))
        painter.drawText(QRectF(cx - r, cy + r * 0.05, r * 2, r * 0.7), Qt.AlignCenter, line2)


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
        self.setMinimumHeight(38)
        self.setFixedHeight(38)
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
        if not grid:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self.draw_timer_segments(painter, grid)

        if not grid.is_today():
            return

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
            elif segment["mode"] == "long_break":
                color = QColor("#af87ff")
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
        self.subject_color = None
        self.setMouseTracking(True)
        self.setObjectName("TimeBlock")
        self.setProperty("filled", False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_task_text(self, text: str) -> None:
        self.task_text = text
        self.setText("")
        self.update()

    def set_subject_color(self, color: dict | None) -> None:
        self.subject_color = color
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
        if self.subject_color and self.property("filled"):
            return self.subject_color["text"]
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
