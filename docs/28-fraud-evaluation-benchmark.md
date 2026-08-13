# Fraud Evaluation Benchmark v0.1

## 목적

Fraud Scenario Engine을 단순 정확도가 아니라 탐지, 유형, 필수 신호, 사용자 상태별
행동, 공식 근거 연결로 나눠 재현 가능하게 측정한다.

## 데이터

- ID: `fraud_golden_v0.1`
- 61건: 위험 39건, 정상·예방 문맥 22건
- 사회초년생, 소상공인, 미지정 persona와 7개 `UserState` 포함
- 모두 팀이 직접 작성한 합성 문장
- 개인정보·실제 피해 메시지·외부 데이터셋 없음
- bootstrap 개발셋이며 `held_out: false`
- 결과 JSON에 persona·state 분포와 정규화 데이터 SHA-256 포함
- 모든 `UserState` 최소 3건, 단 `received_only` 43건으로 불균형

상세 출처와 라벨 계약은 `evaluation/data/README.md`에 있다. 이 데이터는 엔진 교정에도
사용됐으므로 실서비스 일반화 성능의 근거가 아니다.

## 재현

```bash
python -m scripts.evaluate_fraud_engine --check
python -m scripts.evaluate_fraud_engine \
  --check \
  --performance-repeats 20 \
  --output evaluation/results/fraud-benchmark-v0.1.json
```

`--check`는 Scenario Engine의 precision 0.75 이상, recall 0.65 이상, FPR 0.25 이하,
필수 signal·action coverage 및 상태 정책 정확도 0.90 이상, 공식 근거 coverage 1.0을
요구한다. CI도 동일 명령을 별도 실행한다.

## 2026-08-13 측정 결과

| 항목 | Legacy 5-keyword baseline | Scenario Engine v0.1 |
|---|---:|---:|
| Precision | 0.857143 | 0.973684 |
| Recall | 0.461538 | 0.948718 |
| F1 | 0.600000 | 0.961039 |
| FPR | 0.136364 | 0.045455 |
| Accuracy | 0.606557 | 0.950820 |

Scenario Engine의 필수 signal coverage는 0.943396, 필수 action coverage는 0.966667,
상태 정책 정확도는 0.967213, action-source 근거 coverage는 1.0이다. 상세 유형별
수치와 오류 ID는 `evaluation/results/fraud-benchmark-v0.1.json`을 기준으로 한다.

## 알려진 오류

- false negative: `fg-046`, `fg-047`
- false positive: `fg-049`
- 기관 사칭 유형 support가 6건에 불과해 유형별 수치의 불확실성이 크다.
- 예방 문맥 억제는 일반 자연어 부정 해석기가 아니라 명시적 안전 문구에 대한 좁은
  규칙이다. 안전 문구 뒤에 직접 요구가 이어지면 억제하지 않는다.

오류 ID를 지우거나 점수만 높이기 위해 데이터에서 제거하지 않는다. v0.2 held-out
평가 전에 유형별 표본과 변형 문장을 늘린다.

## Baseline 정직성

- `legacy_rule_v0`: 실행됨. 기존 공개 호환 5-keyword 규칙이다.
- `scenario_engine_v0_1`: 실행됨. 결정론적 signal·taxonomy·state policy·evidence다.
- `llm_only`: 실행하지 않음. 고정 model·prompt·provider·예산 계약이 없다.
- `proposed_hybrid`: 구현하지 않음. 현재 제품에 LLM 설명 계층이 없다.

따라서 현재 결과로 “Hybrid가 LLM-only보다 우수하다”고 주장하지 않는다.

## 지연시간 범위

결과 JSON의 latency는 FastAPI 앱을 같은 Python 프로세스에서 ASGI transport로 호출한
개발기 측정이다. 네트워크, TLS, reverse proxy, 실제 동시 사용자, 외부 상품 API
지연은 포함하지 않는다. 운영 SLO나 배포 성능 수치로 사용하지 않는다.
