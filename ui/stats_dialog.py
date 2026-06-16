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


class SubjectBarChart(QWidget):
    """과목별 공부시간 수평 막대 그래프. 각 막대의 최대값(꽉 채운 길이)은
    해당 과목의 TimePlan 계획 시간(scheduled_minutes)이다."""

    def __init__(self, data: list[dict], parent=None):
        """
        data: [{"name": str, "minutes": int, "scheduled_minutes": int, "color": dict}, ...]
        color: {"bg": str, "border": str, "text": str}
        """
        super().__init__(parent)
        self.data = [d for d in data if d["minutes"] > 0 or d["scheduled_minutes"] > 0]
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        rows = max(len(self.data), 1)
        return QSize(560, rows * 52 + 60)

    @staticmethod
    def _fmt_minutes(minutes: int) -> str:
        h_val, m_val = divmod(minutes, 60)
        return f"{h_val}h {m_val}m" if h_val else f"{m_val}m"

    def paintEvent(self, event) -> None:
        if not self.data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        margin_left = 120
        margin_right = 90
        margin_top = 20
        row_height = 36
        row_gap = 16
        chart_w = self.width() - margin_left - margin_right

        for i, item in enumerate(self.data):
            y = margin_top + i * (row_height + row_gap)
            minutes = item["minutes"]
            scheduled_minutes = item["scheduled_minutes"]
            color = item.get("color", {})

            # 막대 최대값 = 해당 과목의 TimePlan 계획 시간. 계획이 없으면 실제 시간을 기준으로 꽉 채움.
            max_minutes = scheduled_minutes if scheduled_minutes > 0 else max(minutes, 1)
            bar_w = int(chart_w * min(minutes, max_minutes) / max_minutes)

            # 배경 회색 트랙 (= 계획 시간 전체)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#f0f4fb"))
            painter.drawRoundedRect(QRectF(margin_left, y, chart_w, row_height), 6, 6)

            # 실제 막대 (= 실제 공부 시간)
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

            # 시간 텍스트 (막대 오른쪽) — 실제/계획
            time_str = f"{self._fmt_minutes(minutes)} / {self._fmt_minutes(scheduled_minutes)}"
            font_val = QFont(self.font())
            font_val.setPointSize(9)
            painter.setFont(font_val)
            painter.setPen(QColor("#647086"))
            painter.drawText(
                QRectF(margin_left + chart_w + 4, y, margin_right - 4, row_height),
                Qt.AlignLeft | Qt.AlignVCenter,
                time_str,
            )


class SubjectStatsDialog(QDialog):
    def __init__(self, records: list[dict], todos: list, subject_color_map: dict, subject_color_idx_map: dict,
                 subject_colors: list, subject_color_other: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("과목별 공부시간")
        self.setModal(True)
        self.setMinimumSize(620, 400)
        self.setObjectName("SubjectDialog")

        data = self._aggregate(records, todos, subject_color_map, subject_color_idx_map,
                               subject_colors, subject_color_other)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("과목별 공부시간")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("StatsScroll")

        chart = SubjectBarChart(data)
        chart.setMinimumHeight(chart.sizeHint().height())
        scroll.setWidget(chart)
        root.addWidget(scroll, 1)

    @staticmethod
    def _aggregate(records, todos, subject_color_map, subject_color_idx_map,
                   subject_colors, subject_color_other) -> list[dict]:
        from collections import defaultdict

        totals: dict[str, int] = defaultdict(int)
        scheduled: dict[str, int] = defaultdict(int)
        sid_name: dict[int, str] = {}

        for r in records:
            sid = r.get("subject_id")
            if sid and sid not in sid_name:
                sid_name[sid] = r["subject_name"]
            if r["event_type"] != "focus" or r["subject_kind"] == "other":
                continue
            totals[r["subject_name"]] += r["seconds"] // 60

        for todo in todos:
            if todo.subject_kind == "other":
                continue
            sid_name.setdefault(todo.subject_id, todo.subject_name)
            scheduled[todo.subject_name] += todo.planned_minutes

        name_color: dict[str, dict] = {
            name: subject_color_map.get(sid, subject_color_other)
            for sid, name in sid_name.items()
        }

        names = sorted(set(totals) | set(scheduled))
        result = []
        for name in names:
            result.append({
                "name": name,
                "minutes": totals.get(name, 0),
                "scheduled_minutes": scheduled.get(name, 0),
                "color": name_color.get(name, {}),
            })
        result.sort(key=lambda item: item["minutes"], reverse=True)
        return result
