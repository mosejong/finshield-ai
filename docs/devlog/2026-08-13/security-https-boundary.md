# 보안 헤더·CSRF·HTTPS 경계 개발일지

- 날짜: 2026-08-13 (Asia/Seoul)
- 역할: PM 통합 작업
- 브랜치: `feature/security-https-boundary`
- 기준 main: `5f2fd321551a9c76f558c434732b607a728f2456`
- 시작: 16:27
- 상태: 진행 중

## 목표

브라우저·API 응답 보안 헤더, cookie 기반 변경 요청의 same-origin 검증, production trusted host와 TLS reverse
proxy 경계를 추가한다. localhost HTTP 개발과 공개 HTTPS 정책을 분리하고 기존 금융 계산·분석 결과는
변경하지 않는다.

## 시간순 기록

- 16:27: `feature/security-https-boundary` 생성, Next proxy와 FastAPI middleware·Compose 경계 점검.
- 16:29: CSRF 보호 대상을 세션 생성·폐기, 익명 계정 삭제, profile 생성·교체·삭제로 확정. 읽기와 stateless
  계산 proxy는 cookie 기반 상태 변경이 아니므로 비범위로 둠.
- 16:30: CSP는 Next inline bootstrap 제약상 `unsafe-inline`을 허용하되 `unsafe-eval`, 외부 script, object,
  frame을 차단하는 기준으로 결정. nonce 기반 strict CSP는 후속 강화 항목으로 기록.

## 예정 검증

- backend/frontend 전체 회귀와 production build
- security header exact contract
- same-origin 허용, missing/cross-site Origin 403
- production trusted host fail-closed
- TLS proxy Compose config와 내부 port loopback 제한
- live HTTP Compose E2E Origin header

## 보안 영향

- 금융·사기 원문을 새로 로그에 남기지 않는다.
- TLS는 reverse proxy에서 종료하고 backend DB port는 public network에 노출하지 않는다.
- HSTS는 실제 HTTPS proxy에서만 설정하며 localhost HTTP에는 적용하지 않는다.

## 완료 기록

- 16:33: FastAPI 공통 보안 헤더와 production trusted-host fail-closed 구현.
- 16:34: Next 전 경로 CSP·frame 차단·권한 제한 헤더와 상태 변경 proxy Origin 검사 구현.
- 16:35: backend/web host port를 loopback으로 제한하고 Caddy HTTPS override를 추가. Caddy 2.10.2 이미지를 digest로 고정.
- 16:36: 단위 검증 통과 — Python 보안 3개, 프론트 출처 보호 2개, Next production build 성공.
- 16:37: 전체 회귀 통과 — Python 195 passed/1 skipped, frontend 34 passed, TypeScript·lint·build 성공.
- 16:38: HTTPS Compose config와 Caddyfile validate 성공. live header에서 CSP·COOP·CORP·DENY·nosniff 확인, Origin 없는 세션 생성은 403 확인.
- 16:38: Docker/PostgreSQL 전체 E2E 성공 — backend 재시작 보존, backup/restore, 암호화 평문 비노출, 최종 사용자·세션·프로필 `0|0|0`.

## 판단과 남은 한계

- 실제 도메인과 DNS가 없으므로 자동 인증서와 외부 HTTP→HTTPS 전환은 아직 실환경 검증하지 않았다. public deployment 완료가 아니라 deployment configuration 완료다.
- Next runtime 호환을 위해 CSP에 `unsafe-inline`이 남아 있다. 외부 script와 `unsafe-eval`은 금지하며 nonce 기반 강화는 후속 작업이다.
- 상태 변경 보호는 cookie 기반 세션·프로필 lifecycle에만 적용했다. stateless 분석·계산 API에 임의로 적용하지 않았다.

## Git/PR

- 검증 후 기록
