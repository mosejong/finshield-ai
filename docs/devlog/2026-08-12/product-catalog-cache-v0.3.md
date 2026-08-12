# Product Catalog v0.3 — In-memory TTL Cache 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- 시작: 16:58 KST
- 담당 역할: backend
- 브랜치: `feature/product-catalog-cache-v03`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-backend`
- 기준 `main`: `54b1f9376dcd2f2817133598aa907e0835e7bd4b`
- 상태: 구현·로컬 검증 완료, Draft PR 준비

## 목표

공식 금융상품의 최신 활성 기준월 전체 snapshot을 한 번 수집한 뒤 설정된 TTL 동안
프로세스 메모리에서 재사용한다. 목록 pagination은 snapshot에 대해 로컬에서 수행해
동일 사용 흐름의 provider 반복 호출을 줄인다.

## 비범위

- Redis나 영구 저장소 도입
- 상품명 기반 중복 제거
- 자격조건 판정·추천·정렬
- stale data 자동 fallback
- frontend 변경

## 관련 근거

- `docs/15-product-catalog-live-profile.md`: 최신월 325건, source ID 중복 0건
- cache identity는 provider, 기준월, active query를 보존한다.
- 금리·한도·상환방식 누락값은 추정하지 않는다.

## 구현 계획

1. 최신월 탐색과 전체 pagination 수집을 애플리케이션 서비스로 분리한다.
2. thread-safe TTL cache가 snapshot 단위로 한 번만 loader를 실행하게 한다.
3. 만료 전에는 동일 snapshot과 `fetched_at`을 재사용한다.
4. 만료 후 provider 실패를 빈 목록으로 바꾸지 않고 502 경계를 유지한다.
5. 단위·API·전체 회귀 테스트와 compile, diff 검사를 수행한다.

## 보안·개인정보

- 인증키를 cache key, 응답, 로그 또는 개발일지에 저장하지 않는다.
- 고정된 공식 endpoint만 호출한다.
- 사용자 개인정보를 수집하거나 저장하지 않는다.

## 구현 및 데이터 흐름

- `ProductCatalogSnapshotKey`: provider + 기준월 + active query + all-page scope
- `ProductCatalogSnapshotCache`: monotonic clock 기반 TTL과 thread lock 사용
- cache miss: 최신월 탐색 → 100건 단위 전체 수집 → 정규화 → 일관성 검증
- cache hit: provider 호출 없이 요청 page를 snapshot에서 slice
- catalog 응답에 `source_base_month`를 추가해 빈 페이지도 기준월을 보존

## 구현 중 검수·수정 이력

- 17:03 KST: 관련 테스트 30개 최초 통과
- PM 자체 리뷰에서 빈 local page는 상품 item이 없어 기준월 provenance를 확인할 수
  없는 문제 발견
- catalog 최상위 응답에 `source_base_month`를 추가하고 OpenAPI 회귀 테스트 보강
- `float("nan")`, `float("inf")`가 양수 비교를 통과할 수 있어 TTL 설정을 유한값으로
  제한
- provider `totalCount`, page number, row 기준월 불일치 시 cache 저장 전 실패하도록
  교정

## Live 검증

- 17:05 KST: 사용자 `.env`의 키를 출력하지 않고 공식 endpoint로 smoke test
- 기준월 `202607`, 전체 325건, 첫·두 번째 페이지 각 20건
- 첫 요청 provider 호출 6회, 두 번째 요청 후에도 누적 6회
- 두 응답의 `fetched_at` 동일
- 상품 원문 전체와 인증키는 출력·저장하지 않음

## 현재 검증 결과

- 관련 product/profile/cache 테스트: **35 passed**
- 전체 `pytest -q -p no:cacheprovider`: **111 passed**
- 알려진 경고: 기존 Starlette `TestClient` 사용 중단 예정 경고 1건
- 다음 검증: 보강 테스트 포함 전체 pytest, compile, diff, frontend CI

## 변경 파일

- `app/api/routes/products.py`
- `app/schemas/product.py`
- `app/services/product_catalog.py`
- `app/services/product_catalog_snapshot.py`
- `tests/test_product_catalog.py`
- `tests/test_product_catalog_cache.py`
- `docs/16-product-catalog-cache.md`
- 본 개발일지

## 최종 로컬 검증

- 전체 `pytest -q -p no:cacheprovider`: **111 passed**
- Python compile (`app`, `tests`, `scripts`): 통과
- `git diff --check`: 통과
- 실제 공식 API cache 재사용 smoke: 통과
- secret 검색: 실제 인증키·원문 dataset 미포함, 테스트용 고정 키만 존재
- frontend 파일 변경 없음; GitHub CI에서 build·typecheck·lint·test 재검증 예정

## 알려진 한계와 다음 작업

- cache는 단일 프로세스에만 존재하며 hit/miss 계측이 없다.
- provider 장애 시 stale snapshot 자동 반환은 하지 않는다.
- 다음 단계에서 source ID 유일성, 동일 source ID 충돌과 보수적 duplicate 정책을
  별도 PR로 구현한다.

## 커밋·PR

- 구현 커밋: `09a7880787503d206b733e03b5a828f3903b7a8c`
- PR: [#16 feat: cache latest product catalog snapshot](https://github.com/mosejong/finshield-ai/pull/16)
- PR 생성: 2026-08-12 17:05:58 KST (Draft)
- 상태: GitHub CI·PM 검수 중
