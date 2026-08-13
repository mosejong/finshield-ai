# ADR-0007: 합성 bootstrap fraud evaluation을 먼저 고정한다

- 상태: Accepted
- 날짜: 2026-08-13

## 맥락

현재 저장소에는 결정론적 Scenario Engine이 있지만 재현 가능한 분류·행동·근거
평가셋이 없었다. 실제 피해 메시지는 개인정보, 동의, 라이선스와 표본 편향 문제가
해결되지 않았다. LLM baseline은 고정 model·prompt·provider 계약도 없다.

## 결정

팀이 직접 작성한 합성 61건을 versioned JSONL로 저장하고 다음을 기계적으로 측정한다.

- 이진 precision, recall, F1, FPR, accuracy
- 유형별 precision, recall, F1과 support
- 필수 public signal·action coverage
- 사용자 상태별 최소 risk와 필수 action을 함께 보는 정책 정확도
- action과 official source의 양방향 연결 coverage
- 명시적인 false positive/negative case ID

Legacy와 Scenario Engine만 실행하며 LLM-only와 Hybrid는 미실행 상태를 결과에 남긴다.
최소 품질 기준은 CI에서 실패 조건으로 사용한다.

## 결과

개발 중 오탐을 재현하고 좁은 예방 문맥 억제를 추가할 수 있다. 반면 같은 데이터로
수정했기 때문에 독립 성능을 주장할 수 없다. v0.2 held-out 데이터는 v0.1 동결 후
별도 작성·검수한다.
