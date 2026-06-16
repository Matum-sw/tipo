from datetime import datetime

from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtCore import QPoint, QPointF, Qt, QRectF, Signal, QTimer
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
    """일정 지정 시간(하늘색) 대비 타이머 작동 시간(파란색) 도넛 그래프 (배경=24시간 회색)."""

    DAY_SECONDS = 86400

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scheduled_seconds = 0
        self.active_seconds = 0
        self.setMinimumSize(140, 140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, scheduled_seconds: int, active_seconds: int) -> None:
        self.scheduled_seconds = max(0, scheduled_seconds)
        self.active_seconds = max(0, active_seconds)
        self.update()

    def _is_dark(self) -> bool:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            return False
        ss = app.styleSheet()
        return "#141927" in ss or "#1a2030" in ss

    def paintEvent(self, event) -> None:
        dark = self._is_dark()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        size = min(self.width(), self.height()) - 4
        cx = self.width() / 2
        cy = self.height() / 2
        ring = size * 0.18
        r = (size - ring) / 2

        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        pen = QPen()
        pen.setWidthF(ring)
        pen.setCapStyle(Qt.FlatCap)

        # 1. 회색 배경 (24시간)
        pen.setColor(QColor("#2a3650" if dark else "#e4e9f2"))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # 2. 일정을 지정한 시간 (하늘색)
        scheduled_angle = min(360, int(self.scheduled_seconds / self.DAY_SECONDS * 360))
        if scheduled_angle > 0:
            pen.setColor(QColor("#3a78c8" if dark else "#93c5fd"))
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -scheduled_angle * 16)

        # 3. 실제 타이머를 작동한 시간 (일정 범위 내에서 하늘색을 채워나감)
        active_in_schedule = min(self.active_seconds, self.scheduled_seconds)
        active_angle = min(360, int(active_in_schedule / self.DAY_SECONDS * 360))
        if active_angle > 0:
            pen.setColor(QColor("#5a9aff" if dark else "#3f7df1"))
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -active_angle * 16)

        # 4. 중앙 텍스트 — 일정 지정 시간 대비 타이머 작동시간 비율(%)
        percent = int(round(active_in_schedule / self.scheduled_seconds * 100)) if self.scheduled_seconds else 0
        line1 = f"{percent}%"
        active_min = active_in_schedule // 60
        scheduled_min = self.scheduled_seconds // 60
        line2 = f"{active_min}/{scheduled_min}분"

        font1 = QFont(self.font())
        font1.setPointSize(11)
        font1.setBold(True)
        painter.setFont(font1)
        painter.setPen(QColor("#e8edf8" if dark else "#1d2738"))
        painter.drawText(QRectF(cx - r, cy - r * 0.5, r * 2, r * 0.9), Qt.AlignCenter, line1)

        font2 = QFont(self.font())
        font2.setPointSize(8)
        painter.setFont(font2)
        painter.setPen(QColor("#7a8799" if dark else "#738095"))
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

    def _is_dark(self) -> bool:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            return False
        ss = app.styleSheet()
        return "#141927" in ss or "#1a2030" in ss

    def paintEvent(self, event) -> None:
        dark = self._is_dark()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 17, -2, -6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#1e2840" if dark else "#e8f1ff"))
        painter.drawRoundedRect(QRectF(rect), 5, 5)

        font = QFont(self.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        tick_color = QColor("#3a5080" if dark else "#b6c7df")
        label_color = QColor("#5a6880" if dark else "#93a0b4")
        for minute in range(0, 61, 10):
            x = rect.left() + (rect.width() * minute / 60)
            painter.setPen(QPen(tick_color, 1))
            painter.drawLine(int(x), rect.top() - 4, int(x), rect.bottom())
            painter.setPen(label_color)
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
    MARKER_WIDTH = 1.5
    MARKER_DOT_SIZE = 10

    def _is_dark(self) -> bool:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            return False
        ss = app.styleSheet()
        return "#141927" in ss or "#1a2030" in ss

    def _hour_geometry(self, grid: TimeGridWidget, hour: int):
        first = grid.block_buttons.get(f"{hour:02d}:00")
        last = grid.block_buttons.get(f"{hour:02d}:50")
        if not first or not last:
            return None
        return first, first.x(), last.x() + last.width()

    @staticmethod
    def _x_for_seconds(left: int, right: int, seconds: int) -> float:
        return left + (right - left) * (seconds / 3600)

    def _marker_geometry(self, grid: TimeGridWidget, now: datetime):
        geometry = self._hour_geometry(grid, now.hour)
        if not geometry:
            return None
        first, left, right = geometry
        seconds = now.minute * 60 + now.second
        marker_x = round(self._x_for_seconds(left, right, seconds))
        return marker_x, first.y(), first.y() + first.height()

    def paintEvent(self, event) -> None:
        grid = self.parent()
        if not grid:
            return

        dark = self._is_dark()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        now = datetime.now()
        self.draw_timer_segments(painter, grid, now)
        painter.setRenderHint(QPainter.Antialiasing)

        if not grid.is_today():
            return

        marker = self._marker_geometry(grid, now)
        if not marker:
            return
        marker_x, y1, y2 = marker

        line_color = QColor("#5a9aff" if dark else "#2f7df6")
        pen = QPen(line_color)
        pen.setWidthF(self.MARKER_WIDTH)
        painter.setPen(pen)
        painter.drawLine(QPointF(marker_x, y1), QPointF(marker_x, y2))

        painter.setPen(Qt.NoPen)
        painter.setBrush(line_color)
        dot_offset = self.MARKER_DOT_SIZE / 2
        painter.drawEllipse(QRectF(marker_x - dot_offset, y1 - dot_offset, self.MARKER_DOT_SIZE, self.MARKER_DOT_SIZE))

        font = QFont(self.font())
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        label = now.strftime("%H:%M")
        bubble = QRectF(max(0, marker_x - 20), max(0, y1 - 22), 40, 16)
        painter.drawRoundedRect(bubble, 7, 7)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(bubble, Qt.AlignCenter, label)

    def draw_timer_segments(self, painter: QPainter, grid: TimeGridWidget, now: datetime) -> None:
        now_ts = now.timestamp()
        marker = self._marker_geometry(grid, now) if grid.is_today() else None
        marker_x = marker[0] if marker else None
        painter.setRenderHint(QPainter.Antialiasing, False)

        for segment in grid.timer_segments:
            start_ts = segment["start"]
            end_ts = segment["end"]
            is_current_segment = grid.is_today() and start_ts <= now_ts <= end_ts + 2
            if is_current_segment:
                end_ts = now_ts

            started = datetime.fromtimestamp(start_ts)
            ended = datetime.fromtimestamp(end_ts)
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
                geometry = self._hour_geometry(grid, hour)
                if not geometry:
                    continue
                first, left, right = geometry

                hour_start_seconds = 0 if hour > started.hour else started.minute * 60 + started.second
                hour_end_seconds = 3600 if hour < ended.hour else ended.minute * 60 + ended.second
                if hour_end_seconds <= hour_start_seconds:
                    continue

                x1 = self._x_for_seconds(left, right, hour_start_seconds)
                x2 = self._x_for_seconds(left, right, hour_end_seconds)
                if is_current_segment and marker_x is not None and hour == now.hour:
                    x2 = min(x2, marker_x - (self.MARKER_WIDTH / 2))
                if x2 <= x1:
                    continue
                rect = QRectF(x1, first.y(), x2 - x1, first.height())
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

        if self.property("excluded"):
            # 제외 시간으로 지정된 블록: 옅은 빨간색 + 빨간 빗살무늬
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(220, 60, 60, 40))
            painter.drawRect(self.rect())
            painter.setBrush(QBrush(QColor(200, 50, 50, 110), Qt.BDiagPattern))
            painter.drawRect(self.rect())
            painter.restore()
        elif self.property("past") and not self.property("timer_ran"):
            # 이미 지나갔지만 실제 타이머가 작동하지 않은 블록만 회색 빗살무늬로 표시한다.
            # 타이머가 작동했던 구간(오버레이) 등 기존에 강조된 부분은 덮지 않는다.
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(120, 130, 150, 70), Qt.BDiagPattern))
            painter.drawRect(self.rect())
            painter.restore()

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
