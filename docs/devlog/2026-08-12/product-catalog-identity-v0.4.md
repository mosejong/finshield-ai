# Product Catalog v0.4 — Source Identity Integrity 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- 시작: 17:19 KST
- 담당 역할: backend
- 브랜치: `feature/product-catalog-identity-v04`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-backend`
- 기준 `main`: `452debaf228ad50931f6aded5a6bda2252f248f1`
- 상태: 구현·로컬·live 검증 완료, Draft PR 준비

## 목표

- snapshot 내부 공식 `provider + basYm:snq` identity의 유일성을 검증한다.
- 상품별 provider, 기준월, 수집시각, source reference 일관성을 검증한다.
- 정규화 이름이 같아도 source ID가 다르면 별도 상품으로 보존한다.
- API 응답에 적용한 identity 정책과 동명상품 그룹 수를 명시한다.

## 비범위

- 서로 다른 source ID 자동 병합
- 월간 source ID 안정성 또는 상품 계보 판정
- fuzzy name matching
- 추천·자격 판정·순위 계산
- frontend 변경

## 구현 계획

1. pure domain identity audit를 추가한다.
2. snapshot cache 저장 전에 audit를 통과시킨다.
3. source ID 중복과 provenance 불일치는 provider 오류로 차단한다.
4. 동명상품은 보존하고 집계 metadata만 catalog 응답에 추가한다.
5. live 325건의 유일성·동명 1그룹을 재검증한다.

## 보안·개인정보

- 공식 상품 공개 정보만 처리하며 사용자 개인정보는 사용하지 않는다.
- 인증키는 identity, audit 결과, 응답 또는 로그에 포함하지 않는다.
- 외부 URL fetch를 추가하지 않는다.

## 구현 및 데이터 흐름

- `app/domain/finance/product_identity.py`에 pure identity audit 추가
- cache loader가 정규화 후, cache 저장 전에 audit 실행
- 공식 source ID 형식·유일성, provider, 기준월, 수집시각, source reference, active
  query 일관성을 검증
- catalog 응답에 snapshot 전체 identity metadata 추가
- 동명상품을 제거하거나 병합하는 코드는 추가하지 않음

## API 결정

`GET /api/v1/products`에 다음 `identity` 객체를 추가한다.

- `policy`: `provider_base_month_sequence`
- `source_id_unique`: 항상 audit 통과를 의미하는 `true`
- `unique_source_id_count`: 전체 snapshot 기준
- `normalized_name_duplicate_groups`: 전체 snapshot 기준 관측값
- `name_only_dedup_applied`: 항상 `false`

## 구현 중 검수

- 동일 source ID는 내용이 같아도 provider pagination 손실 가능성이 있으므로 전체
  snapshot을 거부하도록 결정
- 동명상품은 공식 source ID가 다르면 모두 보존하고 group count만 노출
- identity를 여러 기준월에 걸친 영구 상품 ID로 설명하지 않도록 문서 범위를
  단일 provider·단일 기준월 snapshot으로 제한

## Live 검증

- 17:22 KST: 공식 API 집계 smoke test
- 기준월 `202607`, 활성 325건, unique source ID 325개
- 정규화 동명 그룹 1개, name-only dedup 미적용
- 실제 인증키와 325건 원문 전체는 출력·저장하지 않음

## 변경 파일

- `app/domain/finance/product_identity.py`
- `app/schemas/product.py`
- `app/services/product_catalog.py`
- `app/services/product_catalog_snapshot.py`
- `tests/test_product_catalog.py`
- `tests/test_product_catalog_cache.py`
- `tests/test_product_catalog_identity.py`
- `docs/17-product-catalog-identity.md`
- 본 개발일지

## 다음 검증

- 전체 pytest
- Python compile
- `git diff --check`
- GitHub backend·frontend CI

## 최종 로컬 검증

- 관련 identity/product/cache 테스트: **35 passed**
- 전체 `pytest -q -p no:cacheprovider`: **120 passed**
- 알려진 경고: 기존 Starlette `TestClient` 사용 중단 예정 경고 1건
- Python compile (`app`, `tests`, `scripts`): 통과
- `git diff --check`: 통과
- 개인정보·secret·임의 URL fetch 추가 없음

## 커밋·PR

- 구현 커밋: `c66c8d395b3a31692829f5ede52a02bbc0d5fcf9`
- PR: [#19 feat: enforce product source identity](https://github.com/mosejong/finshield-ai/pull/19)
- PR 생성: 2026-08-12 17:23:42 KST (Draft)
- 상태: PM 검수·GitHub CI 통과, Ready 전환 대기

## PM 최종 검수

- 계획한 domain·service·schema·tests·해당 docs 9개 파일만 변경
- 최신 head: `de9e104c3ddb8f429c6d459821f64847c9cd335b`
- GitHub CI: backend `test` 2개, frontend `web` 2개 통과
- source ID 중복은 전체 실패, 동명·다른 ID는 보존하는 정책 재확인
- snapshot-scoped identity를 영구 cross-month ID로 표현하지 않음
- secret·개인정보·임의 URL fetch·frontend 변경 없음
- 차단 이슈 없음
