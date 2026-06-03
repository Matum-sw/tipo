from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

DAY_MINUTES = 24 * 60


class SubjectBarChart(QWidget):
    """과목별 공부시간 수평 막대 그래프 (x축: 0~24h, y축: 과목)."""

    def __init__(self, data: list[dict], parent=None):
        """
        data: [{"name": str, "minutes": int, "color": dict}, ...]
        color: {"bg": str, "border": str, "text": str}
        """
        super().__init__(parent)
        self.data = [d for d in data if d["minutes"] > 0]
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        rows = max(len(self.data), 1)
        return QSize(560, rows * 52 + 60)

    def paintEvent(self, event) -> None:
        if not self.data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        margin_left = 120
        margin_right = 20
        margin_top = 20
        margin_bottom = 40
        row_height = 36
        row_gap = 16
        chart_w = self.width() - margin_left - margin_right

        # x축 눈금선 + 레이블 (0, 4, 8, 12, 16, 20, 24)
        tick_hours = [0, 4, 8, 12, 16, 20, 24]
        chart_h = len(self.data) * (row_height + row_gap)
        font = QFont(self.font())
        font.setPointSize(9)
        painter.setFont(font)

        for h in tick_hours:
            x = margin_left + int(chart_w * h / 24)
            painter.setPen(QColor("#e0e6f0"))
            painter.drawLine(x, margin_top, x, margin_top + chart_h)
            painter.setPen(QColor("#93a0b4"))
            painter.drawText(
                QRectF(x - 16, margin_top + chart_h + 6, 32, 18),
                Qt.AlignCenter,
                str(h),
            )

        painter.setPen(QColor("#b0b8c8"))
        painter.drawLine(margin_left, margin_top + chart_h, margin_left + chart_w, margin_top + chart_h)

        for i, item in enumerate(self.data):
            y = margin_top + i * (row_height + row_gap)
            minutes = item["minutes"]
            color = item.get("color", {})

            bar_w = int(chart_w * minutes / DAY_MINUTES)

            # 배경 회색 트랙
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#f0f4fb"))
            painter.drawRoundedRect(QRectF(margin_left, y, chart_w, row_height), 6, 6)

            # 실제 막대
            if bar_w > 0:
                bg = QColor(color.get("bg", "#eaf3ff"))
                border = QColor(color.get("border", "#b9d4ff"))
                painter.setBrush(bg)
                painter.setPen(border)
                painter.drawRoundedRect(QRectF(margin_left, y, bar_w, row_height), 6, 6)

            # 과목명 (왼쪽)
            font_label = QFont(self.font())
            font_label.setPointSize(11)
            font_label.setBold(True)
            painter.setFont(font_label)
            painter.setPen(QColor(color.get("text", "#1f5fcf")))
            painter.drawText(
                QRectF(0, y, margin_left - 8, row_height),
                Qt.AlignRight | Qt.AlignVCenter,
                item["name"],
            )

            # 시간 텍스트 (막대 오른쪽)
            h_val, m_val = divmod(minutes, 60)
            time_str = f"{h_val}h {m_val}m" if h_val else f"{m_val}m"
            font_val = QFont(self.font())
            font_val.setPointSize(9)
            painter.setFont(font_val)
            painter.setPen(QColor("#647086"))
            painter.drawText(
                QRectF(margin_left + bar_w + 4, y, 60, row_height),
                Qt.AlignLeft | Qt.AlignVCenter,
                time_str,
            )


class SubjectStatsDialog(QDialog):
    def __init__(self, records: list[dict], subject_color_map: dict, subject_color_idx_map: dict,
                 subject_colors: list, subject_color_other: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("과목별 공부시간")
        self.setModal(True)
        self.setMinimumSize(620, 400)
        self.setObjectName("SubjectDialog")

        data = self._aggregate(records, subject_color_map, subject_color_idx_map,
                               subject_colors, subject_color_other)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("과목별 공부시간")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        hint = QLabel("더블클릭으로 닫기")
        hint.setObjectName("MutedText")
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("StatsScroll")

        chart = SubjectBarChart(data)
        chart.setMinimumHeight(chart.sizeHint().height())
        scroll.setWidget(chart)
        root.addWidget(scroll, 1)

    def mouseDoubleClickEvent(self, event) -> None:
        self.accept()

    @staticmethod
    def _aggregate(records, subject_color_map, subject_color_idx_map,
                   subject_colors, subject_color_other) -> list[dict]:
        from collections import defaultdict
        totals: dict[str, int] = defaultdict(int)
        meta: dict[str, dict] = {}
        for r in records:
            if r["event_type"] != "focus":
                continue
            if r["subject_kind"] == "other":
                continue
            name = r["subject_name"]
            totals[name] += r["seconds"] // 60
            if name not in meta:
                # find color by subject_id (not in record directly; use name lookup)
                meta[name] = {"name": name, "color": {}}

        # Build color lookup by subject name
        # subject_color_map is keyed by subject_id; we need subject_id for each name
        # Build name→color from subject_color_map + subject_color_idx_map
        name_color: dict[str, dict] = {}
        for sid, color in subject_color_map.items():
            # We don't have subject name here directly; will be filled below
            pass

        # Use a simpler approach: records already carry subject_name
        # Rebuild from records
        sid_name: dict[int, str] = {}
        for r in records:
            sid = r.get("subject_id")
            if sid and sid not in sid_name:
                sid_name[sid] = r["subject_name"]

        for sid, name in sid_name.items():
            color = subject_color_map.get(sid, subject_color_other)
            name_color[name] = color

        result = []
        for name, minutes in sorted(totals.items(), key=lambda x: x[1], reverse=True):
            result.append({
                "name": name,
                "minutes": minutes,
                "color": name_color.get(name, {}),
            })
        return result
