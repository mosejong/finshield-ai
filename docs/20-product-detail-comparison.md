# 20. Product Detail and Comparison v0.1

## 목적

목표 기반 공식 상품 후보에서 사용자가 상품 1개를 자세히 읽거나 2개를 같은 기준월로
나란히 확인할 수 있게 한다. 적격성·승인 가능성·금리 우열을 판정하지 않고 공식 API의
원문 필드를 보존한다.

## backend 계약

### 단건 상세

`GET /api/v1/products/{source_product_id}`

- 최신 활성 snapshot을 한 번 읽어 source ID가 정확히 같은 상품 반환
- 없는 ID는 404, provider 장애는 502
- source ID는 `YYYYMM:sequence` 형식이며 기준월이 바뀐 옛 ID는 최신 snapshot에 없으면 404

### 2개 비교

`POST /api/v1/products/compare`

```json
{"product_ids": ["202607:1", "202607:2"]}
```

- 서로 다른 ID 정확히 2개만 허용
- snapshot을 한 번만 읽고 요청 순서대로 2개 반환
- 응답 최상위에 provider, source_base_month, fetched_at, source_reference, disclaimer 포함
- 하나라도 없으면 부분 결과 대신 404

한 요청에서 snapshot을 한 번만 읽기 때문에 TTL 만료 경계에서도 서로 다른 기준월의
상품을 한 비교 결과에 섞지 않는다.

## 화면 계약

- `/products/[id]`: 전체 공식 원문 필드와 출처
- `/products/compare?ids=...&ids=...`: 같은 snapshot의 2개 상품을 항목별로 비교
- `/products`: 후보 카드에서 상세 보기와 최대 2개 선택

비어 있는 공식 필드는 `확인 필요`로 표시하고 추정하지 않는다. 비교 화면은 금리·한도
문자열을 숫자로 변환하거나 정렬하지 않으며 “더 유리함” 같은 결론을 만들지 않는다.

## 보안·개인정보

- 비교 request는 source product ID 2개만 허용
- profile, 소득, 부채, 신용, 계좌정보를 상세·비교 API에 전송하지 않음
- provider 실패를 상품 없음이나 빈 비교 결과로 바꾸지 않음
- 공식 source URL은 backend 계약에서 받은 값만 새 탭으로 표시
