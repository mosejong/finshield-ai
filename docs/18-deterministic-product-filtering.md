# 18. Deterministic Product Filtering v0.1

## 목적

FinancialProfile의 `goal`과 공식 상품의 `purpose_text`를 결정론적으로 비교해 상품을
`potential_match`, `mismatch`, `needs_review`로 분류한다. 이 결과는 적격성·승인·금리
추천이 아니며, 자유형 자격 원문을 임의 해석하지 않는다.

## API

`POST /api/v1/recommendations?page_no=1&page_size=20`

- request: filtering에 실제 사용하는 `goal` 하나만 전송
- response: snapshot provider·기준월, 전체 상태 집계, 페이지 결과, disclaimer
- 소득·부채·신용·연령 등 사용하지 않는 profile 정보는 서버로 전송하지 않는다.

## v0.1 규칙

- 공식 `purpose_text`에 goal별 검토된 토큰이 있으면 `potential_match`
- 공식 용도가 있지만 goal 범주와 다르면 `mismatch`
- 공식 용도가 없거나 goal이 `other`면 `needs_review`
- 모든 결과에 나이·소득·신용·지역 등 상세 자격의 취급기관 확인 필요를 명시
- 상태 순서는 `potential_match → needs_review → mismatch`, 같은 상태에서는 공식
  source ID 순서로 고정한다.

goal token은 주거, 긴급·생계, 대환, 생활, 창업·사업, 차량, 자산형성 범주만
사용한다. substring 규칙은 bootstrap이며 공식 용도 필드 밖의 상품명·상세조건을
확대 해석하지 않는다.

## 안전 경계

- `potential_match`는 자격 충족이 아니라 용도 후보라는 뜻이다.
- 누락값을 0이나 불일치로 바꾸지 않는다.
- 공식 자격 원문에서 숫자·나이·신용점수를 임의 parsing하지 않는다.
- LLM을 사용하지 않는다.
- 주민번호·계좌 비밀번호·OTP 등 스키마 밖 필드는 422로 거부한다.
- provider 오류는 빈 결과가 아니라 502로 유지한다.

## 다음 단계

- 실제 325건 상태 분포와 persona별 golden set을 측정한다.
- 공식 자격 필드를 구조화하려면 별도 규칙·근거·오류율 평가가 필요하다.
- frontend는 이 API의 상태와 reason을 그대로 표시하고 재계산하지 않는다.

## 2026-08-12 live smoke

대표 사회초년생 주거 목표 프로필 1건을 최신월 325개에 적용한 집계다. 이는 정확도
평가나 추천 성과가 아니라 규칙 실행 확인이다.

- `potential_match`: 44건
- `mismatch`: 280건
- `needs_review`: 1건
- 기준월: `202607`

실제 인증키, 입력 profile 원문과 상품 원문 전체는 출력·저장하지 않았다.
