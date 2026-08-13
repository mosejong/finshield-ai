# Fraud Golden Set v0.1

## 출처와 권리

- `fraud_golden_v0.1.jsonl`은 FinShield 팀이 2026-08-13 직접 작성한 합성 문장이다.
- 실제 피해자 메시지, 개인정보, 외부 데이터셋 문장을 복사하지 않았다.
- 외부 데이터 라이선스나 재배포 권한에 의존하지 않는다.
- `synthetic: true`가 아닌 사례는 v0.1 로더가 거부한다.

## 라벨 계약

각 줄은 독립 JSON 객체이며 다음을 포함한다.

- `case_id`: 변경되지 않는 `fg-NNN` 식별자
- `text`, `persona`, `state`, 선택적 `url`: API 입력
- `is_fraud`, `expected_fraud_types`: 이진·유형 라벨
- `required_signal_codes`: 반드시 노출돼야 하는 public signal
- `expected_min_risk`: 최소 위험 등급
- `required_action_codes`: 사용자 상태상 반드시 필요한 행동
- `annotation_note`: 판정 이유와 경계 조건

라벨의 사기 유형·행동 코드는 실제 API 계약에 존재해야 하고 중복될 수 없다.
모든 `UserState`가 포함돼야 하며 사례 ID는 유일해야 한다.
평가 결과에는 순서와 라벨을 포함한 정규화 사례의 SHA-256을 기록해 어떤 데이터로
측정했는지 식별한다.

## 이용 한계

이 데이터는 합성 61건의 bootstrap 개발셋이며 독립 held-out 테스트셋이 아니다.
각 `UserState`는 최소 3건을 포함하지만 `received_only`가 43건으로 많아 균형
표본은 아니다. 엔진 오류를
확인하고 규칙을 수정하는 데 사용했으므로 이 결과를 실서비스 탐지 성능이나
일반화 성능으로 주장하면 안 된다. v0.2는 이 파일을 동결한 뒤 별도 작성자 검수와
미사용 held-out 표본을 추가한다.
