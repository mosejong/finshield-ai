# 23. 브라우저 세션 인증과 FinancialProfile 소유권

## 목적과 범위

로그인 화면 없이 프로토타입을 사용할 수 있도록 익명 사용자 세션을 발급하고, 저장된
FinancialProfile을 생성한 브라우저 세션의 사용자에게만 공개한다. 이름·이메일·전화번호·주민등록번호는
인증을 위해 수집하지 않는다.

이 단계는 정식 계정·복구 기능이 아니다. 쿠키가 삭제되거나 다른 브라우저를 사용하면 기존 익명
프로필에 다시 접근할 수 없다.

## 요청 흐름

```text
브라우저
  └─ GET /api/proxy/auth/session
       ├─ 200: 기존 세션 사용
       └─ 401: POST /api/proxy/auth/session
                    └─ FastAPI가 32-byte 난수 토큰 발급
                         ├─ 브라우저: HttpOnly 쿠키
                         └─ DB: SHA-256 토큰 해시만 저장

브라우저의 profile 요청
  └─ Next Route Handler
       └─ finshield_session 쿠키 하나만 FastAPI에 전달
            └─ 세션 사용자 ID + profile owner_user_id 일치 조건으로 CRUD/metrics 수행
```

브라우저 JavaScript에는 세션 원문 토큰을 반환하지 않는다. Next 프록시는 테마·분석 등 다른 쿠키를
백엔드에 전달하지 않는다.

## API 계약

- `POST /api/v1/auth/session`: 유효한 쿠키가 있으면 같은 세션을 사용하고, 없거나 만료되었으면 익명
  사용자와 세션을 생성한다.
- `GET /api/v1/auth/session`: 현재 세션의 공개 메타데이터를 반환한다.
- `DELETE /api/v1/auth/session`: 세션을 폐기하고 쿠키를 만료시킨다.
- `DELETE /api/v1/auth/account`: 현재 익명 사용자, 모든 세션과 소유 FinancialProfile을 삭제하고 쿠키를
  만료시킨다. 세션 폐기와 개인정보 삭제는 서로 다른 계약이다.
- `POST/GET/PUT/DELETE /api/v1/profiles`, `GET /api/v1/profiles/{id}/metrics`: 유효한 세션 필수.
- 인증 실패는 `401`, 저장소 장애는 내부 정보를 숨긴 `503`을 반환한다.
- 존재하지 않는 프로필과 다른 사용자의 프로필은 모두 같은 `404`를 반환한다. 소유 여부를 추측할 수
  있는 별도 오류는 제공하지 않는다.

인증 응답에는 익명 사용자 UUID, 세션 만료 시각과 익명 사용자 종류만 포함한다. 쿠키 토큰은 응답
본문에 포함하지 않는다.

## 저장 구조와 migration

Alembic revision `20260813_02`가 다음 구조를 추가한다.

- `users`: 무작위 UUID, `anonymous` 종류, 활성 상태, 생성 시각
- `auth_sessions`: SHA-256 토큰 해시, 사용자 FK, 생성·만료 시각
- `financial_profiles.owner_user_id`: 사용자 FK와 조회 index

기존 profile row는 안전한 자동 소유권 추론이 불가능하므로 `owner_user_id = NULL`로 남는다. 이 row는
새 인증 API에서 조회되지 않는다. 새 profile은 항상 현재 세션 사용자 ID를 기록한다.

## 쿠키 정책

- 이름: `finshield_session`
- `HttpOnly`: JavaScript 원문 접근 차단
- `SameSite=Strict`: 교차 사이트 요청의 자동 쿠키 전송 차단
- `Path=/`
- development/test: 로컬 HTTP 확인을 위해 `Secure` 미설정
- staging/production: `Secure` 필수, HTTPS 연결에서만 전송
- 기본 수명: 30일, `AUTH_SESSION_TTL_SECONDS`로 5분~365일 범위 설정

## 위협과 통제

| 위협 | 통제 |
| --- | --- |
| DB 유출로 세션 탈취 | 원문 대신 SHA-256 해시만 저장, 원문은 32-byte CSPRNG 토큰 |
| 다른 사용자의 UUID 추측 | 모든 profile query에 `profile_id AND owner_user_id`, 불일치는 동일한 404 |
| XSS의 쿠키 원문 탈취 | HttpOnly 쿠키 |
| CSRF | SameSite=Strict, 상태 변경은 같은 출처 Next 프록시 경유 |
| 다른 서비스 쿠키 유출 | Next 프록시가 `finshield_session` 하나만 선별 전달 |
| 만료·위조 토큰 사용 | 길이 제한, 해시 일치와 만료 시각, 활성 사용자 상태 검증 |
| 장애 정보 노출 | 공개 응답은 일반화된 401/503, DB 주소·암호문·키 정보 미포함 |

HttpOnly는 XSS가 사용자의 브라우저에서 같은 출처 요청을 실행하는 것까지 막지는 못한다. 배포 전 CSP,
의존성 점검, 출력 인코딩과 보안 헤더 검증이 별도로 필요하다.

## 로컬 실행

기존 `.env`의 암호화 DB 설정을 유지하고 migration을 적용한다.

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload --env-file .env
```

프론트는 별도 설정 없이 `/api/proxy/auth/session`으로 세션을 준비한다. 브라우저 개발자 도구에서 쿠키가
HttpOnly·SameSite Strict인지 확인할 수 있지만 원문 토큰을 로그나 문서에 복사하지 않는다.

## 데이터 생명주기

profile 화면은 단일 profile 삭제와 익명 계정 전체 삭제를 분리한다. 활성 세션이 하나도 없는 익명 사용자와
소유 profile은 dry-run 기본 운영 명령으로 집계한 뒤 명시적으로 정리한다. 상세 보존·삭제·백업 경계는
`docs/24-anonymous-data-lifecycle.md`를 따른다.

## 남은 운영 과제

- 익명 사용자의 계정 전환·복구 정책
- 운영 스케줄러와 정리 실패 알림
- PostgreSQL 동시성·복구·부하 통합 테스트
- CSP, HSTS, reverse proxy TLS, secret manager, 접근 감사 로그
- 세션 교체·다중 기기·강제 폐기 운영 도구

상세 결정은 `docs/adr/0003-anonymous-session-profile-ownership.md`를 따른다.
