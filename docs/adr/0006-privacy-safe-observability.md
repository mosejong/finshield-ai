# ADR 0006: 허용 목록 기반 개인정보 안전 관측성

- 상태: 승인
- 날짜: 2026-08-13

## 결정

요청 로그는 route template, method, status, duration, request ID만 JSON으로 기록한다. URL 원문·query·path 값·본문·Cookie·Authorization·사용자 식별자는 기록하지 않는다. latency는 process-local histogram과 JSON 로그를 함께 제공하며 다중 worker 전체 수치는 중앙 로그 집계로 계산한다.

## 이유

마스킹 정규식은 새로운 금융 필드나 문구 형식을 놓칠 수 있다. 민감값을 먼저 기록한 뒤 지우는 방식보다 애초에 허용된 메타데이터만 읽는 방식이 안전하다. route template은 운영 분석에 충분하면서 UUID와 검색어 노출을 막는다.

## 결과

- 운영 access log를 비활성화하고 애플리케이션 JSON 로그를 기준으로 삼는다.
- 개별 사용자 추적 분석은 의도적으로 지원하지 않는다.
- `/internal/metrics`는 worker별 값이며 전체 지표로 오해하지 않는다.
