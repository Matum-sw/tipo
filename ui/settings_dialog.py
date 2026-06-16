from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


SETTING_DEFAULTS = {
    "focus_minutes": 25,
    "break_minutes": 5,
    "long_break_minutes": 15,
    "sprint_count": 4,
    "alarm_volume": 80,
    "dark_mode": 0,
}

# (key, label, min, max, suffix)
SPIN_FIELDS = [
    ("focus_minutes",       "집중 시간",           1, 60, " 분"),
    ("break_minutes",       "짧은 휴식",           1, 30, " 분"),
    ("long_break_minutes",  "긴 휴식 (세트 완료 후)", 1, 60, " 분"),
    ("sprint_count",        "세트당 스프린트 수",    1,  8, " 개"),
]


class SettingsDialog(QDialog):
    def __init__(self, store, day: str, on_sample_added=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.day = day
        self.on_sample_added = on_sample_added
        self.data_reset = False
        self._spins: dict[str, dict] = {}   # key → {val, min, max, suffix, label}

        self.setWindowTitle("설정")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setObjectName("SubjectDialog")
        self._build()
        self._load()

    # ── 빌드 ─────────────────────────────────────────────────────────────────

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

        # +/- 스피너 필드
        for key, label, mn, mx, suffix in SPIN_FIELDS:
            spin_widget = self._make_spin_widget(key, mn, mx, suffix)
            form.addRow(label, spin_widget)

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

        # ── AI API 키 ────────────────────────────────────────────────────────
        api_key_row = QHBoxLayout()
        self.api_key_status_label = QLabel()
        self.api_key_status_label.setStyleSheet("font-weight: 700;")
        api_key_change_btn = QPushButton("변경")
        api_key_change_btn.setObjectName("SoftButton")
        api_key_change_btn.setStyleSheet("padding: 6px 14px; min-height: 0; border-radius: 10px;")
        api_key_change_btn.clicked.connect(self._change_api_key)
        api_key_row.addWidget(self.api_key_status_label, 1)
        api_key_row.addWidget(api_key_change_btn)
        form2 = QFormLayout()
        form2.setSpacing(14)
        form2.setLabelAlignment(Qt.AlignRight)
        form2.addRow("AI API 키", api_key_row)
        root.addLayout(form2)

        # ── 표본 추가 ────────────────────────────────────────────────────────
        sample_btn = QPushButton("표본 추가")
        sample_btn.setObjectName("SoftButton")
        sample_btn.setStyleSheet("padding: 8px 16px; min-height: 0; border-radius: 10px;")
        sample_btn.clicked.connect(self._add_sample_data)
        sample_row = QHBoxLayout()
        sample_hint = QLabel("Study Stats 등 모든 기능을 점검할 수 있는 표본 데이터를 추가합니다")
        sample_hint.setObjectName("MutedText")
        sample_hint.setStyleSheet("font-size: 12px;")
        sample_row.addWidget(sample_hint, 1)
        sample_row.addWidget(sample_btn)
        root.addLayout(sample_row)

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

    def _make_spin_widget(self, key: str, mn: int, mx: int, suffix: str) -> QWidget:
        """−·값·+ 버튼 한 줄 위젯."""
        dark = self.store.get_setting("dark_mode", "0") == "1"

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        minus_btn = QPushButton("−")
        minus_btn.setFixedSize(36, 36)
        if dark:
            minus_btn.setStyleSheet(
                "QPushButton { background:#3a1010; color:#ff7070; border:1.5px solid #602020;"
                " border-radius:10px; font-size:18px; font-weight:900; min-height:0; padding:0; }"
                "QPushButton:hover { background:#501818; }"
            )
        else:
            minus_btn.setStyleSheet(
                "QPushButton { background:#f5e0e0; color:#c0392b; border:1.5px solid #e0b0b0;"
                " border-radius:10px; font-size:18px; font-weight:900; min-height:0; padding:0; }"
                "QPushButton:hover { background:#f0c0c0; }"
            )

        val_label = QLabel(str(mn) + suffix)
        val_label.setAlignment(Qt.AlignCenter)
        val_label.setMinimumWidth(70)
        if dark:
            val_label.setStyleSheet(
                "font-size:15px; font-weight:800; color:#dde4f0;"
                " background:#1a2030; border:1.5px solid #2a3650;"
                " border-radius:10px; padding:4px 8px;"
            )
        else:
            val_label.setStyleSheet(
                "font-size:15px; font-weight:800; color:#202636;"
                " background:#f4f8ff; border:1.5px solid #dde6f4;"
                " border-radius:10px; padding:4px 8px;"
            )

        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(36, 36)
        if dark:
            plus_btn.setStyleSheet(
                "QPushButton { background:#1a2c4a; color:#7baeff; border:1.5px solid #2a4880;"
                " border-radius:10px; font-size:18px; font-weight:900; min-height:0; padding:0; }"
                "QPushButton:hover { background:#1e3a60; }"
            )
        else:
            plus_btn.setStyleSheet(
                "QPushButton { background:#dbeafe; color:#1f5fcf; border:1.5px solid #93c5fd;"
                " border-radius:10px; font-size:18px; font-weight:900; min-height:0; padding:0; }"
                "QPushButton:hover { background:#bfdbfe; }"
            )

        row.addWidget(minus_btn)
        row.addWidget(val_label, 1)
        row.addWidget(plus_btn)

        state = {"val": mn, "min": mn, "max": mx, "suffix": suffix, "label": val_label}
        self._spins[key] = state

        def _refresh():
            val_label.setText(str(state["val"]) + suffix)

        def _dec():
            if state["val"] > state["min"]:
                state["val"] -= 1
                _refresh()

        def _inc():
            if state["val"] < state["max"]:
                state["val"] += 1
                _refresh()

        minus_btn.clicked.connect(_dec)
        plus_btn.clicked.connect(_inc)
        return container

    # ── 데이터 ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        def gi(key):
            return int(self.store.get_setting(key, str(SETTING_DEFAULTS[key])))

        for key, state in self._spins.items():
            v = gi(key)
            state["val"] = v
            state["label"].setText(str(v) + state["suffix"])

        vol = gi("alarm_volume")
        self.volume_slider.setValue(vol)
        self.volume_label.setText(f"{vol} %")
        self.dark_mode_check.setChecked(gi("dark_mode") == 1)
        self._refresh_api_key_status()

    def _refresh_api_key_status(self) -> None:
        api_key = self.store.get_setting("openai_api_key", "")
        if api_key:
            self.api_key_status_label.setText("✓ 등록됨")
            self.api_key_status_label.setStyleSheet("font-weight: 700; color: #2f9e44;")
        else:
            self.api_key_status_label.setText("✗ 등록되지 않음")
            self.api_key_status_label.setStyleSheet("font-weight: 700; color: #e5484d;")

    def _change_api_key(self) -> None:
        api_key, ok = QInputDialog.getText(
            self,
            "AI API 키 변경",
            "AI 재조정에 사용할 API 키를 입력하세요.\n\n"
            "지원 API:\n"
            "- OpenAI (sk-...)\n"
            "- Gemini (AIza...)\n"
            "- Hugging Face (hf_...)\n\n"
            "키는 이 PC의 앱 설정 DB에 저장됩니다.",
            QLineEdit.Password,
        )
        if not ok:
            return
        self.store.set_setting("openai_api_key", api_key.strip())
        self._refresh_api_key_status()

    def _reset(self) -> None:
        d = SETTING_DEFAULTS
        for key, state in self._spins.items():
            v = d[key]
            state["val"] = v
            state["label"].setText(str(v) + state["suffix"])
        self.volume_slider.setValue(d["alarm_volume"])
        self.dark_mode_check.setChecked(d["dark_mode"] == 1)

    def _save(self) -> None:
        for key, state in self._spins.items():
            self.store.set_setting(key, str(state["val"]))
        self.store.set_setting("alarm_volume", str(self.volume_slider.value()))
        self.store.set_setting("dark_mode", "1" if self.dark_mode_check.isChecked() else "0")
        self.accept()

    def _add_sample_data(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("표본 추가")
        box.setText("표본을 추가하시겠습니까?")
        box.setInformativeText("Study Stats 그래프 등 모든 기능을 점검할 수 있는 표본 데이터가 오늘 날짜에 추가됩니다.")
        add_button = box.addButton("추가", QMessageBox.AcceptRole)
        box.addButton("취소", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() != add_button:
            return

        self.store.add_sample_data(self.day)
        if self.on_sample_added:
            self.on_sample_added()
        QMessageBox.information(self, "표본 추가 완료", "표본 데이터가 추가되었습니다.")

    def _reset_data(self) -> None:
        reply = QMessageBox.warning(
            self,
            "저장 정보 초기화",
            "모든 할 일, 타이머 기록, 시간 계획, Brain Dump가 영구 삭제됩니다.\n\n"
            "이 작업은 되돌릴 수 없습니다. 계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        final_reply = QMessageBox.question(
            self,
            "정말 초기화할까요?",
            "마지막 확인입니다.\n\n"
            "저장된 모든 정보가 삭제됩니다. 정말 초기화하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if final_reply == QMessageBox.Yes:
            self.data_reset = True
            self.accept()
