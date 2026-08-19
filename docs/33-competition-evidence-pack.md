# Competition Evidence Pack v0.1

## 검증 가능한 주장

1. FinShield의 사기 **판정**은 런타임 웹 검색이나 LLM 호출 없이 결정론적으로
   동작한다. `POST /api/v1/analyze`가 위험 수준·유형·행동을 정하고, LLM은 그 결과를
   받아 설명 문장만 만드는 별도 엔드포인트(`/api/v1/analyze/explanation`)에 있다.
   모델이 판정에 닿을 경로가 함수 서명에 없다(2026-08-19 검증, 아래 6번).
2. 합성 bootstrap 61건에서 Scenario Engine v0.1은 legacy 5-keyword baseline보다
   recall과 F1이 높았다.
3. 행동에 연결된 정적 공식 근거는 benchmark 대상 응답에서 100% source ID로
   연결됐다.
4. 결과는 메시지 위험 신호와 사용자가 이미 수행한 행동을 분리해, 낮은 문구 점수라도
   긴급한 사용자 상태에는 필수 대응 행동을 제시한다.
5. 로컬 합성 데이터, 평가 코드, 결과 JSON, 오류 case ID를 저장소에서 재현할 수 있다.
6. 같은 61건을 `gemini-3.6-flash` 단독에게도 시켰고, Rule-only / LLM-only / Hybrid
   3자 비교를 유료 호출 없이 재현할 수 있다(판정 61건이 저장소에 커밋돼 있다).
   **탐지만 보면 모델이 우리 엔진보다 나았다**(재현율 1.000 대 0.949, F1 0.975 대
   0.961). 그럼에도 결정론 경로를 판정에 남긴 근거는 나머지 세 칸이다 — 필수 행동
   coverage 0.600 대 0.967, 상태 정책 정확도 0.508 대 0.967, 공식 근거 0.0 대 1.0.

## 함께 밝혀야 하는 한계

- 61건은 실제 사용자 분포를 대표하지 않는 개발용 합성 표본이며 상태 분포도
  `received_only`에 치우쳐 있다.
- 같은 데이터로 오류를 찾고 규칙을 교정했으므로 독립 held-out 성능이 아니다.
- LLM-only 및 Hybrid 비교는 2026-08-19에 수행했으나 **같은 non-held-out 61건**이며,
  프롬프트 한 벌·모델 한 개·실행 한 번의 결과다. 모델 일반 능력의 측정이 아니다.
- 그 비교에서 상태 정책 정확도 0.508은 모델에게 `STATE_MINIMUM_RISK` 정책표를 준 적이
  없는 상태의 수치다. "주지 않은 정책의 준수율"이라는 점을 함께 밝힌다.
- 3자 비교는 전부 탐지·행동에 대한 숫자다. 설명 문장 자체의 품질(근거 이탈률, 안전
  필터 차단율, prompt injection 내성)은 아직 측정하지 않았다.
- 공식 근거 연결률은 행동-source 무결성이지 법률·금융 자문의 정답률이 아니다.
- latency는 in-process ASGI 개발기 측정이며 배포 SLO가 아니다.

## 심사 증거 경로

| 증거 | 경로 |
|---|---|
| 합성 golden set | `evaluation/data/fraud_golden_v0.1.jsonl` |
| 출처·라벨·라이선스 | `evaluation/data/README.md` |
| 평가 구현 | `evaluation/fraud_benchmark.py` |
| 재현 명령 | `scripts/evaluate_fraud_engine.py` |
| 기계 판독 결과 | `evaluation/results/fraud-benchmark-v0.1.json` |
| 평가 해설 | `docs/32-fraud-evaluation-benchmark.md` |
| 설계 결정 | `docs/adr/0007-bootstrap-fraud-evaluation.md` |
| 시간순 개발·리뷰 | `docs/devlog/2026-08-13/fraud-evaluation-benchmark-v0.1.md` |
| LLM 단독 판정자 | `evaluation/llm_judge.py` (제품 경로에는 없다) |
| 유료 측정 명령 | `scripts/run_llm_fraud_judge.py` |
| 판정 61건 원본 | `evaluation/results/llm-judge-fraud-v0.1.json` |
| 3자 비교 해설 | `docs/32-fraud-evaluation-benchmark.md` §2026-08-19 |
| 시간순 개발·리뷰 | `docs/devlog/2026-08-19/llm-only-benchmark.md` |

## 다음 증거 단계

1. v0.1을 동결하고 별도 작성자·별도 파일의 held-out v0.2를 만든다.
2. 유형별 최소 support와 persona별 분포를 사전에 정한다.
3. ~~고정된 model ID, prompt, temperature, provider와 비용 한도를 정한 뒤에만
   LLM-only를 실행한다.~~ 2026-08-19 완료(비용 한도는 아직 선불 크레딧뿐이다).
4. ~~Hybrid를 구현한 뒤 동일 데이터와 동일 오류 분류로 비교한다.~~ 2026-08-19 완료.
   **held-out v0.2에서 같은 3자 비교를 다시 돌리는 것**이 남은 일이다.
5. 공개 배포 환경에서 TLS·proxy·동시성을 포함한 latency와 error rate를 측정한다.
6. 모델이 잡고 규칙이 놓친 `fg-046`·`fg-047`을 v0.2에서 **규칙 어휘로** 메운다.
   모델을 판정 경로에 넣지 않는다.
7. 설명 문장 품질을 측정한다 — 근거 이탈률, 안전 필터 차단율, prompt injection 골든셋.
