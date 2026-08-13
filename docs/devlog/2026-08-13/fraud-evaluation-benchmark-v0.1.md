# Fraud Evaluation Benchmark v0.1 개발일지

- 날짜: 2026-08-13 (Asia/Seoul)
- 담당: PM·backend
- 브랜치: `feature/fraud-evaluation-benchmark-v01-final`
- worktree: `finshield-ai-eval`
- 목표: 합성 golden set, 재현 benchmark, CI gate, 대회 증거 묶음
- 비범위: 실제 사용자 데이터, LLM-only 실행, Hybrid 구현, 운영 SLO

## 시간순 기록

- 1차 검수: 저장소 지침과 데이터·평가 문서를 읽고 실제 데이터 반입 없이 합성
  bootstrap 데이터만 사용하기로 결정했다.
- 구현: 7개 사용자 상태와 6개 fraud type을 포함하는 JSONL, Pydantic 라벨 검증,
  legacy·scenario evaluator, 오류 case ID, ASGI latency 측정을 추가했다.
- 최초 평가: 45건에서 Scenario precision 0.833333, recall 0.806452, F1 0.819672,
  FPR 0.357143으로 gate에 실패했다. 예방 안내·정상 비교 문맥 오탐과 action 누락을
  확인했다.
- PM 수정: 기준을 낮추거나 실패 문장을 삭제하지 않고 canonical signal에만 동의어를
  보강했다. 명시적인 예방 문구만 억제하고 뒤에 직접 요구가 이어지면 탐지하는 좁은
  문맥 규칙을 추가했다. Legacy 공개 점수 규칙은 변경하지 않았다.
- 재검수: 안전 문맥 4건, 혼합 안전·직접 요구 1건, 결과에 알려진 오류 ID를 고정하는
  회귀 테스트를 추가했다. 데이터는 49건으로 확장했다.
- 상태 분포 검수: 후속 상태가 각 1건뿐인 약점을 확인했다. 6개 상태마다 정상·위험
  문맥을 1건씩 더 추가해 전체 61건, 모든 상태 최소 3건으로 보강했다. 여전히
  `received_only` 43건인 불균형 bootstrap임을 문서에 남겼다.
- 최종 측정: Scenario precision 0.973684, recall 0.948718, F1 0.961039,
  FPR 0.045455. signal 0.943396, action 0.966667, 정책 0.967213, evidence 1.0.
- 한계 검수: 이 데이터가 교정에 쓰인 non-held-out 개발셋이며 실서비스 정확도,
  LLM/Hybrid 우위, 운영 latency를 주장할 수 없음을 평가·대회 문서에 명시했다.

## 데이터·처리 흐름

`versioned JSONL → schema/collection validation → AnalyzeRequest → legacy 또는
Scenario Engine → binary/type/signal/policy/action/evidence metrics → JSON report
→ CI quality gate`

성능 측정은 같은 입력을 in-process ASGI endpoint에 반복 호출하며 네트워크·TLS는
포함하지 않는다.

## 변경 범위

- `app/domain/fraud/signals.py`
- `evaluation/`
- `scripts/evaluate_fraud_engine.py`
- `tests/test_fraud_evaluation.py`
- `.github/workflows/ci.yml`
- `docs/05-data-and-evaluation.md`, `docs/10-mvp-backlog.md`
- `docs/28-fraud-evaluation-benchmark.md`
- `docs/29-competition-evidence-pack.md`
- `docs/adr/0007-bootstrap-fraud-evaluation.md`
- 문서 색인과 `README.md`

## 보안·개인정보

실제 메시지와 개인정보를 사용하지 않는다. benchmark는 outbound URL fetch나 LLM,
외부 API를 호출하지 않는다. latency 결과에도 메시지 원문을 저장하지 않는다.

## 검증

- targeted fraud tests: 46 passed
- 전체 Python: 207 passed, 1 skipped, 기존 TestClient 경고 1건
- benchmark gate: 통과, 20회×61건 latency sample 1,220건
- in-process ASGI latency: p50 2.671ms, p95 4.719ms, max 27.065ms
- frontend: 10 files, 35 tests passed
- Next production build, TypeScript, lint: 통과
- Python compile: 통과
- 구현 commit: `eff8bc0` (`feat: add reproducible fraud evaluation benchmark`)
- PR: #54, https://github.com/mosejong/finshield-ai/pull/54
- PR 생성: 2026-08-13 17:39:13 KST, draft
- GitHub Actions Linux CI: 진행 중
- 병합 시각·merge commit: PM 승인 후 기록

## 알려진 위험과 다음 작업

- `fg-046`, `fg-047` false negative와 `fg-049` false positive
- support가 작은 유형의 지표 변동성
- 한국어 부정·인용·반어에 대한 일반 문맥 해석 부재
- 독립 held-out v0.2, 고정 LLM baseline, 실제 공개 환경 latency 필요
