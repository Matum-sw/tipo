# 실행 안내

간단 실행 스크립트가 `run.sh`에 들어 있습니다. 팀원과 환경 충돌 없이 실행하려면 이 스크립트를 사용하세요.

사용법:

```bash
./run.sh
```

설명:
- 스크립트는 프로젝트 루트에 `.venv`를 생성합니다.
- `requirements.txt`를 설치합니다.
- 실행 시 venv 안의 PySide6 라이브러리와 플러그인 경로를 우선시하여 conda의 Qt와 충돌하지 않도록 환경 변수를 설정합니다.

주의:
- 이미 conda 환경에서 작업 중이라면, conda의 `qt` 패키지와 충돌할 수 있으니 `venv`를 만들어 실행하는 방식이 안전합니다.
- 팀 배포 시 `environment.yml` 또는 Docker를 사용해 환경을 통일하는 것을 권장합니다.
# tipo

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

빌드 결과는 `dist/tipo.exe`에 생성됩니다.

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



## 데이터 저장

개발 실행 시 데이터는 프로젝트 내부 `data/planner.sqlite3`에 저장됩니다.

실행 시 데이터는 사용자 홈의 `.daily_time_box_planner/data/planner.sqlite3`에 저장됩니다.

## 구조

- `ui/`: PySide6 화면과 위젯
- `core/`: 경로, 리포트, AI 피드백
- `database/`: SQLite 저장소
- `styles/`: QSS 스타일
- `assets/`: 빌드에 포함되는 리소스
