# 04. Architecture

## Design rule

LLM에게 원문을 던지고 `0~100점 매겨줘`라고 시키는 구조를 피한다.

```text
Client
  |
FastAPI
  |
Input Validator
  |
Feature Pipeline
  +-- Content features
  +-- Requested-action features
  +-- URL/domain features
  +-- Persona/context features
  |
Risk Engine
  |
Scenario Engine
  |
Evidence Store / Retrieval
  |
LLM Explanation Layer
  |
Response Validator
```

## Separation of responsibility

### Deterministic / ML layer
- 위험 행동 요구 탐지
- URL feature
- 유형 분류
- 위험도 구성
- scenario selection

### LLM layer
- 사용자가 이해하기 쉬운 설명
- 확인 질문
- 근거를 벗어나지 않는 요약

## Security-by-design TODO

2026-08-14 기준 실제 코드 상태로 갱신했다. 남은 항목의 우선순위와 착수 조건은 `28-production-readiness.md`를 따른다.

- [x] PII redaction — `app/core/observability.py`가 로그 필드를 allowlist(`request_id`/`method`/route template/`status_code`/`duration_ms`)로 고정한다. 쿼리스트링·본문·경로 파라미터는 구조적으로 로그에 들어가지 않고 `tests/test_observability.py`가 회귀를 막는다.
- [x] secrets management — `app/core/runtime_secrets.py`의 `*_FILE` 우선 조회 + Docker file secrets. 값이 이미지·환경변수·저장소에 남지 않는다.
- [~] request size limits — 스키마 단위 상한만 있다 (`app/schemas/analysis.py`의 `text` 10000자, `url` 2048자). 요청 본문 전체 크기를 막는 HTTP 경계 제한은 없다.
- [~] prompt injection threat model — 문서(`08`, `12`)에는 있으나 LLM 계층 자체가 없어 방어 코드와 golden set 은 미구현이다.
- [ ] rate limiting
- [ ] audit log
- [~] SSRF 방지를 위한 URL 분석 구조 — 서버가 사용자 URL을 가져오지 않는 정책은 유지하고, 어휘 분석은 스킴 유무와 무관하게 동작한다 (`app/domain/fraud/signals.py`, `tests/test_fraud_urls.py`). URL 평판 분석을 도입하는 순간 네트워크 경계 통제가 별도로 필요해진다.
- [ ] model output schema validation — LLM 계층 도입과 함께 진행한다.
