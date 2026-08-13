# 관측성·PII 마스킹 개발일지

- 날짜: 2026-08-13 (Asia/Seoul)
- 브랜치: `feature/observability-pii-masking`
- 기준 main: `c5e81d3`
- 시작: 16:53
- 상태: 진행 중

## 목표

금융 원문·프로필 값·세션·인증정보를 로그에서 구조적으로 제외하면서 요청 단위 추적, 응답시간, 상태코드, route별 운영 지표와 storage readiness를 제공한다.

## 결정

- raw URL 대신 FastAPI route template만 기록해 UUID와 query string을 제외한다.
- request/response body, Cookie, Authorization, 사용자 ID는 읽거나 기록하지 않는다.
- 운영 Uvicorn 기본 access log를 끄고 안전한 JSON 요청 로그로 대체한다.
- metrics label은 method·route template·status로 제한한다.
- in-process metrics는 worker별 값이므로 전체 p50/p95는 JSON 로그를 집계해 계산한다.
- 기존 `/health`는 호환 유지하고 `/health/live`, `/health/ready`를 분리한다.

## 예정 검증

- 민감한 UUID·query·본문·cookie·authorization의 로그/metrics 비노출
- request ID 주입 방지와 응답 전달
- readiness와 metrics OpenAPI 비노출
- 전체 Python/frontend/Compose 회귀

## 완료 기록

- 16:54: 허용 목록 JSON 요청 로그, request ID, `Server-Timing`, route template latency 계측 구현.
- 16:55: `/health/live`, `/health/ready`, OpenAPI 비노출 `/internal/metrics` 구현. Compose healthcheck를 readiness로 전환.
- 16:56: Uvicorn raw access log 비활성화와 단위 PII 비노출 회귀 추가.
- 16:57: 런타임 검증기에 실제 session token·profile UUID·소득값 Docker log 비노출 검사를 추가.
- 16:58: 전체 회귀 통과 — Python 199 passed/1 skipped, frontend 35 passed, build·TypeScript·lint 통과.
- 16:59: Docker/PostgreSQL E2E 통과 — 구조화 로그 출력, PII 비노출, 재시작·backup/restore·암호화·삭제 `0|0|0`.
- 17:00: root logger가 있는 환경의 중복 가능성을 제거하고 실제 컨테이너 요청 1건당 JSON 로그 1줄을 확인.

## 남은 운영 경계

- process-local histogram은 2 workers 전체 값이 아니다. 전체 p50/p95는 중앙 JSON 로그 집계가 필요하다.
- 배포 플랫폼의 로그 접근권한·보존기간·삭제정책과 알림 채널은 실제 플랫폼 선택 후 확정한다.
- 사용자 단위 audit log는 익명 MVP 범위에서 만들지 않는다. 계정 체계와 법적 목적을 먼저 정해야 한다.

## Git/PR

- 최종 PM 검수 후 feature PR을 생성한다.
