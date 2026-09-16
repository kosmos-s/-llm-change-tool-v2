# v2 1차 구현 보고서

## 목표와 범위

Phase 0~7의 Local-first 데스크톱 흐름을 새 코드로 구현했습니다. 사용자 승인 없이 원본을 바꾸거나 실제 API를 호출하지 않았습니다. 실제 기업 데이터는 저장소에 포함하지 않았습니다.

## 구현된 영역

프로젝트/SQLAlchemy/SQLite migration, 원본 불변 Import, versioned schema/prompt, OpenAI 및 Mock, persistent Job/Retry/Resume/recovery, Compare, 이미지 검수/이력, 3,000 Work Plan, Final Gate/JSON·JPG Export, 팀 ZIP/충돌, backup/restore, DB dashboard, Golden/모델 지표, PyInstaller/Windows CI를 연결했습니다.

아키텍처와 DB 테이블은 [architecture.md](architecture.md), 실행 방법은 [README](../README.md), 구체적 화면 순서는 [user-guide.md](user-guide.md)에 설명합니다.

폴더: `src/llm_change_tool/{core,storage,providers,ui,resources}` + `tests/`, `scripts/`, `docs/`, `.github/workflows/`. runtime 프로젝트의 데이터/DB/export/backup은 소스 폴더와 분리합니다.

## v1에서 참고한 것

- 26.03.24 guideline을 반영한 prompt_v5. 업무 규칙 본문을 사용하고 응답 envelope만 schema-driven labels로 변경했습니다.
- 엘컴텍 JSON 키 및 artifact_detail 매핑, unknown field 보존.
- core/detailed 비교 정책, 세부 인공물의 상위 라벨 관계.
- 작업 계획/실행 hash binding, 필수 검수/보류 Gate, portable 팀 교환의 목적.
- F2 계산 및 GPT 분석과 변화탐지 모델 평가의 분리.

v1 참고 기준: `kosmos-s/llm-change-auto` commit `066634c677ae5a182d781e411221d9420926561c`.

## v1에서 가져오지 않은 것

Streamlit UI, CSV 중심 상태 관리, checkpoint 파일 재개 방식, 출력 폴더를 찾아 최신 결과를 추측하는 방식은 사용하지 않았습니다. v1 앱 코드를 복제하지 않고 SQLite 관계와 immutable Run/review revision을 중심으로 다시 작성했습니다.

## 검증 상태

로컬 Python 3.12 환경에서 pytest, 실제 PySide6 offscreen GUI, 별도 QProcess 점검, Mock end-to-end를 검증합니다. CI는 Python 3.11/Linux·Windows 테스트와 Windows Portable 빌드/동결된 실행 파일의 offline end-to-end를 수행합니다. 최종 실행 결과는 이 문서의 검증 결과 섹션에 기록합니다.

## 알려진 제한 및 실제 사용자 수용 테스트

- 실제 기업 데이터의 모든 변형 스키마/이미지 크기, 유료 OpenAI 호출은 검증하지 않았습니다. 첫 실데이터는 소규모 pilot로 확인해야 합니다.
- OpenAI가 현재 모델에 대해 image input과 strict structured output을 지원해야 합니다. 모델 단가 입력은 사용자 책임이며 비용 제한은 추정치입니다.
- API 요청을 provider가 처리한 직후 프로세스가 죽으면 결과를 복구할 수 없고, Retry는 추가 비용이 발생할 수 있습니다. 보수적 예약액과 UNKNOWN 이력을 남깁니다.
- 자동 저장은 초안이며 반드시 완료 저장과 구분합니다. UI의 실제 한글 입력, HiDPI, 듀얼 모니터, 매우 큰 이미지, Windows 종료/백신 환경은 팀원 PC에서 확인해야 합니다.
- 앱 안의 이미지 데이터는 로컬 경로로 읽습니다. 네트워크 마운트 자동 탐지는 완전하지 않습니다.
- 팀 ZIP은 동일 AI 결과 문맥의 검수 교환용입니다. 독립적으로 재실행한 다른 GPT 결과에 기반한 검수는 stale 검수로 거절합니다.
- DB/ZIP 암호화, Windows 코드 서명, 자동 업데이트는 포함하지 않았습니다.
- 이미지 opacity slider는 제공하지 않습니다. 동기화 pan/zoom, difference와 flicker를 제공합니다.
- 모델 학습을 실행하는 도구는 아닙니다. 실제 Baseline/Retrained 예측 JSON을 받아 평가합니다.

## 다음 개선 후보

실데이터 adapter 수용 테스트 확장, 이미지 캐시/대형 데이터 페이지 단위 목록, provider-side 비동기 Batch, OS keyring, 선택형 Golden subset UI, 코드 서명/업데이트, 팀 충돌 비교 화면 개선을 고려할 수 있습니다.
