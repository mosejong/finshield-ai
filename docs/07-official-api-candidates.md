# 07. Official API Candidates

> 조사일: 2026-08-11

## MVP 우선 후보

### 서민금융진흥원 대출상품한눈에
- REST/XML
- 무료, 개발 자동승인
- 상품명, 한도, 금리구분, 대출용도, 기간, 취급기관, 지원대상 등
- 후보 역할: 목적/직업/소득조건 기반 상품 탐색과 비교

Base: `apis.data.go.kr/B553701/LoanProductSearchingInfo`
Endpoint: `GET /LoanProductSearchingInfo/getLoanProductSearchingInfo`

### 금융위원회 서민금융상품기본정보
- REST JSON/XML
- 무료, 개발 자동승인
- 상품유형, 상품명, 금리, 한도, 지원대상, 상환방식, 취급기관

Base: `apis.data.go.kr/1160100/service/GetSmallLoanFinanceInstituteInfoService`
Endpoint: `GET /getOrdinaryFinanceInfo`

### 서민금융진흥원 서민대출상품 취급기관 정보
- 실제 취급기관 연결용 후보

## Strategy
User Financial Profile -> Eligibility pre-filter -> Official APIs -> normalize/deduplicate -> Product catalog -> deterministic filter -> Loan simulator -> LLM explanation.

## TODO
- [ ] API 활용신청
- [ ] 실제 응답 필드 샘플 저장
- [ ] 중복률/신선도 비교
- [ ] eligibility 판정 가능한 필드 확인
- [ ] 주택금융/청년주거 API 조사
- [ ] 소상공인 정책자금 API 조사
