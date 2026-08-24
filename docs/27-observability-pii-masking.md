# 27. 관측성·PII 비노출·운영 준비

## 목적

장애와 지연은 추적할 수 있어야 하지만 금융 프로필, 사기 의심 원문, 세션 토큰, 인증정보를 로그로 복제해서는 안 된다. FinShield의 관측성은 허용 목록 방식으로 최소 메타데이터만 기록한다.

## 안전한 요청 로그 계약

각 완료 요청은 한 줄 JSON으로 다음 필드만 기록한다.

- `timestamp`: UTC ISO 8601
- `service`: `finshield-api`
- `event`: `http_request`
- `request_id`: 안전한 문자 8~64자 또는 서버가 생성한 32자 ID
- `method`: HTTP 메서드
- `route`: 실제 URL이 아닌 FastAPI route template
- `status_code`: 응답 상태
- `duration_ms`: 애플리케이션 처리시간

다음 값은 읽거나 기록하지 않는다.

- query string과 실제 path parameter/프로필 UUID
- request·response body와 금융값
- Cookie, 세션 원문, Authorization
- 사용자 ID, IP, User-Agent
- 사기 의심 메시지·URL 원문

Uvicorn 기본 access log는 운영 이미지에서 비활성화한다. 위 JSON 로그가 요청 관측의 기준이다. 예외 traceback은 Uvicorn 오류 로그에 남을 수 있지만 요청 본문과 인증 헤더를 예외 메시지에 포함하는 코드는 금지한다.

## 요청 추적

유효한 `X-Request-ID`는 응답에 그대로 돌려주고, 공백·개행·과도한 길이 등 허용 형식 밖의 값은 무시한 뒤 새 ID를 만든다. `Server-Timing`에는 애플리케이션 처리시간만 제공한다.

## 내부 지표

`GET /internal/metrics`는 Prometheus text 형식으로 route template별 요청 수와 latency histogram을 반환한다. OpenAPI에서는 숨긴다. label은 method·route template·status만 사용해 cardinality와 PII 유입을 제한한다.

현재 backend는 2 workers이므로 이 endpoint는 응답한 한 process의 값이다. 전체 p50/p95와 오류율은 모든 worker의 JSON 로그를 중앙 집계해 계산한다. 단일 process 지표를 전체 서비스 값으로 보고하지 않는다.

이 endpoint는 Caddy/Next 공개 경로에 연결하지 않는다. backend host port도 loopback 전용이므로 서버 내부 수집기만 접근한다.

## 설명 계층 지표 (2026-08-24)

LLM 설명 계층은 오래 아무것도 기록하지 않았다. 어느 모델이 몇 번 실패했는지, 안전 필터에 얼마나 막히는지 셀 수 없었다(`docs/34` 9절). 같은 endpoint에 지표군 셋을 덧붙여 해결한다. **새 endpoint를 열지 않는다** — 새 외부 표면은 CLAUDE.md의 보안 검토 대상이고, 여기서 필요한 것은 표면이 아니라 숫자다.

- `finshield_llm_explanation_attempts_total{model,outcome}`: 모델 호출 시도 수
- `finshield_llm_explanation_attempt_duration_milliseconds_sum{model,outcome}`: 시도별 누적 소요시간
- `finshield_llm_explanation_results_total{outcome}`: 요청당 최종 결과 수

대체 모델이 있으므로 요청 하나가 시도 둘을 만든다. 시도와 결과를 나눠 세는 이유가 그것이다. 시도 지표로는 "주 모델이 얼마나 막히는가", 결과 지표로는 "설명이 결국 비었는가"를 계산한다.

로그도 두 줄을 추가한다. logger는 `finshield.llm`, 형식은 요청 로그와 같은 한 줄 JSON이다.

- `llm_explanation_attempt`: `model`, `outcome`, `attempt`, `duration_ms`
- `llm_explanation_result`: `outcome`, `attempts`

`outcome`은 자유 문자열이 아니라 닫힌 어휘(`app/services/llm/outcomes.py`의 `ExplanationOutcome`)다. **provider가 준 문자열을 그대로 label로 쓰지 않는다.** 그렇게 하면 Gemini가 새 `finishReason`을 추가하는 날 검토받지 않은 시계열이 생기고, Prometheus label은 한 번 늘어나면 줄지 않는다. 모르는 값은 어휘 안의 칸(`stopped_early`, `unspecified`)으로 접는다. `model` label도 허용 목록(`^[A-Za-z0-9._-]{1,64}$`)을 통과하지 못하면 `other`로 센다 — 마스킹은 빠뜨린 것을 흘리고 허용 목록은 모르는 것을 버린다.

프롬프트, 모델 출력 본문, 사기 의심 원문은 어느 줄에도 남지 않는다. 개수와 성패만 남긴다(ADR 0006).

지표를 세는 자리는 `explain_with_fallback`(조립 계층)이고 `explain_analysis`(순수 계층)가 아니다. `evaluation/`이 후자를 직접 부르므로, 거기에 카운터를 두면 벤치마크 한 번에 운영 지표가 오염된다.

## 상태 확인

- `/health`: 기존 호환 liveness.
- `/health/live`: process 생존 확인. 외부 의존성을 검사하지 않는다.
- `/health/ready`: 세션·프로필 storage 연결을 실제 확인하고 불가하면 503.

Compose backend healthcheck는 readiness를 사용하므로 DB 연결이 준비되지 않은 backend로 web 요청이 전달되지 않는다.

## 자동 검증

- 단위 테스트는 알려진 UUID, query, 금융 본문, Cookie, Authorization이 JSON 로그와 metrics에 없는지 확인한다.
- 잘못된 request ID가 교체되는지 확인한다.
- 런타임 검증기는 실제 session token, profile UUID, 소득값 `2800000`이 Docker backend logs에 없는지 확인한다.
- 런타임 검증기는 구조화 요청 로그가 실제로 출력됐는지 함께 확인한다.
- `tests/test_llm_explanation_outcomes.py`는 설명 계층에 대해 같은 검사를 한다. 원문에 심은 주민등록번호·계좌번호와 모델이 지어낸 전화번호가 로그·지표에 없는지, 응답 본문에서 온 문자열이 label이 되지 않는지, `app/` 안에 사유 없이 올라오는 실패가 없는지(구문 트리 검사)를 확인한다.

## 남은 운영 작업

- 배포 플랫폼의 로그 보존기간·접근권한·삭제 정책 결정
- 중앙 로그 집계와 p50/p95·5xx 대시보드 연결
- 오류율·readiness 실패·provider 장애 알림 임계치 설정
- 특정 사용자 행동 감사 로그는 사용자 계정·법적 목적이 정해진 뒤 별도 최소수집 설계
