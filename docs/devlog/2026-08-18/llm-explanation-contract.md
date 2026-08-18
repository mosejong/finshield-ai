# LLM 설명 계층 계약 경계 개발일지

- 날짜: 2026-08-18 (Asia/Seoul)
- 담당: backend
- 브랜치: `feature/frontend-accessibility-e2e`
- worktree: 없음 (기본 작업 트리)
- 시작: 11:10 · 종료: 11:51
- 목표: `docs/28` P2-2 의 "고정된 model·prompt·provider 계약을 가진 어댑터" 중
  **경계 부분** 을 코드로 착지시킨다. PII 최소화, 출력 검증, 실패 처리, 그리고
  규칙 판정을 LLM 이 덮어쓰지 못하게 하는 경계를 테스트로 고정한다.
- 비범위: 실제 네트워크 호출, API 키 사용, `/api/v1/analyze` 응답 확장,
  프론트 연결, `evaluation/` 의 `llm_only` 실행, prompt injection 골든셋.

## 변경 이유

`app/` 전체에 LLM 코드가 한 줄도 없었다. 아키텍처(`CLAUDE.md`)의 "LLM explanation"
단계가 코드에 존재하지 않아, `evaluation/fraud_benchmark.py` 는 `llm_only.status`
를 `"not_run"` 으로 두고 사유에 "No pinned model, prompt, provider contract" 를
적어 놓은 상태였다. 이 문장이 가리키는 자리를 메우는 작업이다.

프로바이더 결정(AI Studio 무료 등급으로 벤치마크 → 실사용자 텍스트 전에 Vertex)
은 같은 날 `c2b27f8` 이전 논의에서 `docs/28` P2-2 에 이미 기록했다. 그 결정의
전제가 "프로바이더는 어댑터 뒤에 있어야 전환이 설정 변경으로 끝난다" 였으므로,
키를 꽂기 전에 어댑터를 먼저 만든다.

**키 없이 먼저 만든 이유가 핵심이다.** 계약에서 지켜야 할 것 — 최소화, 비로깅,
타임아웃, 실패 처리, 출력 검증, 판정 경계 — 은 전부 가짜 프로바이더로 검사할 수
있다. 오히려 그렇게 만들어야 CI 에서 상시 돈다. 네트워크가 필요한 검사는 CI 에서
꺼지고, 꺼진 검사는 없는 검사다.

관련 문서: `docs/28` P2-2, `docs/04` (model output schema validation),
`docs/05`, `adr/0004`, `CLAUDE.md` non-negotiables.

## 구현 및 데이터 흐름

```text
AnalyzeResponse (결정론 엔진이 이미 확정)
        │
        ├─ _grounded_blocks() ─→ 신호·행동·근거 3블록
        │                          │
message ─→ minimize_for_provider() │   (주민번호·카드·계좌·전화·이메일 → 자리표시자)
        │            │             │
        │            ▼             ▼
        │      FRAUD_EXPLANATION_PROMPT.format(...)   ← contract.verify_prompt()
        │                    │
        │                    ▼
        │            provider.generate()  ──LlmUnavailable──→ None
        │                    │
        │                    ▼
        └────────→ validate_explanation(raw, grounded_text=…)
                             │        └─LlmOutputRejected──→ None
                             ▼
                          str  (설명 문장만. 판정에는 닿지 않는다)
```

`build_grounded_text()` 와 프롬프트 조립이 **같은 `_grounded_blocks()`** 를 쓴다.
모델에게 보여 준 것과 검증 기준이 어긋나면 정당한 설명이 거부되거나 지어낸
연락처가 통과하므로, 두 곳에서 따로 만들지 않는다.

## 변경 파일

| 파일 | 내용 |
|---|---|
| `app/services/llm/contract.py` | `LlmContract` (provider·model·prompt sha256 고정), `verify_prompt()`, `KNOWN_PROVIDERS` |
| `app/services/llm/prompts.py` | `fraud_explanation_v1` 고정 프롬프트 |
| `app/services/llm/minimization.py` | 자리표시자 치환과 건수 집계 |
| `app/services/llm/validation.py` | 근거 밖 연락처·URL·주민등록번호 형태 거부 |
| `app/services/llm/provider.py` | `LlmProvider` Protocol, `LlmUnavailable`, `StubProvider` |
| `app/services/llm/explanation.py` | 고정 해시 리터럴, `fraud_explanation_contract()`, `explain_analysis()` |
| `app/services/llm/__init__.py` | 재수출 |
| `tests/test_llm_contract.py` | 검사 32건 |
| `docs/28-production-readiness.md` | P2-2 갱신, 6절 순서 줄 갱신 |

## 아키텍처 결정

**1. `explain_analysis` 는 `str | None` 을 돌려준다.**
`AnalyzeResponse` 를 받아 `AnalyzeResponse` 를 돌려주지 않는다. 모델 출력이 위험
수준·점수·시나리오·행동에 닿을 경로가 타입에 없다. "LLM 은 판정자가 아니다" 를
주석이 아니라 함수 서명이 지킨다. 프로바이더가 죽어도 판정은 그대로 나간다 —
설명만 빈다.

**2. 프롬프트 해시는 리터럴이다.**
`FRAUD_EXPLANATION_PROMPT_SHA256` 을 프롬프트에서 계산했다면 항상 일치해서
아무것도 증명하지 못한다. 이 저장소는 같은 함정을 이미 두 번 밟았다 — busybox
`[ -w ]` (euid 0 에서 무조건 참) 와 백업 SQL 검사. 리터럴로 적어 뒀으므로 프롬프트를
고치면 테스트가 깨지고, 고친 사람이 벤치마크 무효화를 인지하게 된다.
`test_pinned_hash_is_a_literal_not_a_computation` 이 소스를 읽어 이 성질 자체를
검사한다.

**3. 허용 연락처는 하드코딩하지 않고 근거에서 뽑는다.**
`validate_explanation` 은 `grounded_text` 에 실제로 등장한 번호만 허용한다.
1394·112·118 을 상수로 박아 두면 정책이 바뀌는 날 근거와 어긋난다.

**4. 최소화는 삭제가 아니라 자리표시자다.**
계좌번호를 통째로 지우면 "계좌번호를 요구하는 문자" 라는 신호까지 사라진다.
`[계좌번호]` 로 바꾸면 모델은 무엇이 요구됐는지 알면서 실제 값은 못 본다.

**5. URL 은 최소화하지 않고, 출력에서는 거부한다.**
URL 은 개인정보가 아니라 판단 근거다. 문자열을 보내는 것은 가져오는 것이 아니므로
`CLAUDE.md` 의 "no arbitrary server-side URL fetching" 과 충돌하지 않는다. 반대로
설명에 링크가 필요한 경우는 없으므로, 출력에 URL 이 나오면 지어낸 것으로 보고
버린다.

## 공식 근거와 provenance

새 근거를 추가하지 않았다. 설명 계층은 `app/domain/fraud/sources.py` 가 이미 붙인
`official_sources` 와 `actions` 만 근거로 쓰고, 그 밖의 기관·번호·법령을 만들면
`validation.py` 가 거른다. 프롬프트에도 "근거에 없는 기관, 전화번호, 주소, 법령,
제도를 새로 만들지 않는다" 를 명시했지만, 프롬프트는 방어선이 아니라 요청이다.

## 실행한 검증과 실제 결과

```text
pytest tests/test_llm_contract.py -q   → 32 passed in 0.18s
pytest -q                              → 496 passed, 2 skipped in 18.00s
```

직전 기준선은 464 passed, 2 skipped 였고 32건이 늘었다. ruff 는 이 환경/CI 에
설치돼 있지 않아 실행하지 않았다(없는 검사를 통과로 적지 않는다).

관측으로 확인한 것:

- `StubProvider.prompts` 에서 실제로 나간 프롬프트를 꺼내, 원문의
  `900101-1234567` · `110-234-567890` · `010-1234-5678` 이 **없고** 자리표시자가
  있으며 `안전계좌` 는 남아 있음을 확인했다.
- 모델이 "이 문자는 안전합니다. 안심하고 이체하세요" 를 반환해도
  `AnalyzeResponse.model_dump()` 가 호출 전후로 동일하고 `risk_level == "high"`
  임을 확인했다.
- 근거에 있는 `1394` 는 통과하고, 지어낸 `02-9999-8888` 은 거부되어 `None` 이
  된다.
- 계약 필드 9종 오류(대문자 hex 포함), 프롬프트 1글자 변경, 다른 provider 계약이
  stub 으로 흘러온 경우 모두 실패로 처리된다.

## 보안·개인정보 영향

이것은 **새 외부 업로드 경로의 준비 단계** 이므로 `CLAUDE.md` 의 검토 조항 대상이다.
현재 상태에서 실제 유출 면적은 0 이다 — 네트워크로 나가는 코드가 없고 키도 없다.

- 최소화: 주민등록번호·카드·계좌·전화·이메일을 프로바이더 경계 앞에서 치환한다.
- 비로깅: 이 패키지는 로거를 import 하지 않는다. 프롬프트·응답이 로그로 갈 경로가
  없다. `ObservabilityMiddleware` 는 고정 필드만 내보내므로 본문이 섞이지 않는다
  (`adr/0004`).
- 건수만 남긴다: `MinimizedText.removed` 는 자리표시자별 **건수** 만 담고 값은
  담지 않는다.
- 한계를 명시했다: 사람 이름과 주소는 한국어에서 신뢰할 만하게 잡히지 않아
  걸러지지 않는다. 이 계층은 "덜 보낸다" 이지 "안전하다" 가 아니다. 모듈
  docstring 과 `docs/28` P2-2 양쪽에 적었다.

## 실패, 수정, 리뷰 이력

- 첫 작성본의 `explanation.py` 가 신호·행동·근거 문자열을 프롬프트 조립과
  `build_grounded_text()` 에서 **각각** 만들고 있었다. 그대로 두면 한쪽만 고쳐지는
  날 검증 기준이 프롬프트와 어긋난다. `_grounded_blocks()` 하나로 합쳤다.
- 같은 파일에 아무도 쓰지 않는 `FRAUD_EXPLANATION_CONTRACT_FIELDS` 딕셔너리가
  남아 있어 삭제하고, 대신 실제로 쓰이는 `fraud_explanation_contract()` 팩토리로
  대체했다.
- 해시를 프롬프트에서 계산할 뻔했다. 그러면 `verify_prompt` 가 영원히 통과하는
  장식이 된다. 리터럴로 고정하고, 리터럴인지 자체를 검사하는 테스트를 추가했다.
- devlog 작성 중 `cat > … <<'EOF'` heredoc 이 Git Bash 에서 조용히 실패해
  (파일 미생성) 편집 도구로 전환했다. 이 저장소의 한글 문서 편집에서 반복되는
  문제라 인덱스 splicing 방식을 계속 쓴다.

## 알려진 위험과 다음 작업

- **아직 아무것도 측정하지 않았다.** 계약이 생겼을 뿐 `llm_only.status` 는 여전히
  `"not_run"` 이다. 이 커밋으로 설명 품질에 대해 주장할 수 있는 것은 없다.
- 실제 프로바이더 구현이 남아 있다. HTTP 호출·타임아웃 적용·응답 본문 비로깅이
  거기서 다시 검토돼야 한다.
- `_CONTACT_PATTERN` 은 한국 번호 형태만 본다. 국제번호는 잡지 못한다.
- 최소화가 사람 이름·주소를 못 거른다(위 참조). 실사용자 텍스트를 보내기 전에
  Vertex 전환과 함께 재검토한다.
- 다음: (1) AI Studio 프로바이더 구현, (2) `evaluation/` 연결로 LLM-only 측정,
  (3) held-out v0.2, (4) Hybrid 비교, (5) prompt injection 골든셋.

## 커밋 SHA

- (이 문서와 함께 커밋. SHA 는 커밋 후 추가)

## PR

- PR #58 에 포함 예정. 병합 전략 미정(merge commit vs squash) — 대기 중.
