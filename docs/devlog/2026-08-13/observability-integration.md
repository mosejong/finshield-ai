# 관측성·PII 비노출 main 통합

- 날짜: 2026-08-13 (Asia/Seoul)
- 역할: PM main 관리
- 코드 PR: #52
- feature commit: `d42ea81a90fc3ae6910bf0fbbc3442c651317299`
- main merge commit: `391e962`
- 상태: 통합 완료

## 통합 범위

- 허용 목록 한 줄 JSON 요청 로그와 안전한 request ID
- route template 기준 요청 수·latency histogram
- liveness/readiness 분리와 storage readiness 기반 Compose healthcheck
- 운영 raw access log 비활성화
- 단위·실제 Docker 로그 PII 비노출 회귀
- 운영 문서, ADR, 백로그 갱신

## PM 검수 결과

- 로컬: Python 199 passed/1 skipped; frontend 35 passed; build·TypeScript·lint 통과.
- 실제 Docker/PostgreSQL: structured log 출력, session token·profile UUID·소득값 비노출, 요청당 로그 1줄.
- 기존 보존·backup/restore·암호화·계정 삭제 `0|0|0` 회귀 통과.
- GitHub Linux CI: test, web, container-runtime 두 실행 모두 통과.

## 범위 판단

process-local histogram은 다중 worker 전체 수치가 아니다. 따라서 API latency instrumentation은 완료했지만 공모전 성능표의 p50/p95는 2차 benchmark runner가 같은 입력과 반복 횟수로 산출해야 한다. 플랫폼별 로그 보존·알림은 실제 배포 플랫폼 선택 후 확정한다.

## 다음 단계

2차에서 persona·사기 유형·사용자 상태를 포함한 golden set, 평가 runner, 반복 성능 측정, 공모전 근거 패키지를 순서대로 만든다.
