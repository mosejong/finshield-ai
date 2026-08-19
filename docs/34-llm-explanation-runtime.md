# 34. LLM 설명 계층 런타임 (2026-08-19)

## 0. 이 문서가 생긴 이유

`app/services/llm/` 는 2026-08-17 에 완성돼 있었다. 계약(`contract.py`), 개인정보
최소화(`minimization.py`), 고정 프롬프트(`prompts.py`), 출력 검증(`validation.py`),
그리고 판정을 문장으로 옮기는 `explanation.py` 까지 전부 있고 테스트도 붙어 있었다.

**그런데 요청 경로에 연결돼 있지 않았다.**

`explain_analysis()` 는 프로바이더와 계약을 주입받는 함수다. 주입해 주는 사람이
없으면 아무도 부르지 않는다. 실제로 `app/clients/google_ai_studio.py` 를 import 하는
운영 코드는 하나도 없었고 — 테스트만 import 하고 있었다 — 배포된 서비스는 100%
규칙 기반이었다. `evaluation/results/fraud-benchmark-v0.1.json` 의 `llm_only.status`
가 `"not_run"` 인 것도 같은 원인이다(2026-08-19 에 `measured` 로 옮겼다 — 9절).

이 문서는 그 빈칸을 메운 작업의 기록이다. 무엇을 만들었고, **왜 그렇게 만들지 않을
수도 있었는데 그렇게 만들었는지**를 남긴다. 결정의 이유가 없으면 다음 사람이 같은
자리에서 반대로 결정한다.

관련 파일:

| 파일 | 역할 |
|---|---|
| `app/services/llm/runtime.py` | 신규. 스위치·모델 순서·대체 모델·프로세스 캐시 |
| `app/api/routes/analysis.py` | `POST /api/v1/analyze/explanation` 추가 |
| `app/schemas/analysis.py` | `ExplanationResponse` 추가 |
| `app/services/rate_limits.py` | `analyze_explanation` 정책 추가 |
| `app/clients/google_ai_studio.py` | `build_google_ai_studio_provider(values)` — 매핑 주입 |
| `app/main.py` | lifespan 에서 설정 검증 |
| `compose.gemini.yaml` | 신규. 키를 파일 secret 으로 붙이는 선택 override |
| `tests/test_llm_runtime.py` | 신규 9건 |
| `tests/test_analysis.py` | 라우트 4건 추가 |
| `tests/test_rate_limits.py` | 정책 선택·한도 역전 2건 추가 |
| `tests/test_runtime_secrets.py` | override 파일의 secret 까지 검사하도록 확장 |

---

## 1. 무엇이 환경 설정이고 무엇이 코드인가

이 계층에서 가장 먼저 정한 것이다.

**환경이 정하는 것: 켜는가.** `FINSHIELD_LLM_PROVIDER` 하나뿐이다. 값은 `off`(기본),
`stub`, `google_ai_studio`. 배포마다 다르고, 사고가 났을 때 재배포 없이 꺼야 하는
값이라 환경에 둔다.

**코드가 정하는 것: 어떤 모델인가.** `EXPLANATION_MODEL` 과
`EXPLANATION_FALLBACK_MODEL` 은 `runtime.py` 의 상수다. 환경변수로 못 바꾼다.

두 번째가 직관에 어긋나 보이므로 이유를 적는다. `contract.py` 가 이미 같은 판단을
적어 뒀다 — provider 와 model 이 환경변수로 조용히 움직이면, **그 전에 측정한
벤치마크 숫자가 어느 모델의 것인지 아무도 모르게 된다.** 모델을 올리는 것이 코드
변경이어야, 올린 사람이 `evaluation/` 을 다시 돌리게 된다. `tests/test_llm_runtime.py`
의 `test_the_models_come_from_code_not_the_environment` 가 그럴듯한 이름의 환경변수
(`FINSHIELD_LLM_MODEL`, `GEMINI_MODEL`)를 넣어 두고 그래도 코드 상수가 이기는지
확인한다.

### 오타는 off 가 아니다

`FINSHIELD_LLM_PROVIDER=gogole_ai_studio` 를 조용히 off 로 접으면 아무도 오타를 못
찾는다. 서비스는 정상으로 보이고 화면에서 "왜 위험한지" 만 영영 비어 있다. 그래서
모르는 값은 `LlmRuntimeConfigurationError` 로 거부한다.

같은 이유로 **켜 놓고 키가 없는 것도 오류다.** 조용히 끄면 배포에서 키를 빠뜨렸을
때 서비스가 정상으로 보인다. 켠 것과 끈 것은 다른 상태이고, 다르게 다뤄야 한다.

이 검증은 첫 요청이 아니라 `main.py` 의 lifespan 에서 실행된다
(`verify_llm_runtime_configuration()`). 잘못된 설정으로 뜬 컨테이너는 healthcheck 를
통과하지 못하고, 배포가 거기서 멈춘다.

---

## 2. 모델 선택 — 실측 기록

2026-08-19, Google AI Studio 에 직접 호출한 값이다. 계정은 선불 크레딧이 들어 있는
**유료 등급**이다(`docs/28` P2-2).

첫 탐색(짧은 프롬프트, 각 1회):

| 모델 | 응답 시간 | 비고 |
|---|---:|---|
| `gemini-3.1-flash-lite` | 1.31s | 대체 모델로 채택 |
| `gemini-3.5-flash` | 3.75s | |
| `gemini-3.6-flash` | 5.52s | 주 모델로 채택 |
| `gemini-2.5-flash` | 5.88s | |
| `gemini-3.7-flash` | 6.48s | |
| `gemini-3.1-flash` | — | **존재하지 않는다. HTTP 404** |

마지막 줄은 그대로 남긴다. `gemini-3.1-flash` 를 대체 모델로 쓰기로 했다가 404 를
받고 바꾼 것이다. 이름이 그럴듯하다고 있는 모델이 아니며, 확인 없이 상수에 적었다면
**주 모델이 죽었을 때만** 드러났을 종류의 실패다.

**이 표는 이 계층을 설명하지 못했다.** 라우트를 붙이고 실제로 호출해 보니 주 모델은
한 번도 답하지 않았다. 다음 절이 그 이야기다.

### 2-1. 사고 토큰이 답변 예산을 먹고 있었다

라우트 완성 후 첫 실호출 3회가 전부 대체 모델로 떨어졌다. `available: true`,
`model: gemini-3.1-flash-lite`. 설명은 나왔으니 화면상으로는 정상이었다 — **주 모델이
100% 실패하는데 정상으로 보이는 상태**였다.

원인을 계약 수준에서 재현했다.

```
gemini-3.6-flash   t=8.0   7.52s  UNAVAILABLE  stopped early: MAX_TOKENS
gemini-3.6-flash   t=25.0  7.48s  UNAVAILABLE  stopped early: MAX_TOKENS
```

타임아웃이 아니었다. 25초를 줘도 같았다. 원시 응답의 `usageMetadata` 를 보고 답이
나왔다.

| 요청 | thinking 토큰 | 답변 토큰 | finishReason |
|---|---:|---:|---|
| `gemini-3.6-flash`, 1024 tok | 982 | 38 | **MAX_TOKENS** |
| `gemini-3.6-flash`, 4096 tok | 1025 | 125 | STOP |
| `gemini-3.5-flash`, 1024 tok | 984 | 36 | **MAX_TOKENS** |
| `gemini-3.5-flash`, 4096 tok + `thinkingLevel: low` | 725 | 129 | STOP |
| `gemini-3.1-flash-lite`, 1024 tok | 0 | 105 | STOP |

Gemini 3.x flash 계열은 **사고 토큰이 `maxOutputTokens` 와 같은 예산에서 나간다.**
`MAX_OUTPUT_TOKENS = 1024` 는 "설명은 600자니까 넉넉하다" 는 계산으로 정한 값이었고,
그 계산에 사고 몫이 빠져 있었다. 사고에 982 토큰이 나가면 답변에 38 토큰이 남고,
문장은 중간에 잘리고, `finishReason` 검사가 그 잘린 문장을 (정확하게) 버린다.

사고를 하지 않는 `-lite` 만 통과하고 있었다는 것이 이 버그의 성질을 잘 보여 준다.
**사고 모델을 하나라도 주 모델로 세우는 순간 전부 실패했을 텐데, 대체 모델이 받아
주는 바람에 화면에는 아무 문제도 나타나지 않았다.** 대체 경로가 버그를 가린 것이다.

고친 것 둘:

- `MAX_OUTPUT_TOKENS` 1024 → **4096**. 이 상수는 답변 길이가 아니라 **사고 + 답변의
  합**으로 잡아야 한다. `tests/test_llm_provider_google.py::test_the_token_budget_leaves_room_for_thinking`
  가 실측 사고 토큰의 2배 이상을 요구해서 이 값이 다시 내려가는 것을 막는다.
- `generationConfig.thinkingConfig.thinkingLevel = "low"` 추가. 확정된 판정을 3~5문장
  으로 옮기는 일에 깊은 사고는 필요 없고, 출력은 어차피 검증기를 통과해야 한다.
  `gemini-3.5-flash` 는 이것으로 실패에서 4.34초 성공으로 바뀌었다.
  사고를 완전히 끄는 `thinkingBudget: 0` 은 `gemini-3.6-flash` 에서 **HTTP 400** 이라
  쓰지 않는다. `thinkingLevel` 을 모르는 모델도 400 을 낼 텐데, 그러면
  `LlmUnavailable` 로 접혀 다음 모델로 넘어간다 — 조용히 나빠지는 대신 그 모델이
  통째로 빠진다.

고친 뒤 라우트 전 경로 3회:

| 회차 | 응답한 모델 | 총 소요 |
|---|---|---:|
| 1 | `gemini-3.6-flash` | 7.69s |
| 2 | `gemini-3.6-flash` | 8.17s |
| 3 | `gemini-3.6-flash` | 7.65s |

타임아웃은 이 실측의 약 1.7배로 잡았다 — 주 모델 14초, 대체 모델 6초. 모델마다 다른
이유는 `fraud_explanation_contract` 에 적었고, **둘의 합(20초)이 이 계층의 최대 지연**
이라 `tests/test_llm_runtime.py::test_the_worst_case_wait_is_bounded_and_the_fallback_is_the_shorter_one`
가 그 합에 상한을 건다.

### 지금 이 조합이 최선인지는 별개 문제다

주 모델은 7.7~8.2초이고 매 요청 800~1030 토큰을 사고에 쓴다. 대체 모델은 1.6~1.9초에
사고 토큰이 0 이고, 나온 문장은 검증기를 통과했으며 읽기에도 손색이 없었다. **이 과제
— 확정된 판정을 근거 안에서 3~5문장으로 옮기기 — 에서 사고가 사 주는 것이 무엇인지는
아직 측정되지 않았다.** `evaluation/` 에서 두 모델을 비교하기 전까지 이 배치는 근거가
아니라 선택이며, 뒤집는 데 필요한 것은 상수 한 줄이다.

### 대체 모델이 `-lite` 인 것은 타협이 아니다

주 모델이 막혔을 때 필요한 것은 같은 품질이 아니라 **응답이 돌아오는 것**이다. 그리고
어느 모델이 쓰든 출력은 `validate_explanation` 을 통과해야 한다 — 근거에 없는 연락처,
URL, 주민번호 형태는 어느 쪽에서 나와도 버려진다. 품질의 하한은 모델이 아니라 검증기가
잡는다.

두 모델이 **사고 여부에서 갈리는 것도 의도**다. 2-1 이 보여 준 것이 바로 그것이다 —
성질이 같은 모델 둘을 세우면 같은 이유로 함께 죽는다.

### 어느 모델이 답했는지 함께 돌려준다

`ExplanationResult.model` 과 응답의 `model` 필드다. 대체 모델로 넘어갔는데 주 모델
이름을 기록하면, 나중에 이 문장이 어느 모델의 것인지 평가에서 다시 세울 수 없다. 위
1절에서 모델을 코드에 박아 지키려던 것과 정확히 같은 성질의 문제다.

---

## 3. 왜 별도 엔드포인트인가

`POST /api/v1/analyze/explanation` 을 새로 만들었다. `AnalyzeResponse` 에 `explanation`
필드를 더하지 않았다. 이유가 둘이다.

**첫째, 지연이다.** 설명 한 문단에 약 8초가 걸린다(2-1 실측). 판정 응답에 붙이면 위험
수준을 보여 주기까지 그 8초를 기다리게 된다. 지금 의심 문자를 받은 사람에게 가장
나쁜 설계다. 지금 구조에서는 판정이 먼저 그려지고 설명이 그 뒤에 채워진다 —
`analyze_fraud()` 자체는 200회 반복 측정에서 평균 0.041ms 였고, 네트워크 왕복을
얹어도 설명의 8초와는 자릿수가 다르다.

**둘째, 의존 방향이다.** 판정 응답이 설명을 품으면 "설명이 없으면 판정도 없다" 는
상태가 코드 모양으로 **가능해진다.** 나눠 두면 그 상태를 만들 수 없다. `CLAUDE.md` 의
첫 non-negotiable — LLM 은 판정의 권위가 아니다 — 을 주석이 아니라 구조로 지킨다.

### `available` 은 `explanation is None` 과 다르다

| `available` | `explanation` | 뜻 | 화면 |
|---|---|---|---|
| `false` | `null` | 계층이 꺼져 있다 | "왜 위험한지" 블록을 아예 만들지 않는다 |
| `true` | `null` | 켜져 있는데 이번에 못 만들었다 | 블록은 두고 "설명을 불러오지 못했습니다" |
| `true` | 문장 | 정상 | 문장 표시 + 모델 표기 |

꺼져 있을 때 404 나 503 으로 답하지 않는 것이 중요하다. 그러면 프론트엔드가 이것을
장애로 다룬다. 설명이 없는 것은 장애가 아니다.

---

## 4. 클라이언트는 설명받을 판정을 고를 수 없다

이 라우트에서 가장 중요한 결정이다.

엔드포인트는 `AnalyzeResponse` 가 아니라 **`AnalyzeRequest` 를 받는다.** 그리고 서버가
`analyze_fraud()` 를 다시 돌려 판정을 스스로 만든 뒤, 그 판정만 설명한다.

`AnalyzeResponse` 를 받게 했다면 클라이언트가 위험 수준을 `low` 로, 신호를 빈 배열로
적어 보내는 것만으로 모델이 "이 문자는 크게 위험하지 않습니다" 를 써 준다. 결정론
엔진을 두고도 설명이 조작되는 경로가 생긴다. 화면에 붙는 것은 판정이 아니라 문장이므로,
사용자가 실제로 읽는 것은 조작된 쪽이다.

`analyze_fraud` 는 순수 함수라 같은 입력에 같은 판정이 나오고, 다시 부르는 비용은
8초 옆에서 무시할 만하다.

`tests/test_analysis.py::test_the_client_cannot_supply_the_verdict_it_wants_explained`
가 이것을 주장하지 않고 관측한다 — 요청 본문에 `risk_level: "low"` 와 가짜 `summary`
를 섞어 보낸 뒤, 모델이 **실제로 받은 프롬프트**에 서버가 계산한 위험 수준이 들어갔고
가짜 문구는 없는지 확인한다.

---

## 5. 요청 한도 — 밟을 뻔한 함정

설명 경로는 이 서비스에서 가장 비싼 경로다. 유료 외부 호출이 나가고, 대체 모델까지
가면 한 요청에 두 번 나간다. 그래서 `analyze_explanation` 정책을 **10회/분**으로
따로 뒀다(`analyze` 는 30회/분).

함정은 순서와 매칭 방식에 있었다.

- `analyze` 정책은 `exact_path=True` 다. `/api/v1/analyze/explanation` 은 `/api/v1/analyze`
  와 문자열이 다르므로 **이 정책에 걸리지 않는다.**
- 정책을 따로 두지 않으면 이 경로는 아래의 `write` 정책(60회/분)으로 떨어진다.
- 즉 **더 비싼 경로가 더 헐거운 한도를 갖게 된다.**

실제로 확인한 값이다. `analyze_explanation` 을 목록에서 빼고 정책을 고르면
`write / 60` 이 나온다. `tests/test_rate_limits.py::test_the_explanation_path_is_not_looser_than_the_paths_it_sits_under`
가 이름이 아니라 **숫자의 대소**를 검사하는 이유다 — 이름만 맞고 한도가 뒤집혀 있으면
검사가 아무것도 증명하지 못한다.

정책은 `analyze` 보다 **위에** 있어야 한다. 목록은 위에서부터 먼저 맞는 하나만
적용하기 때문이다.

**남는 위험:** 한도는 IP 단위다(`rate_limits.py` 첫머리의 이유 참고). 분산된 남용은
막지 못한다. 그것은 여기가 아니라 프로바이더 쪽 예산 한도로 막을 문제이고, 아직 하지
않았다 — 9절에 남겨 둔다.

---

## 6. 실패 모드

설명 계층은 **어떤 실패에서도 판정 경로를 죽이지 않는다.** 각 경우가 어떻게 되는지.

| 상황 | 결과 | 확인하는 테스트 |
|---|---|---|
| 계층이 꺼져 있음 | 200, `available: false` | `test_explanation_is_absent_but_the_endpoint_still_answers` |
| 프로바이더 이름 오타 | 기동 실패 | `test_a_typo_in_the_provider_name_is_refused` |
| 켰는데 키 없음 | 기동 실패 | `test_turning_it_on_without_a_key_is_an_error_not_a_silent_off` |
| 주 모델 응답 없음 | 대체 모델 시도 | `test_the_fallback_answers_when_the_first_model_is_down` |
| 모든 모델 실패 | 200, `available: true`, `explanation: null` | `test_every_model_failing_yields_no_explanation` |
| 안전 필터 차단 / 잘린 응답 | `LlmUnavailable` → 다음 모델 | `google_ai_studio.py` 의 `finishReason` 검사 |
| 없는 연락처를 지어냄 | 그 모델 출력 폐기 → 다음 모델 | `test_output_that_invents_a_hotline_is_dropped_and_falls_through` |

마지막 줄이 이 계층에서 가장 신경 쓴 곳이다. 가짜 신고번호를 알려 주는 것은 이
서비스가 낼 수 있는 가장 나쁜 출력이다 — 사용자가 그 번호로 전화를 건다. 거부가
**대체 모델 시도로 이어지는지**까지 테스트로 고정했다.

`explain_with_fallback` 은 "프로바이더가 죽음" 과 "출력이 거부됨" 을 구분하지 않고
둘 다 다음 모델로 넘긴다. 호출하는 쪽에서 보면 둘 다 "설명이 없다" 이고, 어느 쪽이든
다음 모델을 시도할 가치가 있기 때문이다. 대신 한 요청에 유료 호출이 두 번 나갈 수
있으므로 **계약 목록은 짧게 유지한다**(현재 2개).

---

## 7. 스트리밍을 하지 않는다

설명이 늦게 나오는 것이 답답하니 토큰을 순차적으로 흘리자는 안을 검토했고,
**하지 않기로 했다.**
나중에 같은 제안이 다시 나올 것이므로 이유를 남긴다.

**(1) 검증을 통과하지 않은 문장을 보여 주게 된다.** 이 계층의 마지막 방어선은
`validate_explanation` 이고, 그것은 **완성된 출력 전체**를 보고 판정한다 — 근거에
없는 연락처가 들어왔는지는 그 연락처가 다 나온 뒤에야 알 수 있다. 스트리밍하면
`02-1234-5678` 이 화면에 찍힌 다음에 거부 판정이 난다. 그때 할 수 있는 일은 이미 읽힌
문장을 지우는 것뿐이고, **사기 경고 화면에서 방금 보여 준 연락처를 회수하는 것**은
8초를 기다리게 하는 것보다 훨씬 나쁘다. `explanation.py` 가 이미 같은 판단을 적어
뒀다 — "검증에 실패하면 설명 없이 간다. 설명이 없는 결과는 불편하지만, 검증을
통과하지 못한 설명이 붙은 결과는 위험하다."

**(2) 기다리는 대상이 이미 바뀌었다.** 3절의 분리 덕분에 사용자는 그 8초 동안 빈 화면을
보지 않는다. 위험 수준·신호·권고 행동·공식 근거는 첫 응답에 이미 다 들어 있고, 늦게
차는 것은 "왜 위험한지" 블록 하나다. 그 블록 하나를 위한 스켈레톤은 스트리밍보다
싸고, 무엇보다 **취소할 수 있다.**

**(3) 지연을 줄이는 더 싼 손잡이가 남아 있다.** `gemini-3.1-flash-lite` 가 1.31초다.
설명 품질이 충분하다고 측정되면 주 모델을 바꾸는 것만으로 8초가 1.7초가 된다(2절 끝).
스트리밍은 SSE 경계·프록시 버퍼링·중간 취소·부분 출력 로깅을 전부 새로 다뤄야 하는
작업인데, 그것을 하기 전에 상수 하나로 4초를 줄일 수 있는지부터 재는 것이 순서다.

**다시 검토할 조건:** 위 (3)을 측정했는데도 사용자에게 필요한 문장이 3초를 넘고,
동시에 출력 검증을 **증분으로** 할 수 있는 방법이 생겼을 때. 두 조건이 함께 만족되기
전에는 이 결정을 뒤집지 않는다.

---

## 8. 켜는 방법

로컬(스텁, 네트워크 없음):

```powershell
$env:FINSHIELD_LLM_PROVIDER = "stub"
uvicorn app.main:app --reload
```

로컬(실제 모델):

```powershell
$env:FINSHIELD_LLM_PROVIDER = "google_ai_studio"
$env:GEMINI_API_KEY_FILE = "secrets/gemini_api_key.txt"
uvicorn app.main:app --reload
```

컨테이너:

```powershell
docker compose -f compose.yaml -f compose.gemini.yaml --env-file .env.docker up -d
```

`compose.gemini.yaml` 이 별도 파일인 이유는 `compose.public-data.yaml` 과 같다. compose 의
`secrets:` 항목은 파일이 실제로 있어야 하므로, 기본 `compose.yaml` 에 넣으면 키가 없는
사람은 `docker compose up` 자체가 실패한다. **없는 쪽이 기본이어야 한다.**

키는 환경변수가 아니라 파일로 받는다. 값으로 주면 `docker inspect` 와 프로세스 목록에
남는다. `secrets/` 디렉터리 전체가 `.gitignore` 되어 있고,
`tests/test_runtime_secrets.py` 가 `git check-ignore` 로 실제 동작을 확인한다 — 이번에
그 검사를 **override compose 파일까지** 훑도록 넓혔다. 기본 파일만 보고 있었기 때문에,
선택 기능의 키는 항상 검사 밖에서 추가되는 구조였다.

---

## 9. 남은 일

- **프로바이더 예산 한도.** IP 한도로는 분산 남용을 못 막는다(5절). 유료 등급이라
  자동으로 멈추는 지점이 없다 — 선불 크레딧 ₩70,000 이 상한의 전부다. Google Cloud
  콘솔에서 일 상한과 예산 알림을 걸어야 하고, 아직 걸지 않았다. `docs/31` 11-5 의
  GCP 예산 알림과 같은 성질의 미완 항목이다.
- ~~**`evaluation/` 연결.**~~ 했다(2026-08-19). `llm_only.status` 가 `measured` 로
  옮겨졌고 Rule-only / LLM-only / Hybrid 비교표가 `docs/32` 에 있다. **결과를 여기
  한 줄로 적어 두면: 탐지만 보면 모델이 우리 엔진을 이겼다**(재현율 1.000 대 0.949,
  F1 0.975 대 0.961). 대신 필수 행동 coverage 0.600, 상태 정책 정확도 0.508, 공식 근거
  0.0 이다. 판정자는 `evaluation/llm_judge.py` 에 있고 제품에는 없다.
- ~~**프론트엔드 연결.**~~ 붙였다(2026-08-19). 10절 참고.
- **안전 필터 차단율 측정.** `finishReason` 이 `SAFETY` 로 오는 비율을 모른다. 사기
  문자를 다루는 서비스라 정상 입력이 차단될 수 있고, 그러면 조용히 설명이 사라진다.
- **prompt injection 골든셋.** 사용자가 붙여넣는 문자 안에 지시문이 섞여 있을 수 있다.
  `validation.py` 가 결과를 거르지만, **얼마나 자주 시도가 성공하는지**는 측정한 적이
  없다.
- **비동기 경계.** 프로바이더가 동기 `httpx` 라 라우트도 `def` 다(FastAPI 가 스레드풀로
  보낸다). 8초짜리 호출이 스레드를 잡으므로, 동시 요청이 늘면 여기가 먼저 막힌다.
  지금 트래픽에서는 문제가 아니지만 부하 테스트 때 첫 번째로 볼 곳이다.
- **로그.** 이 계층은 아무것도 기록하지 않는다. 어느 모델이 몇 번 실패했는지 모른다는
  뜻이다. ADR 0006(`adr/0006-privacy-safe-observability.md`)을 지키려면 **개수와
  성패만** 남기는 형태여야 한다 — 프롬프트와
  출력 본문은 남기지 않는다.

---

## 10. 프론트엔드 연결 (2026-08-19)

`/check/result/[id]` 의 "왜 위험한지" 블록에 붙였다. 관련 파일:

| 파일 | 역할 |
|---|---|
| `web/lib/api/explanation.ts` | 응답 어댑터, 서버·클라이언트 호출 |
| `web/app/api/proxy/analyze/explanation/route.ts` | 신규 프록시 |
| `web/lib/store/explanation-store.ts` | 원문 인계, 결과 캐시, 훅 |
| `web/components/safety/WhyRiskyPanel.tsx` | 설명 자리 추가 |

### 결정론 요약을 대체하지 않는다

이 블록에는 원래 백엔드의 `summary` 가 들어 있었고, 그것은 규칙에서 바로 나오는
값이다. 모델 문장으로 **갈아 끼우지 않고 아래에 덧붙였다.**

이유는 `CLAUDE.md` 의 첫 non-negotiable 과 같다. 판단 근거의 자격을 갖는 것은
결정론 쪽이고, 모델 문장은 그것을 쉬운 말로 옮긴 것이다. 갈아 끼우면 8초 동안
"왜 위험한지" 가 통째로 비어 있게 되고, 모델이 실패한 배포에서는 영영 비어 있다.
덧붙이면 결정론 요약은 즉시 뜨고 모델 문장만 나중에 채워진다.

화면에는 어느 모델이 썼는지와 함께 "위험 수준과 행동은 이 문장이 아니라 규칙
엔진이 정합니다" 를 적는다. 사용자가 이 문단을 판정으로 읽으면 안 된다.

### 원문을 sessionStorage 에 넣지 않았다

이 엔드포인트는 판정이 아니라 **원문**을 받는다(4절). 즉 결과 화면이 설명을
받으려면 사용자가 붙여넣은 문자를 다시 갖고 있어야 한다.

판정 결과는 `sessionStorage` 에 있다(`analysis-store.ts`). 원문도 거기 넣으면
간단했지만 넣지 않았다. 판정은 가공된 값이고 원문은 가공되지 않은 그대로여서,
이름·계좌번호·연락처가 그대로 들어 있을 수 있다. `share/pending.ts` 가 공유로
받은 원문을 화면이 집어가는 즉시 저장소에서 지우는 것과 같은 판단이다.

대신 모듈 메모리로만 넘긴다. **대가는 새로고침하면 설명이 다시 붙지 않는 것**
이다. 판정·신호·행동·공식 근거는 그대로 남고 "왜 위험한지" 는 결정론 요약으로
돌아간다. 원문을 저장소에 남기는 것보다 이쪽이 낫다고 봤다.

요청을 만든 뒤에는 메모리에서도 곧바로 버린다. 결과 `Promise` 는 id 별로
캐시하는데, 유료 호출이 개발 모드의 StrictMode 이중 실행이나 화면 재방문만으로
두 번 나가는 것을 막기 위해서다.

### 예시 결과에는 붙이지 않는다

`/check/result/demo` 는 화면 구조를 보여 주는 예시다. 여는 것만으로 유료 모델
호출이 나가면 안 되므로 훅을 끈다. mock 모드도 같다 — `explainOnServer` 는 mock
모드에서 그럴듯한 문장을 지어내지 않고 `off` 를 돌려준다. 다른 mock 데이터와
성격이 다르기 때문이다. 화면 구조를 보여 주는 예시 값과, 모델이 실제로 뭐라고
말하는지는 서로 대신할 수 없다.

### 상태 세 가지

`available` 과 `explanation` 을 합치지 않고 그대로 옮겼다(3절 표).

| 상태 | 화면 |
|---|---|
| `off` | 설명 자리를 아예 만들지 않는다 |
| `failed` | 자리를 두고 "설명을 불러오지 못했습니다" + 위 요약이 판단 근거라고 안내 |
| `ready` | 문장 + 답한 모델 표기 |

합치면 계층을 켜지 않은 배포에서 매번 "불러오지 못했습니다" 가 뜬다.

### 타임아웃

프론트 기본값은 8초인데(`lib/api/client.ts`), 설명만 25초로 늘렸다. 백엔드가
최악의 경우 20초를 쓰므로(2-1) 기본값을 그대로 두면 백엔드가 정상적으로 답하는
중에 프론트가 먼저 끊는다.

### 실측

`next dev` → 프록시 → 백엔드 → Gemini 전 경로 1회: **9.29초, `gemini-3.6-flash`**.
백엔드 직접 호출이 7.40초였으므로 프록시와 dev 서버가 약 1.9초를 더한다.
프로덕션 빌드에서는 이보다 짧을 것이나 측정하지 않았다.
