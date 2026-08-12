# Recommendation Minimum Input 교정 개발일지

- 작업일: 2026-08-12 (KST)
- 담당: backend / PM privacy review
- 브랜치: `fix/recommendation-minimum-input`
- 기준 main: `e5473130d0e38f72389ba460e33b419be416da39`

## 원인과 결정

products frontend 연결 전 검수에서 v0.1 규칙은 `goal`만 사용하지만 request가 전체
FinancialProfile을 요구해 소득·부채 등 불필요한 정보까지 전송하는 문제를 발견했다.
최소수집 원칙에 따라 request를 `{ "goal": ... }`로 축소한다.

## 영향

- 아직 frontend가 연결되지 않은 신규 API라 사용자 호환성 영향 없음
- filtering 상태·규칙·provider 오류 경계는 변경 없음
- 스키마 밖 `otp` 등은 계속 422로 거부
- profile session 데이터는 브라우저에 남고 goal만 전송 예정
