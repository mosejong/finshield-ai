# Product Filtering v0.1 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- 시작: 17:31 KST
- 담당 역할: backend
- 브랜치: `feature/product-filtering-v01`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-backend`
- 기준 `main`: `5a61caf5226ed46180755ffe28bee6d4d9ca7685`
- 상태: 구현·로컬·live 검증 완료, Draft PR 준비

## 목표와 비범위

- 목표: profile goal과 공식 purpose 원문만으로 보수적 후보 상태와 근거 제공
- 비범위: 적격성 확정, 금리·한도 parsing, LLM 추천, profile 저장, frontend 변경

## 구현

- `POST /api/v1/recommendations`
- goal-purpose pure rule과 명시적 manual-review reason
- 전체 snapshot 상태 집계와 결정론적 정렬·pagination
- 기존 product cache·identity·provenance 재사용
- 민감·미승인 profile 필드는 기존 `extra=forbid`로 거부

## 구현 중 수정

- 첫 관련 테스트: 17개 통과, 민감필드 테스트 1개 실패
- 키 없는 테스트 환경에서 FastAPI dependency가 body validation보다 먼저 503을
  반환한 것이 원인
- provider 상태와 body validation 경계를 분리하도록 해당 테스트에도 catalog stub을
  주입했으며 프로덕션 오류를 숨기거나 순서를 임의 변경하지 않음

## 보안·개인정보

- profile은 메모리 내 요청 계산에만 사용하고 저장·로그하지 않는다.
- 주민번호, 계좌 비밀번호, OTP, 카드번호를 허용하지 않는다.
- 공식 endpoint 외 fetch와 LLM 호출을 추가하지 않는다.
- 결과는 승인·적격성 보장이 아니라 목적 기반 후보임을 disclaimer로 명시한다.

## Live smoke

- 17:35 KST: 대표 사회초년생 주거 목표 profile을 최신월 325건에 적용
- `potential_match` 44, `mismatch` 280, `needs_review` 1
- 이는 규칙 실행 smoke이며 precision·recall 또는 추천 품질 평가가 아님
- 인증키, profile 원문, 상품 원문 전체 미출력·미저장

## 변경 파일

- `app/api/routes/recommendations.py`
- `app/domain/finance/product_filtering.py`
- `app/schemas/recommendation.py`
- `app/services/product_catalog.py`
- `app/services/product_recommendation.py`
- `app/main.py`
- `tests/test_product_filtering.py`
- `tests/test_recommendations_api.py`
- `docs/18-deterministic-product-filtering.md`
- 본 개발일지

## 현재 검증

- 전체 `pytest -q -p no:cacheprovider`: **126 passed**
- Python compile (`app`, `tests`, `scripts`): 통과
- `git diff --check`: 통과
- 다음: OpenAPI 회귀 보강 후 전체 재검증, PR CI

## 최종 로컬 검증

- 전체 pytest: **126 passed**
- compile, `git diff --check`: 통과
- OpenAPI request/response 계약: 통과
- 개인정보 저장·로그, LLM, 임의 URL fetch, frontend 변경 없음
