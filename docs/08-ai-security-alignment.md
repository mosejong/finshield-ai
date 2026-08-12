# 08. AI Security Alignment

## Direction
FinShield의 AI 보안은 장식 기능이 아니라 금융 AI 서비스의 안전설계에 연결한다.

### AI-enabled financial social engineering
생성형 AI는 자연스러운 사칭 메시지, 개인화 spear phishing, 반복/대량 공격 자동화, 음성/이미지 사칭에 악용될 수 있다는 위협 모델을 조사한다.

### AI-service security
FinShield 자체도 다음 위협을 방어해야 한다.
- prompt injection
- retrieval poisoning
- unsafe URL fetching / SSRF
- PII leakage
- hallucinated financial guidance
- tool/API misuse
- log leakage
- excessive data retention

## Product security principles
1. LLM은 대출 적격성/위험판정의 단독 결정자가 아니다.
2. 공식 금융상품 데이터와 대응 절차를 source of truth로 둔다.
3. 사용자가 입력한 URL을 서버가 그대로 요청하지 않는다.
4. 금융프로필 최소수집 원칙을 적용한다.
5. 원문 메시지/민감정보 저장 여부를 명시한다.
6. 모델 출력은 schema로 검증한다.
7. 응답에 근거와 불확실성을 표시한다.
8. 공격 입력/edge case golden set을 관리한다.

## Evaluation candidates
- prompt injection success rate
- unsafe instruction following rate
- sensitive-field leakage rate
- unsupported financial claim rate
- scam/risk recall
- false-positive rate
- signal extraction F1
- citation coverage/source correctness
