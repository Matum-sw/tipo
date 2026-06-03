from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)


SETTING_DEFAULTS = {
    "focus_minutes": 25,
    "break_minutes": 5,
    "long_break_minutes": 15,
    "sprint_count": 4,
    "alarm_volume": 80,
    "dark_mode": 0,
}


class SettingsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.data_reset = False
        self.setWindowTitle("설정")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setObjectName("SubjectDialog")
        self._build()
        self._load()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(20)

        title = QLabel("설정")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignRight)

        # 집중 시간
        self.focus_spin = QSpinBox()
        self.focus_spin.setRange(1, 60)
        self.focus_spin.setSuffix(" 분")
        form.addRow("집중 시간", self.focus_spin)

        # 짧은 휴식
        self.break_spin = QSpinBox()
        self.break_spin.setRange(1, 30)
        self.break_spin.setSuffix(" 분")
        form.addRow("짧은 휴식", self.break_spin)

        # 긴 휴식
        self.long_break_spin = QSpinBox()
        self.long_break_spin.setRange(1, 60)
        self.long_break_spin.setSuffix(" 분")
        form.addRow("긴 휴식 (세트 완료 후)", self.long_break_spin)

        # 스프린트 수
        self.sprint_spin = QSpinBox()
        self.sprint_spin.setRange(1, 8)
        self.sprint_spin.setSuffix(" 개")
        form.addRow("세트당 스프린트 수", self.sprint_spin)

        # 알람 볼륨
        volume_row = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_label = QLabel("80 %")
        self.volume_label.setFixedWidth(42)
        self.volume_slider.valueChanged.connect(
            lambda v: self.volume_label.setText(f"{v} %")
        )
        volume_row.addWidget(self.volume_slider)
        volume_row.addWidget(self.volume_label)
        form.addRow("알람 볼륨", volume_row)

        # 다크모드
        self.dark_mode_check = QCheckBox("다크 모드 사용")
        self.dark_mode_check.setStyleSheet("font-weight: 700;")
        form.addRow("테마", self.dark_mode_check)

        root.addLayout(form)

        # ── 저장 정보 초기화 ──────────────────────────────────────────────────
        reset_data_btn = QPushButton("저장 정보 초기화")
        reset_data_btn.setObjectName("DangerButton")
        reset_data_btn.setStyleSheet("padding: 8px 16px; min-height: 0; border-radius: 10px;")
        reset_data_btn.clicked.connect(self._reset_data)
        reset_row = QHBoxLayout()
        reset_hint = QLabel("모든 할 일·타이머·시간 계획·메모를 삭제합니다")
        reset_hint.setObjectName("MutedText")
        reset_hint.setStyleSheet("font-size: 12px;")
        reset_row.addWidget(reset_hint, 1)
        reset_row.addWidget(reset_data_btn)
        root.addLayout(reset_row)

        # ── 저장 / 기본값 버튼 ───────────────────────────────────────────────
        btns = QHBoxLayout()
        reset_btn = QPushButton("기본값으로")
        reset_btn.setObjectName("GhostButton")
        reset_btn.clicked.connect(self._reset)
        save_btn = QPushButton("저장")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self._save)
        btns.addWidget(reset_btn)
        btns.addStretch(1)
        btns.addWidget(save_btn)
        root.addLayout(btns)

    def _load(self) -> None:
        def gi(key):
            return int(self.store.get_setting(key, str(SETTING_DEFAULTS[key])))

        self.focus_spin.setValue(gi("focus_minutes"))
        self.break_spin.setValue(gi("break_minutes"))
        self.long_break_spin.setValue(gi("long_break_minutes"))
        self.sprint_spin.setValue(gi("sprint_count"))
        vol = gi("alarm_volume")
        self.volume_slider.setValue(vol)
        self.volume_label.setText(f"{vol} %")
        self.dark_mode_check.setChecked(gi("dark_mode") == 1)

    def _reset(self) -> None:
        d = SETTING_DEFAULTS
        self.focus_spin.setValue(d["focus_minutes"])
        self.break_spin.setValue(d["break_minutes"])
        self.long_break_spin.setValue(d["long_break_minutes"])
        self.sprint_spin.setValue(d["sprint_count"])
        self.volume_slider.setValue(d["alarm_volume"])
        self.dark_mode_check.setChecked(d["dark_mode"] == 1)

    def _save(self) -> None:
        self.store.set_setting("focus_minutes", str(self.focus_spin.value()))
        self.store.set_setting("break_minutes", str(self.break_spin.value()))
        self.store.set_setting("long_break_minutes", str(self.long_break_spin.value()))
        self.store.set_setting("sprint_count", str(self.sprint_spin.value()))
        self.store.set_setting("alarm_volume", str(self.volume_slider.value()))
        self.store.set_setting("dark_mode", "1" if self.dark_mode_check.isChecked() else "0")
        self.accept()

    def _reset_data(self) -> None:
        reply = QMessageBox.warning(
            self,
            "저장 정보 초기화",
            "모든 할 일, 타이머 기록, 시간 계획, Brain Dump가 영구 삭제됩니다.\n\n"
            "이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.data_reset = True
            self.accept()
