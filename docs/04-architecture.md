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

- [ ] SSRF 방지를 위한 URL 분석 구조
- [ ] prompt injection threat model
- [ ] PII redaction
- [ ] request size limits
- [ ] rate limiting
- [ ] audit log
- [ ] model output schema validation
- [ ] secrets management
