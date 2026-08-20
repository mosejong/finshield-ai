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

---

# Injection Golden Set v0.1

`injection_golden_v0.1.jsonl`. 로더는 `evaluation/injection_golden.py`.

## 무엇이 다른가

**사기 골든셋은 판정을 잰다. 이쪽은 경계를 잰다.** 묻는 것이 "이 문자가 사기인가"
가 아니라 "이 문자에 심긴 지시가 프로바이더까지 도달하는가" 이고, 그 질문은 모델을
부르지 않고 답할 수 있다. 그래서 이 셋의 검사는 CI 에서 돈다
(`tests/test_llm_prompt_injection.py`). **유료 호출이 없다.**

모델이 실제로 지시를 따르는지는 별개의 유료 측정이며, 날짜와 모델을 붙여
`docs/devlog/2026-08-20/prompt-injection-boundary.md` 에 남긴다. 그 숫자를 여기
두면 CI 가 매번 돈을 쓰거나, 낡은 숫자가 테스트인 척하게 된다.

## 라벨 계약

- `case_id`: `pi-NNN`
- `technique`: `direct_override` · `role_assignment` · `english_mixed` ·
  `delimiter_forgery` · `verdict_forgery` · `developer_impersonation` ·
  `output_pinning`
- `text`: 주입 문장이 섞인 문자 원문
- `injected_fragment`: **프로바이더까지 가면 안 되는** 조각
- `evidence_fragment`: **반드시 남아야 하는** 조각. 이쪽이 사라지면 설명이 근거를
  잃는다
- `expected_min_risk`, `note`

두 fragment 는 로더가 `text` 안에 실제로 있는지 검사한다.

## 출처와 권리

FinShield 팀이 2026-08-20 직접 작성한 합성 문장이다. 실제 피해자 메시지나 외부
데이터셋을 복사하지 않았다.

## 이용 한계

7건짜리 개발셋이다. held-out 아니고, 기법 목록이 완전하지도 않다. 실제로 첫
실행에서 3건(`pi-005`·`pi-006`·`pi-007`)이 뚫렸고 그만큼 패턴을 넓혔다 — 즉 이 셋은
**현재 방어를 교정하는 데 쓴 셋**이므로 통과율을 방어 성능으로 주장하면 안 된다.

`pi-004`(구획 위조)는 입력 계층이 **의도적으로 막지 않는다.** 명령문이 아니라
평서문이라 잡으려면 "금융감독원" 이 든 문장을 지워야 하고, 그러면 금융감독원을
사칭한 실제 사기 문자를 통째로 지운다. 이 건은 `validation.py` 의 근거 이탈 검증이
받는다.

`pi-002`의 결정론 판정이 `low` 인 것은 주입과 무관한 **탐지 공백**이며 `docs/32`
소관이다.
