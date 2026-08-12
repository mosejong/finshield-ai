# Product Catalog v0.2 — 1단계 Live Data Profile 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- 시작: 16:30 KST
- 담당 역할: backend
- 브랜치: `feature/product-catalog-v02`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-backend`
- 기준 `main`: `54923f52be629e05d7a7f19f34a3a56c28000f19`
- 종료: 16:43 KST
- 상태: 완료 — PR #13 병합 및 PM 문서 통합

## 단계 목표

캐시·중복 제거·추천 규칙을 설계하기 전에 최신 공식 상품 데이터의 실제 품질을
재현 가능한 명령으로 측정한다. 이번 단계에서는 공개 API 계약과 프론트엔드를
변경하지 않는다.

## 사전 확인

- 전체 활성 이력: 9,316건
- 최신 기준월: `202607`
- 최신 기준월 활성 상품: 325건
- 전체 이력을 매번 수집하지 않고 최신 기준월만 profiling한다.

## 구현 범위

- 현재 KST 기준월부터 역순으로 최신 데이터 월 탐색
- 최신 월을 100건 단위 pagination으로 완전 수집
- 핵심 필드 누락 건수·비율
- source ID, 정규화 상품명, 보수적 상품 signature 중복
- 상품 구분·세부 구분·제공기관·용도 상위 분포
- JSON stdout 출력, 인증키·원문 전체 저장 금지

## 누락과 중복 정의

- 누락: `None`, 공백, `NULL`, `none`, `-`를 trim 후 동일하게 처리
- source ID: `basYm:snq`
- 정규화 상품명: trim, 연속 공백 축약, casefold
- signature: 상품명 + 제공기관 + 상품구분2 + 취급기관 정규화 조합
- 이 signature는 분석용 후보이며 아직 영구 dedup key로 확정하지 않는다.
- 동명 그룹은 최대 5개까지 source ID·제공기관·취급기관 차이만 보고한다.

## 변경 파일

- `app/clients/public_data_products.py`: 내부 `base_month` query 지원
- `scripts/profile_product_catalog.py`: live profiling CLI
- `scripts/__init__.py`: module 실행 경계
- `tests/test_product_catalog.py`
- `tests/test_product_catalog_profile.py`
- `docs/15-product-catalog-live-profile.md`: 공식 snapshot 품질 보고서
- 본 개발일지

## 검증 계획

- 최신월 탐색·연도 경계·pagination·누락·중복 단위 테스트
- 실제 325건 live profile 실행
- 전체 `pytest -q`, compile, `git diff --check`

## 구현 중 수정 이력

- 16:34 KST: 첫 단위 테스트 수집 단계에서 Windows Python에 IANA `tzdata`가 없어
  `ZoneInfo("Asia/Seoul")` 로딩 실패
- 한국은 DST가 없으므로 추가 의존성을 설치하지 않고 표준 라이브러리 고정
  `UTC+09:00` timezone으로 교정
- 16:37 KST: 첫 커밋 직전 `git diff --cached --check`가 품질 보고서의 Markdown
  강제 줄바꿈 공백 2줄을 지적했으나 PowerShell 명령 연결로 커밋이 계속 진행됨
- 해당 2줄을 일반 blockquote 문단으로 즉시 교정하고 별도 수정 커밋으로 추적
- 16:41 KST PM 리뷰: `--base-month`가 6자리만 검사해 `202699`도 허용하는 문제 발견
- API 호출 전에 실제 월 범위 01~12를 검증하도록 교정하고 5개 회귀 테스트 추가
- 16:43 KST: PM 재검수에서 변경 범위가 계획한 7개 파일로 한정되고 공개 API route와
  frontend가 변경되지 않았음을 확인
- 최신 head `1d121be0a01a12a880cf6da4e0fe728a9b66a05b` 기준 GitHub CI의
  backend `test` 2개와 frontend `web` 2개가 모두 통과

## 보안·개인정보

- 서비스키를 출력하거나 보고서에 저장하지 않는다.
- 공식 endpoint만 호출하며 사용자 입력 URL은 사용하지 않는다.
- 사용자 금융 프로필이나 개인정보를 처리하지 않는다.

## 다음 단계 진입 조건

- live 325건 수집 완료
- 품질 지표를 개발일지에 기록
- PM이 cache key·TTL·dedup 기준 설계 착수를 승인

## Live 측정 결과

- 16:34 KST: 최신월 탐색 2회 + 최신월 pagination 4회로 325건 수집
- source ID 누락·중복: 0건
- 상품명 누락: 0건, 정규화 동명상품 1그룹 2행
- 동명상품은 강원·경남신용보증재단의 서로 다른 공식 상품으로 확인
- 보수적 signature 중복: 0건, 상품명 자동 dedup 금지 결정
- 금리 79건(24.31%), 상환방법 52건(16.00%), 용도 28건(8.62%) 누락
- 상품구분2 325건(100%) 누락으로 filtering·dedup key 사용 금지
- 상세 결과와 다음 단계 제약은 `docs/15-product-catalog-live-profile.md`에 기록

## 최종 검증 결과

- 프로파일러·client 관련 테스트: **22 passed**
- 전체 `pytest -q -p no:cacheprovider`: **97 passed**
- 알려진 경고: 기존 Starlette `TestClient` 사용 중단 예정 경고 1건
- Python compile (`app`, `tests`, `scripts`): 통과
- `git diff --check`: 통과
- 키 출력·저장 패턴 검토: 집계 JSON만 stdout, 실제 키·원문 전체 미기록
- 공개 API route와 frontend 변경 없음

## 커밋·PR

- 구현 커밋: `9abce68` (`feat: add product catalog live profiler`)
- whitespace 교정 커밋: `fcd31b5de5f505bad348a89799a84086f8ddfba0`
- push: `feature/product-catalog-v02`
- PR: [#13 feat: add product catalog live profiler](https://github.com/mosejong/finshield-ai/pull/13)
- PR 생성: 2026-08-12 16:38:59 KST (Draft)
- PM 검수 시점 head: `1d121be0a01a12a880cf6da4e0fe728a9b66a05b`
- GitHub CI: `test` 2개, `web` 2개 통과
- Ready 전환: 2026-08-12 16:44 KST
- 병합: 2026-08-12 16:45:16 KST
- 병합 커밋: `c907e7270aff7924e131ce97da03bf674bc76906`
