# 16. Product Catalog In-memory TTL Cache

## 목적

`GET /api/v1/products`가 같은 사용자 흐름에서 공식 provider를 페이지마다 반복
호출하지 않도록 최신 활성 기준월 전체를 하나의 snapshot으로 수집하고 일정 시간
재사용한다. 공식 원문과 provenance는 유지하며 누락값을 보정하거나 상품을 추천하지
않는다.

## 데이터 흐름

```text
GET /api/v1/products?page_no=N&page_size=M
  → current KST month부터 최신 활성 기준월 탐색
  → basYm exact query로 최신월 전체 pagination 수집
  → provider 응답 정규화와 기준월 일관성 검증
  → provider + base month + active query + all-page scope snapshot
  → process-local TTL cache
  → 요청 page_no/page_size로 로컬 pagination
```

최초 요청과 TTL 만료 후 첫 요청만 provider를 호출한다. 동시에 여러 요청이 cache
miss를 만나면 하나의 요청만 snapshot을 갱신하고 나머지는 같은 결과를 기다린다.

## 설정

| 환경변수 | 기본값 | 허용 범위 | 의미 |
|---|---:|---:|---|
| `PRODUCT_CATALOG_CACHE_TTL_SECONDS` | 300 | 0보다 큰 유한 실수 | snapshot 재사용 시간 |
| `PRODUCT_CATALOG_LOOKBACK_MONTHS` | 36 | 0~120 정수 | 최신 활성 기준월 탐색 범위 |

잘못된 설정은 시작 후 첫 상품 API 접근에서 503으로 명시된다. 인증키와 cache 설정은
프로세스 재시작 시 다시 읽는다.

## 응답과 provenance

- catalog 응답의 `source_base_month`로 빈 페이지에서도 snapshot 기준월을 확인한다.
- `fetched_at`은 실제 snapshot 첫 데이터 페이지 수집 시각이며 cache hit에서 유지된다.
- 각 상품은 `provider`, `source_product_id`, `source_base_month`, `fetched_at`,
  `source_reference`를 계속 보존한다.
- cache identity에 인증키나 사용자 입력은 포함하지 않는다.

## 실패 정책

- 갱신 실패를 빈 상품목록이나 적격 상품 없음으로 바꾸지 않고 기존 502 경계를
  유지한다.
- 만료된 snapshot을 자동 반환하지 않는다. freshness 상태를 응답 계약으로 명시하기
  전까지 stale fallback은 사용하지 않는다.
- 수집 중 `totalCount`, page number, 상품 기준월이 달라지면 불완전 snapshot을
  cache하지 않는다.

## 2026-08-12 live 검증

- 공식 기준월: `202607`
- 최신월 활성 상품: 325건
- 첫 목록 조회 provider 호출: 6회
  - 현재월·최신월 탐색 2회
  - 최신월 100건 단위 전체 수집 4회
- 같은 service의 두 번째 페이지 조회 후 누적 provider 호출: 6회
- 두 응답의 `fetched_at`: 동일
- 인증키와 325건 원문 전체: 출력·저장하지 않음

## 한계와 다음 단계

- 프로세스별 메모리 cache라 다중 worker 사이에서 공유되지 않는다.
- 재시작 후 첫 요청은 cold start provider latency를 부담한다.
- hit/miss와 provider p50/p95 계측은 아직 없다.
- Redis는 다중 worker·트래픽 측정으로 필요가 입증될 때만 검토한다.
- 다음 단계는 source identity 무결성 검증과 보수적 중복 처리다. 상품명만으로는
  절대 병합하지 않는다.
