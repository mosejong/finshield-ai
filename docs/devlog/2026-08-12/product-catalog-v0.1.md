# Official Product Catalog v0.1 개발일지

## 작업 정보

- 작업일: 2026-08-12 (KST)
- 시작: 15:48 KST
- 담당 역할: backend
- 브랜치: `feature/product-catalog-v01`
- worktree: `C:\Users\user\Documents\Codex\finshield-ai-backend`
- 기준 `main`: `38110e92d97232d5d023461bf845d8c34e6a61f7`
- 상태: Draft PR 생성, CI·PM 리뷰 중

## 목표

금융위원회 `서민금융상품기본정보`를 호출하는 고정 공식-provider 경계와
`GET /api/v1/products` 정규화 계약을 구현한다. 상품명·금리·한도·자격조건은
공식 응답 원문을 보존하고 누락값을 추정하지 않는다.

## 비범위

- 공공데이터포털 활용신청과 실제 서비스키 발급
- live 응답 검증과 운영 트래픽 설정
- 상품 캐시·중복 제거·사용자 프로필 기반 적격성 판정
- 프론트엔드 상품 탐색·비교 화면

## 공식 근거와 확인 결과

- 공공데이터포털 데이터셋:
  `https://www.data.go.kr/data/15094787/openapi.do`
- 고정 endpoint:
  `https://apis.data.go.kr/1160100/service/GetSmallLoanFinanceInstituteInfoService/getOrdinaryFinanceInfo`
- 포털 확인일: 2026-08-12
- 공식 페이지 기준 JSON+XML, 무료, 개발·운영 자동승인, 실시간 업데이트,
  개발계정 트래픽 10,000건
- 공식 활용가이드 DOCX에서 요청 21개·응답 52개 필드와 XML 예제를 구조적으로
  확인했다. 가이드 샘플 기준월은 202202이므로 실제 필드·신선도는 키 발급 후
  live 응답으로 다시 확인해야 한다.
- LibreOffice가 없어 가이드의 페이지 렌더는 수행하지 못했으며, 문서의 표 7개와
  원문 XML을 구조적으로 추출해 필드명을 확인했다.

## 설계 결정

- 호출 대상은 코드에 정의한 단일 HTTPS 공식 endpoint로 고정한다.
- `serviceKey`는 `PUBLIC_DATA_SERVICE_KEY` 환경변수에서만 읽고 응답·로그에 노출하지 않는다.
- `resultType=json`, `prdExisYn=Y`를 명시한다.
- `basYm:snq`를 provider 내 `source_product_id`로 사용한다.
- 금리·한도·기간·자격조건은 숫자로 추정하지 않고 `*_text`로 보존한다.
- provider 키 누락은 503, 기관·스키마 오류는 502로 명시하며 빈 상품 목록으로 바꾸지 않는다.
- 공식 응답의 HTML 연락처·링크 필드는 v0.1 API에 노출하지 않는다.

## 구현 내용

- 공식 endpoint·요청 파라미터·timeout을 캡슐화한 provider client
- 응답 header·pagination·item shape의 명시적 검증
- 금리·한도·기간·자격조건 원문을 유지하는 정규화 schema
- `GET /api/v1/products`와 1~100건 pagination 계약
- 키 누락 503, 기관·응답 스키마 실패 502 및 내부 오류문 비노출
- 실제 키를 제외한 `.env.example` 설정 안내

## 변경 파일

- `.env.example`
- `app/clients/public_data_products.py`
- `app/domain/finance/product_catalog.py`
- `app/schemas/product.py`
- `app/services/product_catalog.py`
- `app/api/routes/products.py`, `app/main.py`
- `tests/test_product_catalog.py`
- 본 개발일지

## 검증 결과

- 15:51 KST: 신규 계약 테스트 7개 중 6개 통과, URL 타입과 문자열을 직접
  비교한 테스트 1개 실패
- 15:51 KST: 실제 JSON 계약은 문자열임을 확인하고 테스트에서 URL을 명시적으로
  문자열화해 교정
- 15:52 KST: provider 빈 items, Pydantic 스키마 오류→502, 내부 오류문 비노출
  회귀 테스트 추가
- 15:53 KST: 전체 `pytest -q` **85 passed**, 기존 Starlette `TestClient`
  사용 중단 예정 경고 1건
- Python compile: 통과
- `git diff --check`: 통과
- `PUBLIC_DATA_SERVICE_KEY`: 로컬 미설정 확인, live API 테스트 미실행

## 보안·개인정보

- 사용자 제공 URL이나 임의 URL을 fetch하지 않는다.
- 서비스키와 원문 사용자 금융 프로필을 기록하지 않는다.
- 외부 응답의 HTML 링크를 클라이언트에 전달하지 않는다.

## 커밋·PR

- 15:54 KST: 구현·테스트·개발일지 커밋 및 push
- 커밋: `462afb092ee52b95e11bf8e9e5b17bf40c9ba868`
- push: `feature/product-catalog-v01`
- PR: [#7 feat: add official product catalog adapter](https://github.com/mosejong/finshield-ai/pull/7)
- PR 생성: 2026-08-12 15:55:14 KST (Draft)
