# HTTP 보안·HTTPS 경계 main 통합

- 날짜: 2026-08-13 (Asia/Seoul)
- 역할: PM main 관리
- 코드 PR: #50
- feature commit: `cf48007d074238247f2fa9d990b2d8ba8e47fab4`
- main merge commit: `2a6d58f`
- 상태: 통합 완료

## 통합 범위

- FastAPI 공통 보안 헤더와 배포 환경 trusted-host fail-closed
- Next CSP·frame 차단·권한 제한 헤더와 기술 노출 헤더 제거
- 익명 세션·계정·프로필 상태 변경 요청의 same-origin 검사
- 내부 port loopback 제한과 Caddy HTTPS 공개 구성
- HTTPS Compose/Caddy CI 검증, 운영 문서와 ADR

## PM 검수 결과

- 로컬: Python 195 passed, 1 skipped; frontend 35 passed; build·TypeScript·lint 통과.
- 실제 Docker/PostgreSQL: 재시작 보존, backup/restore, 암호화 평문 비노출, 계정 삭제 후 `0|0|0`.
- GitHub Linux CI: test, web, container-runtime 두 실행 모두 통과.
- live response: CSP·COOP·CORP·DENY·nosniff 확인, `X-Powered-By` 미노출, Origin 없는 세션 생성 403.

## 범위 판단

실제 도메인·DNS·인증서가 없으므로 public MVP deployment 자체는 미완료다. 현재 완료 범위는 재현 가능한 HTTPS 배포 구성과 검증 자동화다. nonce 기반 strict CSP, rate limit, 운영 알림은 후속 단계로 넘긴다.

## 다음 단계

1차 4번으로 관측성, PII 마스킹, 성능 지표, 배포 준비 증적을 구현한다.
