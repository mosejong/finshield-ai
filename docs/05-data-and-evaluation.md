# 05. Data & Evaluation

## Dataset policy
데이터 출처, 라이선스, 수집일, 정제 규칙을 기록한다. `data/`는 원본 데이터의 라이선스가 명확해지기 전 Git에 올리지 않는다.

## Candidate tasks
### Fraud/risk classification
Precision, Recall, F1, Confusion Matrix, class별 recall. 금융보안 특성상 accuracy만 제시하지 않는다.

### Risk signal extraction
기관 사칭, 긴급성, 계좌/카드 요구, 인증번호 요구, 앱 설치, 재송금, 링크 클릭 유도 등의 precision/recall/F1.

### Scenario engine
Golden set에 입력 상황, 이미 수행한 행동, 예상 scenario, 허용/금지 행동을 기록해 비교한다.

### Explanation/evidence
근거 포함률, 잘못된 근거 비율, unsupported claim rate, 대응절차 일치율.

### Service
API p50/p95, error rate, model latency, external API failure fallback.

## Baselines
1. Rule-only
2. LLM-only
3. Proposed hybrid

목표는 LLM 사용 자체가 아니라 **왜 hybrid가 더 안전/정확한지 증명**하는 것이다.
