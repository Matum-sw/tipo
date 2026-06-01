# Daily Time Box Planner

PySide6 기반 데일리 타임박싱 플래너입니다.

## 실행

```bash
pip install -r requirements.txt
python app.py
```

## Windows exe 빌드

```bash
python -m PyInstaller planner.spec --noconfirm
```

빌드 결과는 `dist/DailyTimeBoxPlanner.exe`에 생성됩니다.

## 주요 기능

- 과목별 To Do 등록
- 날짜별 Brain Dump 저장
- Time Plan 블록에 To Do 배치
- 현재 시간에 걸쳐 있는 Time Plan 테스크를 자동으로 찾아 뽀모도로 타이머 실행
- 25분 집중 후 알람/팝업, 확인 후 5분 휴식 시작
- 팝업 확인 전까지 초과된 집중/휴식 시간까지 실제 기록
- 완료된 To Do에 초록 체크 표시
- Study Stats에 집중 시간 집계
- Markdown 리포트 생성
- OpenAI API 기반 피드백

## 알람 사운드

알람 사운드는 아래 경로에 WAV 파일을 넣으면 재생됩니다.

```text
assets/alarm.wav
```

파일이 없으면 알람 재생만 건너뛰고 팝업은 정상 표시됩니다.

## 데이터 저장

개발 실행 시 데이터는 프로젝트 내부 `data/planner.sqlite3`에 저장됩니다.

Windows exe 실행 시 데이터는 사용자 홈의 `.daily_time_box_planner/data/planner.sqlite3`에 저장됩니다.

## 구조

- `ui/`: PySide6 화면과 위젯
- `core/`: 경로, 리포트, AI 피드백
- `database/`: SQLite 저장소
- `styles/`: QSS 스타일
- `assets/`: 빌드에 포함되는 리소스
