# ADR 0005: Same-origin 상태 변경 보호와 HTTPS 진입점

- 상태: 승인
- 날짜: 2026-08-13

## 결정

브라우저 상태 변경은 Next same-origin proxy에서 `Origin`과 `Sec-Fetch-Site`를 검증한다. FastAPI는 배포 환경에서 명시적인 trusted host 없이는 시작하지 않는다. 기본 Compose 포트는 loopback에만 열고 외부 공개는 Caddy HTTPS reverse proxy를 유일한 진입점으로 사용한다.

## 이유

세션 쿠키가 `SameSite=Strict`이어도 서버의 의도를 코드와 테스트로 명시하는 편이 안전하다. backend·web 개발 포트를 그대로 외부에 노출하면 HTTPS와 HSTS를 우회할 수 있으므로 공개 진입점을 하나로 제한해야 한다.

## 결과

- 로컬 개발은 기존 HTTP 주소를 사용할 수 있다.
- 공개 배포에는 도메인과 DNS가 필요하며 HTTPS override 없이는 완료로 간주하지 않는다.
- Next 인라인 부트스트랩 때문에 CSP에 `unsafe-inline`이 남아 있으며 nonce 기반 강화는 후속 과제다.
