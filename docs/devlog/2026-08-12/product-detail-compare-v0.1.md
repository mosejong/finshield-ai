# Product Detail & Compare v0.1 개발일지

- 작업일: 2026-08-12 (KST)
- 담당: backend / frontend / PM
- 브랜치: `feature/product-detail-compare-v01`
- 기준 main: `b920e61`

## 목표와 범위

- 공식 상품 후보 단건 상세 화면
- 서로 다른 상품 2개를 동일 최신월 snapshot으로 비교
- 공식 원문 필드만 표시하고 적격성·금리 우열·추천 결론을 만들지 않음
- request 최소 입력은 source product ID 1개 또는 2개
- 3개 이상 비교, 저장된 비교 목록, 상품 신청 연동은 비범위

## 설계 결정

- source ID가 기준월을 포함하므로 상세 deep link는 최신 snapshot 교체 후 404가 될 수 있다.
  stale 상품을 새 상품으로 추정 매핑하지 않는다.
- 비교 service는 snapshot을 한 번만 읽어 두 상품의 provider·기준월·수집시각을 고정한다.
- 비교 대상 하나라도 없으면 부분 성공 대신 404를 반환한다.
- 프론트는 공식 금리·한도 문자열을 숫자로 파싱하지 않는다.

## 예정 변경

- backend product schema/service/routes와 API tests
- frontend product contracts/API/proxy
- `/products/[id]`, `/products/compare`, 후보 선택 UI
- architecture, 설계 문서, 본 개발일지

## 구현 중 테스트 경계 수정

- invalid request 테스트가 dependency 생성 단계의 provider 503을 먼저 만나 request 422를
  확인하지 못했다. provider stub override를 적용해 순수 request 계약 검증으로 분리했다.
- 운영 endpoint는 provider 미설정 시 기존과 같이 503을 유지한다.

## 구현

- latest snapshot 단건 source ID lookup과 정확한 404 경계
- 한 snapshot에서 요청 순서를 보존하는 2개 비교 response
- full official product zod 계약과 상세·비교 Next proxy
- 후보 카드의 상세 링크·최대 2개 비교 선택
- `/products/[id]` 전체 공식 원문 필드 표시
- `/products/compare` 항목별 2열 원문 비교
- 실브라우저 검수에서 동적 경로의 `%3A`가 프록시 매개변수에 남는 현상을 확인해, 프록시 입구에서 1회 디코딩 후 식별자 형식을 검증하도록 수정
- 실데이터 비교에서 공급자 HTML 문자 참조(`&#40;`, `&amp;`) 노출을 확인해, 원문의 의미를 바꾸지 않는 1회 문자 복원과 회귀 테스트 추가
- 누락 필드는 `확인 필요`, 실패는 빈 결과로 대체하지 않음

## 검증 결과

- Python 3.12.10 `pytest -q`: 150 passed, 기존 TestClient 중단 예정 경고 1건
- frontend `vitest`: 7 files / 21 tests passed
- `eslint`, `tsc --noEmit`, Next production build: 통과, 11개 page 생성
- 실제 공공데이터: 기준월 `202607`, 전체 325건에서 단건 상세와 2개 비교 확인
- 실제 사용자 흐름: 후보 2개 선택 → 비교 진입, 세 번째 checkbox 비활성화 확인
- 없는 source ID: 명시적 404 안내, 빈 결과나 부적격 판정으로 대체하지 않음
- 반응형: 375 / 768 / 1280px 가로 overflow 없음, 모바일 하단 navigation과 desktop side navigation 정상
- `git diff --check`: 통과

## PM 리뷰

- 20:18 PR #36 CI 4개(test 2, web 2) 통과 후 변경 계약과 전환 경계를 재검수했다.
- 같은 client page에서 다른 상품 ID로 이동할 때 이전 상세·비교 데이터가 잠깐 남지 않도록
  route 식별자를 component key로 사용해 새 로딩 상태로 remount하도록 보완했다.
- 비교 응답 provider는 상수 대신 실제 snapshot key에서 가져오도록 메타데이터 경계를 정리했다.
