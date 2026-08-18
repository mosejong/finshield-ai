# Competition Evidence Pack v0.1

## 검증 가능한 주장

1. FinShield의 현재 사기 분석은 런타임 웹 검색이나 LLM 호출 없이 결정론적으로
   동작한다.
2. 합성 bootstrap 61건에서 Scenario Engine v0.1은 legacy 5-keyword baseline보다
   recall과 F1이 높았다.
3. 행동에 연결된 정적 공식 근거는 benchmark 대상 응답에서 100% source ID로
   연결됐다.
4. 결과는 메시지 위험 신호와 사용자가 이미 수행한 행동을 분리해, 낮은 문구 점수라도
   긴급한 사용자 상태에는 필수 대응 행동을 제시한다.
5. 로컬 합성 데이터, 평가 코드, 결과 JSON, 오류 case ID를 저장소에서 재현할 수 있다.

## 함께 밝혀야 하는 한계

- 61건은 실제 사용자 분포를 대표하지 않는 개발용 합성 표본이며 상태 분포도
  `received_only`에 치우쳐 있다.
- 같은 데이터로 오류를 찾고 규칙을 교정했으므로 독립 held-out 성능이 아니다.
- LLM-only 및 Hybrid 비교는 아직 수행하지 않았다.
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

## 다음 증거 단계

1. v0.1을 동결하고 별도 작성자·별도 파일의 held-out v0.2를 만든다.
2. 유형별 최소 support와 persona별 분포를 사전에 정한다.
3. 고정된 model ID, prompt, temperature, provider와 비용 한도를 정한 뒤에만
   LLM-only를 실행한다.
4. Hybrid를 구현한 뒤 동일 held-out 데이터와 동일 오류 분류로 비교한다.
5. 공개 배포 환경에서 TLS·proxy·동시성을 포함한 latency와 error rate를 측정한다.
