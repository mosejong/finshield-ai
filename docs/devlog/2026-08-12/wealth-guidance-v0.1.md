# Wealth Guidance v0.1 개발일지

- 작업일: 2026-08-12 (KST)
- 담당: backend / frontend / PM
- 브랜치: `feature/wealth-guidance-v01`
- 기준 main: `b9101e8`

## 목표와 범위

- 재테크 관심 사용자를 위한 공식 근거 기반 기초 교육 화면
- 소득·지출·저축·투자·자산·부채 점검에서 투자위험 학습까지 4단계
- backend 정적 계약과 source 무결성 검증
- profile·보유종목·계좌·거래내역 입력 없음
- 종목·상품·매수·매도·수익률 추천 없음

## 공식 조사

- 서민금융진흥원 재무상담은 소득·지출, 저축·투자, 자산·부채를 함께 점검한다.
- 비대면 금융교육은 재무설계, 저축·소비, 부채관리, 신용관리,
  자산형성·투자를 별도 교육 주제로 제공한다.
- 신용·부채관리 컨설팅은 소비·재무상황과 부채현황 점검, 장기 관리 안내를 제공한다.
- 전국투자자교육협의회는 투자자 자기보호와 자기판단·책임을 설립 목적으로 두며
  분산투자 교육에서 집중 위험을 설명한다.
- 화면 검수 중 원금손실·비용 질문에 더 직접적인 투자자교육협의회의 금융상품
  설명의무 교육을 추가해 문장별 근거 강도를 높였다.

## backend 구현

- versioned JSON source와 Pydantic response 계약
- module 순서·code, source ID·URL·검토일, module-source 지지 관계 검증
- `GET /api/v1/guidance/wealth`
- 입력과 outbound fetch 없음

## frontend 구현

- `GET /api/proxy/guidance/wealth` same-origin proxy와 zod 계약
- `/learn/wealth` 4단계 교육·점검 질문·다음 학습 행동·공식 source 표시
- `/products`에 대출 비교와 나란히 교육 진입점 추가
- 요청 body와 profile 전송 없음
- 실패를 빈 가이드나 안전 판정으로 바꾸지 않음

## PM 화면 검수 교정

- 한 module에 같은 기관의 source가 여러 개면 링크명이 모두 `기관명 근거`로 같아
  목적지를 구분하기 어려웠다.
- 각 링크를 실제 공식 자료 제목으로 표시해 시각 사용자와 스크린리더 모두 목적지를
  구분할 수 있도록 교정했다.

## 최종 검증

- Python 3.12.10 `pytest -q`: **143 passed**
- Python compileall: 통과
- Vitest: **6 files, 18 passed**
- ESLint·TypeScript·Next production build: 통과
- build route: `/api/proxy/guidance/wealth`, `/learn/wealth` 포함
- 금지 스타일 패턴: 0건
- live Next → FastAPI: 4개 module, 6개 공식 source, 검토일 표시 확인
- `/products`의 `/learn/wealth` 진입점 확인
- 375 / 768 / 1280px: 가로 overflow 없음, 1280px SideNav 확인
- browser console error: 0건
- 외부 링크는 자료 제목으로 구분되고 새 탭·`noreferrer` 경계를 유지
- `git diff --check`: 통과

## PR 및 PM 검수

- Draft PR: [#34 feat: add evidence-backed wealth guidance](https://github.com/mosejong/finshield-ai/pull/34)
- GitHub Actions backend `test`, frontend `web`: 통과
- PM 근거 검수: 교육 문장별 source 지지와 원금손실·비용 직접 근거 확인
- PM 안전 검수: 개인 데이터 입력 없음, 투자상품·매매·수익률 추천 없음
- PM 접근성 검수: 동일 기관의 여러 링크를 공식 자료 제목으로 구분
- 차단 이슈: 없음

## 구현 중 수정

- 금지 문구 회귀 테스트의 module별 문자열 목록을 바로 `join`해 TypeError가 발생했다.
- module 안의 문자열을 먼저 평탄화하도록 테스트 구현을 교정했다. 서비스 계약이나
  응답 데이터 문제는 아니었다.
