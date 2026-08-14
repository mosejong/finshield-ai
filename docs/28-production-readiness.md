# 28. 프로덕션 준비 상태와 남은 작업

목적: FinShield AI를 실제 도메인에 공개 배포할 수 있는 상태로 만든다. 이 문서는 "무엇이 이미 되어 있는가"와 "공개 전에 반드시 끝내야 하는가"를 코드 기준으로 구분한다. 작성 기준일 2026-08-14, 기준 커밋 `c4a98a0`.

판단 기준은 하나다. **공개 URL이 붙는 순간 인증 없는 트래픽이 들어온다.** 그 트래픽이 비용·데이터·개인정보에 남기는 흔적을 통제할 수 있으면 배포 가능, 아니면 불가다.

## 1. 이미 갖춰진 것

이 항목들은 다시 만들 필요가 없다.

| 영역 | 상태 | 근거 |
|---|---|---|
| 컨테이너 이미지 | base 이미지 digest 고정, non-root uid 10001, `read_only`, `cap_drop: ALL`, `no-new-privileges` | `Dockerfile`, `web/Dockerfile`, `compose.yaml` |
| 프로세스 경계 | db / migration / backend / web 분리, 내부 포트 loopback 전용, healthcheck 기반 기동 순서 | `compose.yaml` |
| HTTPS 진입점 | Caddy 자동 인증서, HTTP→HTTPS, HSTS, `FINSHIELD_DOMAIN` 필수 | `compose.https.yaml`, `deploy/Caddyfile`, `docs/26` |
| 비밀값 관리 | `*_FILE` 우선 조회 + Docker file secrets. 이미지·환경변수·저장소에 값이 남지 않음 | `app/core/runtime_secrets.py` |
| 저장 데이터 보호 | FinancialProfile 애플리케이션 레벨 암호화, 키 로테이션 경로 | `app/security/profile_encryption.py`, `adr/0002` |
| 로그 개인정보 | 로그 필드 allowlist 고정. 쿼리·본문·경로 파라미터가 구조적으로 로그에 없음 | `app/core/observability.py`, `tests/test_observability.py` |
| HTTP 보안 경계 | 보안 헤더, same-origin 상태 변경 보호, trusted host | `app/core/http_security.py`, `docs/26` |
| CI | pytest / 프론트 build·tsc·lint·test / compose 실기동 + backup·restore 검증 | `.github/workflows/ci.yml`, `scripts/verify_compose_runtime.py` |

정리하면 **배포 스택 자체는 이미 프로덕션 형태다.** 남은 것은 스택이 아니라 운영이다.

## 1-1. 코드 검증 결과 (2026-08-14)

"테스트 199개 통과"는 정확성의 근거가 아니다. 세 가지 독립적인 방법으로 다시 확인했다.

| 방법 | 대상 | 결과 |
|---|---|---|
| 독립 재계산 | `loan_calculator` | 표준 annuity 공식으로 따로 계산해 무작위 800케이스 대조. 참조값 `100000/6%/360 → 599.55` 일치, 원금 합계·잔액 단조감소·최종 잔액 0·회차 분해 전부 통과 |
| 적대적 E2E 탐침 | 세션 소유권 | 실제 쿠키 세션 2개로 프로필 전 엔드포인트 침투. 12/12 차단. 타인 자원은 403이 아니라 **404**로 존재 여부를 감춤 |
| Mutation 감사 | 테스트 자체 | 핵심 로직에 고의로 버그를 심고 스위트가 잡는지 확인 |

Mutation 감사에서 **위험 등급 임계값만 통과했다.** `score >= 70`을 `>= 90`으로 바꿔도 전 테스트가 통과했고, 그 분기는 죽은 코드가 아니라 실제로 등급을 바꾸는 살아있는 로직이었다. 나머지(상태 최소위험, 점수 상한, 반올림 방식, 로그 PII 유출, SQL·메모리 소유자 필터)는 모두 잡혔다.

같은 검증에서 드러나 **함께 수정한 것**:

| 문제 | 수정 |
|---|---|
| 위험 등급 임계값에 테스트 없음 | `HIGH_RISK_SCORE_THRESHOLD` / `MEDIUM_RISK_SCORE_THRESHOLD` 로 명명하고 `tests/test_fraud_risk_level.py` 가 경계 34/35/69/70 + 신호 최소등급 + 조합 규칙 + 상태 최소등급을 각각 고정 |
| 스킴 없는 URL이 링크 검사 통과 (`1.2.3.4/login`) | 스킴 유무와 무관하게 호스트를 뽑아 같은 검사 적용. 본문에서도 스킴 없는 링크를 후보로 추출. `javascript:` / `data:` 같은 비-HTTP 스킴 차단. `tests/test_fraud_urls.py` |
| `retrieved_at` 하드코딩으로 링크 재확인 시 분석 500 | 형식·미래 날짜만 데이터 오류로 막고, 오래된 출처는 `stale_official_sources()` 로 경고. 기동 시 `verify_official_sources()` 호출을 추가해 잘못된 데이터가 health check를 통과하지 못하게 함. `tests/test_official_sources.py` |
| zod ↔ pydantic 계약 드리프트 | `marital_status`·`region` 왕복 보존(수정 시 서버 값이 null로 덮이던 경로 제거), `marital_status`·`annual_business_revenue_band`·`loan_items` 를 느슨한 `string`/`unknown` 에서 실제 enum·객체 스키마로 고정, 금리 소수 자릿수를 백엔드 `decimal_places=4` 에 맞춤 |

**남은 미측정 항목**: `authority_impersonation` 오탐(`"어제 경찰서 다녀왔어요"` → medium)은 규칙 기반 bootstrap의 한계이며 FPR이 측정된 적이 없다. P2-1 평가 하네스 없이는 정량 판단이 불가능하다.

## 2. P0 — 공개 배포 차단 항목

이 다섯 개를 끝내기 전에는 공개 도메인을 붙이지 않는다.

### P0-1. Rate limiting과 요청 본문 크기 제한

`POST /api/v1/analyze`에는 인증 의존성이 없다 (`app/api/routes/analysis.py:9`). `POST /api/v1/auth/session`도 익명 세션을 무제한으로 만들 수 있다. 공개 즉시 두 가지가 동시에 터진다. 분석 엔드포인트는 CPU를 소모하고, 세션 엔드포인트는 DB에 행을 쌓는다. 스키마 상한(`text` 10000자)은 요청 **한 건**의 크기만 막을 뿐 **빈도**를 막지 못한다.

- 대상: `/api/v1/analyze`, `/api/v1/auth/session`, 그 외 쓰기 엔드포인트
- 식별자는 IP 단독이 아니라 익명 세션 + IP 조합으로 두되, 세션 발급 자체가 제한 대상이라는 순환을 고려한다
- 초과 응답은 `429` + `Retry-After`. 위험 분석이 막혔다는 사실이 "안전하다"로 읽히지 않게 프론트 문구를 함께 정한다
- HTTP 경계에서 본문 전체 크기 제한을 추가한다 (스키마 검증 이전에 잘라야 의미가 있다)
- 완료 기준: 제한 초과 시 429 반환, 정상 사용자 흐름 무영향, 카운터가 worker 재시작을 지나 유지되는지 확인, 회귀 테스트

`docs/26`에서 관측성 단계로 미뤄둔 항목이다. 관측성은 끝났으므로 이제 차례다.

### P0-2. 만료 데이터 정리 자동 실행

`scripts/cleanup_expired_anonymous_data.py`는 있지만 아무도 부르지 않는다. `docs/24`가 스케줄을 "권장"으로만 적어둔 상태다. 보존기간 정책이 문서에만 있고 실행되지 않으면 두 가지가 발생한다. 개인정보 보존 약속 위반, 그리고 DB 무한 증가.

- compose에 스케줄 실행 경로를 넣는다 (전용 서비스 또는 호스트 스케줄러)
- 실행 결과를 관측 가능하게 남긴다 — 삭제 건수, 실패 여부. 개인 식별 값은 남기지 않는다
- 실패가 조용히 넘어가지 않도록 한다
- 완료 기준: 만료 데이터를 넣고 스케줄 주기를 지난 뒤 자동으로 사라지는 것을 실환경에서 확인

`adr/0004-anonymous-data-lifecycle.md`의 이행 부분이다.

### P0-3. 백업 자동화와 복원 리허설

`pg_dump`/restore 로직은 현재 `scripts/verify_compose_runtime.py` 안, 즉 CI 검증 경로에만 있다. 운영 백업 스케줄은 없다. 저장 데이터가 암호화된 프로필이라 **DB만 복원하고 키를 잃으면 백업은 쓸모가 없다.**

- 주기적 dump + 보존 세대 관리 + 저장 위치(볼륨 밖)
- 암호화 키와 DB 백업의 복구 절차를 한 문서에 함께 적는다. 둘 중 하나만 있으면 복구 불가라는 점을 명시
- 정기 복원 리허설. "백업이 생성된다"가 아니라 "복원이 성공한다"가 완료 기준
- 완료 기준: 빈 환경에서 백업만으로 서비스를 기동해 프로필 복호화까지 성공

### P0-4. 실도메인·DNS·TLS 실환경 검증

`docs/devlog/2026-08-13/`가 명시한 미완료 항목이다. Caddy 설정과 compose는 검증됐지만 실제 도메인·DNS·인증서 발급은 한 번도 돌지 않았다. 자동 인증서는 DNS가 실제로 가리키기 전에는 검증할 수 없다.

- 도메인 확정 → DNS A/AAAA → `FINSHIELD_DOMAIN` 주입 → 인증서 자동 발급 확인
- 외부에서 HTTP→HTTPS 리다이렉트, HSTS, TLS 등급 측정
- 인증서 갱신 실패 시 알림 경로 (갱신은 60일 뒤에 조용히 실패한다)
- 완료 기준: 외부 네트워크에서 실제 도메인으로 전 주요 화면 동작

### P0-5. 파이썬 의존성 잠금

컨테이너 base 이미지는 digest로 고정했는데 `requirements.txt`는 `fastapi>=0.116,<1.0` 같은 범위 지정이다. 같은 커밋을 다시 빌드해도 다른 버전이 설치된다. 이미지 재현성을 절반만 확보한 상태이고, 장애 시 "어제와 무엇이 달라졌는가"에 답할 수 없다.

- 해시 고정 lock 파일 도입 (`requirements.lock` 등), 런타임 의존성과 개발 의존성 분리
- CI와 Dockerfile 모두 lock 기준으로 설치
- 완료 기준: 서로 다른 시점의 빌드가 동일한 패키지 버전 집합을 설치

## 3. P1 — 공개 직후 필요한 운영 역량

배포는 가능하지만 이것 없이는 오래 운영하지 못한다.

### P1-1. 장애 알림과 에러 추적

`/metrics`가 Prometheus 텍스트를 내지만 수집하는 쪽이 없다. 지금 구조에서는 장애를 사용자가 먼저 안다. 최소한 헬스체크 실패, 5xx 급증, 외부 공식 API 실패율 상승에 대한 알림이 필요하다. 에러 추적을 붙일 때 **로그 allowlist 원칙을 깨지 않는지** 반드시 확인한다 — 대부분의 에러 추적 SDK는 기본값으로 요청 본문을 보낸다.

### P1-2. Audit log

계정 삭제, 프로필 변경처럼 되돌릴 수 없는 동작의 기록이 없다. `docs/10`에서 "identity와 보존 정책 필요"로 미뤄둔 항목이다. 익명 세션 모델 위에서 무엇을 남길 수 있는지부터 정해야 한다. 감사 로그가 개인정보 보존기간 정책과 충돌하지 않게 설계한다.

### P1-3. 배포·롤백 절차

현재 CI는 검증까지만 하고 배포하지 않는다. 수동 배포는 롤백이 안 된다. migration 컨테이너가 앞서 도는 구조이므로 **마이그레이션 되돌리기 전략**을 배포 절차와 함께 정한다. 스키마 변경과 코드 배포를 같은 순간에 되돌릴 수 없다는 점이 핵심 제약이다.

### P1-4. nonce 기반 strict CSP

`docs/26`의 남은 항목. Next.js standalone과 함께 쓸 때 nonce 전달 경로를 확인해야 한다.

## 4. P2 — 제품·대회 완성도

배포와 무관하지만 이 프로젝트의 주장을 증명하는 부분이다.

### P2-1. 평가 하네스

**현재 저장소에 평가 코드가 전혀 없다.** `eval/`도 `benchmarks/`도 없고 precision/recall/F1을 계산하는 코드도 없다. `CLAUDE.md`의 Evaluation 조항과 `docs/05`가 요구하는 Rule-only / LLM-only / Hybrid 비교가 문서로만 존재한다.

이건 단순 누락이 아니다. 이 프로젝트의 논지는 "hybrid가 더 안전하고 정확하다"인데, 그걸 뒷받침하는 숫자가 하나도 없다. 지금 상태로는 아키텍처 주장이 근거 없는 선언이다.

- golden set 먼저 (`docs/05`의 scenario engine 항목 형식: 입력 상황, 이미 한 행동, 예상 scenario, 허용/금지 행동)
- 재현 가능한 실행 진입점, 결과 산출물 포맷 고정
- 지표: fraud 분류 precision/recall/F1과 class별 recall, 신호 추출 precision/recall, scenario 일치율, FPR
- **먼저 Rule-only 베이스라인을 측정한다.** LLM 없이도 지금 당장 낼 수 있는 숫자이고, 이후 모든 비교의 기준선이 된다

### P2-2. LLM 설명 계층

`app/` 전체에 LLM 클라이언트가 없다. 아키텍처 다이어그램의 "LLM explanation" 단계가 코드에 존재하지 않고, 현재 시스템은 순수 규칙 기반이다. 프론트의 설명 텍스트는 mock 계층에서 온다.

도입 시 함께 필요한 것: 출력 스키마 검증(`docs/04`의 model output schema validation), prompt injection golden set, 근거 이탈 검출. 규칙 판정을 LLM이 덮어쓰지 못하게 하는 경계가 코드로 강제되어야 한다 — `CLAUDE.md`의 첫 번째 non-negotiable이다.

**P2-1을 먼저 한다.** 베이스라인 없이 LLM을 넣으면 개선됐는지 나빠졌는지 알 수 없다.

### P2-3. 접근성 실기기 검수

구조적 자동 회귀는 `web/components/a11y.test.tsx`가 상시 실행 중이다. 남은 것은 스크린리더 낭독, 명도대비 AA 실측, 실기기 iOS Safari 확인이다. 상세는 `docs/13` 9절.

## 5. 모바일 전략 — PWA 우선, 네이티브는 나중

사용자 대부분이 폰으로 쓸 것이라는 전제는 타당하다. 의심 문자를 받은 순간 쓰는 서비스이므로 폰이 기본 환경이다. 다만 **지금 필요한 것은 안드로이드 앱이 아니라 PWA다.**

이유는 UI가 아니라 인증 모델이다. 현재 세션은 `SameSite=Strict` + HttpOnly 쿠키에 trusted-host 허용목록이고 CORS 미들웨어가 없다 (`app/core/http_security.py`, `app/api/routes/auth.py`). **네이티브 앱이나 WebView 클라이언트는 이 인증을 그대로 쓸 수 없다.** 네이티브로 가려면 토큰 기반 인증, CORS 정책, 그리고 그에 딸린 위협 모델을 새로 만들어야 한다. 화면을 옮기는 작업이 아니라 보안 경계를 다시 세우는 작업이다.

PWA는 같은 오리진에서 돌기 때문에 지금 인증 모델을 그대로 쓴다. 얻는 것:

- 홈 화면 설치, 전체화면 실행 — 체감상 앱과 같다
- **Android 공유 시트 연동 (`share_target`)** — 문자 앱에서 의심 메시지를 바로 넘길 수 있다. 이 제품의 핵심 진입 경로다
- 배포 심사 없음, 스토어 계정 없음, 단일 코드베이스

포기하는 것: iOS의 공유 시트·푸시 제약, `READ_SMS` 자동 수집. 후자는 Play Store 제한 권한이라 어차피 심사를 통과하기 어렵고, `CLAUDE.md`의 PII 최소화 원칙과도 정면으로 충돌한다. 자동 수집은 하지 않는다.

작업 범위: manifest, 아이콘, `share_target` 라우트, 오프라인 셸(분석 결과는 캐시하지 않는다 — 민감 데이터다), 설치 유도 UI. **실도메인(P0-4) 앞에 넣는다.** HTTPS가 PWA 설치 요건이고, 공개 직후 바로 폰에 설치되는 편이 낫기 때문이다.

Capacitor로 감싸는 선택지는 스토어 등록이 실제로 필요해질 때 다시 판단한다. 그 시점의 선결 조건은 위에 적은 토큰 기반 인증이다.

## 6. 권장 순서

```
0. 접근성 브랜치 병합 (작업 중 브랜치 정리)
1. P0-5 의존성 잠금        ← 이후 모든 검증의 기준을 고정
2. P0-1 rate limit + 본문 크기 제한
3. P0-2 만료 데이터 정리 자동화
4. P0-3 백업 자동화 + 복원 리허설
5. PWA (manifest + share_target)  ← 실도메인 직전
6. P0-4 실도메인·DNS·TLS   ← 공개 배포
7. P1-1 알림 → P1-3 배포·롤백 → P1-2 audit log → P1-4 CSP
8. P2-1 평가 하네스 → P2-2 LLM 계층
```

P0-5를 맨 앞에 두는 이유는 의존성이 고정돼야 이후 rate limit·백업 검증 결과가 재현되기 때문이다. P0-4를 마지막에 두는 이유는 공개 노출이 되돌리기 가장 어려운 단계라서다.

대회 일정이 공개 URL보다 우선한다면 P2-1(평가 하네스)을 P0-1 다음으로 올린다. Rule-only 베이스라인 측정은 배포 상태와 무관하게 지금 바로 가능하다.
