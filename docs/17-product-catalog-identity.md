# 17. Product Catalog Source Identity Integrity

## 목적

공식 최신월 snapshot에 포함된 상품이 동일한 source와 수집 경계를 공유하는지
검증하고, 이름만 같은 서로 다른 공식 상품을 임의로 합치지 않는다. 이 단계의
identity는 **단일 provider·단일 기준월 snapshot 내부**에서만 유효하다.

## Identity 정책

- 정책 코드: `provider_base_month_sequence`
- 공식 source ID: `basYm:snq`
- snapshot identity: provider + 기준월 + active query + all-page scope
- 상품명은 identity key가 아니다.
- source ID가 다르면 정규화 이름이 같아도 별도 상품으로 보존한다.
- 동일 source ID가 두 번 나오면 하나를 버리지 않고 불완전 snapshot으로 거부한다.

## Cache 저장 전 검증

모든 상품이 다음 조건을 만족해야 snapshot cache에 저장된다.

1. `provider`가 snapshot provider와 같다.
2. `source_base_month`와 source ID의 기준월이 snapshot 기준월과 같다.
3. source ID가 `YYYYMM:숫자` 형식이고 snapshot 내에서 유일하다.
4. `fetched_at`이 snapshot 수집시각과 같다.
5. `source_reference`가 고정된 공식 dataset URL과 같다.
6. active query 결과의 `active`가 명시적으로 `true`다.

하나라도 어긋나면 provider 오류로 처리해 기존 API 502 경계를 유지한다. 중복이나
불일치를 빈 목록, 일부 목록 또는 stale snapshot으로 바꾸지 않는다.

## API metadata

`GET /api/v1/products` 응답의 `identity`는 다음 정보를 페이지와 무관하게 제공한다.

```json
{
  "policy": "provider_base_month_sequence",
  "source_id_unique": true,
  "unique_source_id_count": 325,
  "normalized_name_duplicate_groups": 1,
  "name_only_dedup_applied": false
}
```

`normalized_name_duplicate_groups`는 trim, 연속 공백 축약, casefold만 적용한 관측
지표다. 상품 관계나 동일상품 여부를 판정하지 않는다.

## 2026-08-12 live 검증

- 기준월: `202607`
- 활성 상품: 325건
- 공식 source ID 유일: `true`
- unique source ID: 325개
- 정규화 동명 그룹: 1개
- name-only dedup: 미적용
- 인증키와 상품 원문 전체: 출력·저장하지 않음

## 한계와 다음 단계

- 다른 기준월의 동일 `snq`가 같은 상품을 뜻하는지 검증하지 않았다.
- 기관명 변경, 상품 개정, 재출시를 연결하는 cross-month lineage는 지원하지 않는다.
- fuzzy matching은 identity 또는 자동 병합 근거로 사용하지 않는다.
- 다음 단계는 이 보존된 공식 상품 원문에 FinancialProfile 조건을 적용하되 결과를
  `potential_match`, `mismatch`, `needs_review`로 제한하는 deterministic filtering이다.
