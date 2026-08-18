# 26. HTTP 보안 경계와 HTTPS 공개 구성

## 목적

FinShield는 금융 프로필과 익명 세션 쿠키를 다룬다. 브라우저와 API 사이의 경계는 단순한 화면 설정이 아니라 데이터 보호 기능이다. 이 문서는 로컬 HTTP 개발과 외부 HTTPS 공개 환경을 분리하고 현재 구현과 제한을 기록한다.

## 구현된 통제

### 브라우저 응답

- 모든 Next.js 경로에 CSP, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, 제한된 `Permissions-Policy`를 적용한다.
- `X-Powered-By` 헤더를 제거한다.
- 현재 Next.js 인라인 부트스트랩 호환을 위해 CSP의 script/style에 `unsafe-inline`이 남아 있다. 외부 script, `unsafe-eval`, object, 다른 사이트의 frame 삽입은 허용하지 않는다.
- nonce 기반 strict CSP는 배포 전 추가 강화 항목이다.

### 쿠키 기반 상태 변경 요청

다음 Next same-origin proxy 요청은 유효한 `Origin`이 없거나 허용 목록과 다르거나 브라우저가 `Sec-Fetch-Site: cross-site`로 표시하면 403을 반환한다.

- 익명 세션 생성·종료
- 익명 계정과 전체 금융 프로필 삭제
- 금융 프로필 생성·수정·삭제

읽기 요청과 쿠키에 의존하지 않는 분석·계산 요청은 이 검사 대상이 아니다. 세션 쿠키의 `HttpOnly`, `SameSite=Strict`, 공개 환경 `Secure` 속성은 기존 정책을 유지한다.

### FastAPI 응답과 Host 검증

- API 응답에는 `Cache-Control: no-store`, API 전용 CSP, `DENY`, `nosniff`, `no-referrer`, 제한된 `Permissions-Policy`를 적용한다.
- staging/production은 `FINSHIELD_TRUSTED_HOSTS`가 없거나 wildcard이면 시작을 거부한다.
- 배포 환경 요청의 Host가 허용 목록에 없으면 400으로 거부한다.
- HSTS는 배포 환경에서만 활성화하며 localhost HTTP에는 적용하지 않는다.

## 네트워크 경계

기본 Compose의 backend와 web 포트는 `127.0.0.1`에만 bind된다. PostgreSQL은 host 포트를 공개하지 않는다. 외부 공개 시 `compose.https.yaml`을 함께 사용하고 Caddy만 80/443을 공개한다.

```powershell
$env:FINSHIELD_DOMAIN = "finshield.example.com"
$env:FINSHIELD_ACME_EMAIL = "ops@finshield.example.com"
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml up --detach --build
```

Caddy는 실제 도메인의 인증서를 자동 관리하고 HTTP를 HTTPS로 전환하며 HSTS를 추가한다. 실제 배포 전 DNS가 서버를 가리키고 80/443이 열려 있어야 한다. 도메인이 정해지지 않은 현재 단계에서는 구성 유효성과 `localhost` 예행연습까지 검증하며, 공개 배포 완료로는 표시하지 않는다. 절차와 완료 기준은 `31-public-deployment.md`에 있다.

## 환경변수

- `FINSHIELD_DOMAIN`: 외부 공개 도메인. HTTPS override 사용 시 필수.
- `FINSHIELD_ACME_EMAIL`: ACME 계정 연락처. HTTPS override 사용 시 필수. 인증서 갱신은 조용히 실패하고, 발급기관이 그 사실을 알릴 수 있는 유일한 통로가 이 주소다. 값이 비면 Caddy가 기동을 거부한다.
- `FINSHIELD_ALLOWED_ORIGINS`: Next 상태 변경 요청에 허용할 origin의 쉼표 구분 목록.
- `FINSHIELD_TRUSTED_HOSTS`: FastAPI가 허용할 Host 이름의 쉼표 구분 목록. wildcard 금지.
- `APP_ENV`: `production` 또는 `staging`에서 배포용 fail-closed 정책 활성화.

기본 로컬 포트를 바꾸면 `FINSHIELD_ALLOWED_ORIGINS`도 실제 브라우저 origin에 맞게 바꿔야 한다.

## 검증 계약

- Python 보안 테스트: 로컬 HSTS 비활성, 배포 HSTS 활성, Host 거부, 설정 누락/wildcard fail-closed.
- 프론트 테스트: same-origin 허용, missing/cross-site Origin 403.
- production build에서 모든 경로의 보안 헤더 생성.
- Caddyfile validate와 HTTPS Compose config를 CI에서 검증. ACME staging override를 얹은 조합도 함께 검증.
- 공개 배포 판정 기준(`app/core/public_deployment.py`)은 네트워크 없이 단위 테스트로 고정. 실측은 `scripts/verify_public_deployment.py`.
- 실제 HTTP Compose E2E는 Origin을 포함해 세션·프로필·삭제 생명주기를 확인.

## 남은 운영 작업

순서와 완료 기준은 `28-production-readiness.md`를 따른다.

- 실제 배포 도메인·서버를 정한 뒤 DNS, 자동 인증서, 외부 HTTP→HTTPS, TLS 등급을 실환경에서 재검증한다. (28 의 P0-4) 도메인이 필요 없는 부분(ACME 연락처, staging 예행연습 경로, proxy healthcheck, 외부 검증기)은 2026-08-17 에 끝났고 절차는 `31-public-deployment.md` 에 있다. 남은 것은 도메인·서버 확보와 실제 발급이다.
- rate limit 과 요청 본문 크기 제한. 관측성 단계가 끝났으므로 이제 착수 대상이다. (28 의 P0-1)
- 장애 알림. `/metrics` 는 노출되지만 수집·알림 경로가 없다. (28 의 P1-1)
- nonce 기반 strict CSP 를 검토한다. (28 의 P1-4)
- WAF 는 도메인 확정과 트래픽 관찰 이후에 판단한다.
