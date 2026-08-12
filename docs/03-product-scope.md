# 03. Product Scope

## MVP — candidate

### Input
- 의심스러운 문자/메신저 텍스트
- URL (선택)
- 사용자 유형
- 사용자가 이미 취한 행동

### Analysis
1. 위험 표현/행동 요구 추출
2. 사기 유형 후보
3. URL/도메인 feature (가능한 범위)
4. 사용자 상태 기반 scenario
5. 위험도와 confidence

### Output
- 위험 수준
- 위험 신호 목록
- 왜 위험한지
- 현재 단계에서 하지 말아야 할 행동
- 확인해야 할 공식 경로
- 근거 출처

## Candidate scenario states

- `received_only`
- `clicked_link`
- `shared_personal_info`
- `shared_account_access`
- `installed_app`
- `received_unknown_money`
- `transferred_money`

## Guardrails

- 확정적으로 범죄라고 단정하지 않기
- 법률판단을 생성하지 않기
- 공식 기관의 대응 가이드를 우선하기
- 위험한 URL을 서버가 무분별하게 직접 방문하지 않기
- 개인정보 저장 최소화
- 원문 메시지 저장 여부를 명시적으로 설계하기

## Stretch goals

MVP가 안정화된 이후에만:
- STT 통화 분석
- 음성 deepfake signal 연구
- 이메일 첨부파일 metadata 분석
- 브라우저/모바일 공유 기능
- 사용자별 금융안전 교육
