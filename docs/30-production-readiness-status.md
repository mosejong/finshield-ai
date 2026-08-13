# Production Readiness Status — Phases 1–3

기준일: 2026-08-13  
기준 main: `b9906cd9d5990f50b73f571e49cc3d61ce83f6bf`

## 1차 — 데이터·운영·보안 경계

| 영역 | 상태 | 증거 |
|---|---|---|
| 익명 session/profile 소유권 | 완료 | docs 23, PR #43 |
| 익명 계정 삭제·만료 정리 | 완료 | docs 24, PR #46·#47 |
| Docker·PostgreSQL·migration·backup/restore | 완료 | docs 25, PR #48·#49 |
| HTTP 보안 헤더·same-origin·trusted host·HTTPS 구성 | 완료 | docs 26, PR #50·#51 |
| privacy-safe request log·request ID·health·metrics | 완료 | docs 27, PR #52·#53 |
| 실제 공개 도메인·DNS·인증서 외부 검증 | 미완료 | public deployment 필요 |

## 2차 — Fraud 평가·대회 증거

| 영역 | 상태 | 증거 |
|---|---|---|
| 합성 golden set | 완료 | 61건, 모든 UserState 최소 3건 |
| 재현 benchmark·CI gate | 완료 | PR #54, docs 28 |
| 데이터 출처·라벨·SHA-256 | 완료 | `evaluation/data/README.md`, 결과 JSON |
| 대회 claim·한계 문서 | 완료 | docs 29 |
| 독립 held-out v0.2 | 미완료 | v0.1은 튜닝에 사용한 개발셋 |
| 고정 LLM-only·Hybrid 비교 | 미완료 | model·prompt·provider 계약과 구현 필요 |

합성 bootstrap 기준 Scenario Engine v0.1은 precision 0.973684, recall 0.948718,
F1 0.961039, FPR 0.045455다. 이 수치는 실서비스 일반화 성능이 아니다.

## 3차 — 프론트 접근성·세션 UX

| 영역 | 상태 | 증거 |
|---|---|---|
| skip link·main focus·focus-visible | 완료 | PR #56 |
| status·aria-busy·폼 설명 연결 | 완료 | PR #56 |
| reduced motion | 완료 | PR #56 |
| 구조적 접근성 회귀 | 완료 | frontend 47 tests |
| 375·768·1280 다크 화면·nav·overflow | PM 확인 | frontend devlog |
| 스크린리더·정량 AA·라이트·iOS Safari | 미완료 | 실기기·도구 검수 필요 |
| 브라우저 submit/session 전체 E2E | 부분 | unit/API는 통과, 인앱 브라우저 이벤트 제한 |

## 검증 기준

- Python: 209 passed, 1 skipped, 기존 TestClient 경고 1건
- frontend: 11 files, 47 tests passed
- Next production build, TypeScript, lint: 통과
- Linux GitHub Actions: test·web·container-runtime 통과

## 공개 프로덕션 전 차단 항목

1. 실제 도메인·DNS·TLS 인증서로 공개 배포하고 reverse proxy·secure cookie를 검증한다.
2. 독립 held-out fraud 데이터와 사전 고정된 평가 계약으로 다시 측정한다.
3. 실제 스크린리더, WCAG AA 대비, 라이트 모드, iOS Safari를 검수한다.
4. provider latency·error와 공개 환경 동시성·SLO를 측정한다.
5. 로그인 기반 복구를 도입할지 익명-only 정책을 유지할지 제품 결정을 내린다.
6. Starlette TestClient 사용 중단 예정 경고를 제거한다.

위 항목이 남아 있으므로 “프로토타입·공모전 검증 수준”은 높아졌지만
“공개 프로덕션 운영 완료”로 표시하지 않는다.
