# 22. FinancialProfile DB 영속화·암호화

## 목적

FinancialProfile의 재시작·다중 worker 영속성을 확보하고 DB dump에서 소득·자산·
부채·지역·대출 상세가 평문으로 노출되는 위험을 줄인다. 공개 API와 파생지표 계산
계약은 유지한다.

## 저장 구조

`financial_profiles` table은 다음 값만 저장한다.

- `profile_id`: 불투명 UUID
- `owner_user_id`: 인증 사용자 UUID FK. 신규 row는 필수이며 기존 owner 미확정 row는 `NULL`
- `encrypted_profile`: version, profile UUID, 검증된 profile JSON을 포함한 Fernet 암호문
- `encryption_key_id`: 비밀이 아닌 키 식별자
- `created_at`, `updated_at`: UTC 시각

금융 금액이나 지역을 별도 평문 column으로 저장하지 않는다. 암호문 내부 UUID와 row
UUID를 비교하므로 유효한 암호문을 다른 row로 바꾸는 공격도 복호화 실패로 처리한다.

## 환경별 정책

- `development`, `test`: DB URL과 키가 모두 없을 때만 기존 메모리 저장 허용
- `development`, `test`: 두 값을 모두 지정하면 SQLite 또는 PostgreSQL 저장 허용
- 그 외 배포 환경: `postgresql+psycopg://` URL과 키를 모두 필수로 요구
- DB 접속 실패 또는 migration 누락: 앱 시작 실패
- 키 누락·잘못된 키·변조된 암호문: 원문 없이 일반화된 저장 오류

## 로컬 암호화 DB 실행

1. Fernet 키를 한 번 생성한다. 출력값은 secret manager 또는 로컬 `.env`에만 둔다.

   ```powershell
   .\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. `.env`에 아래 값을 설정한다. 실제 키를 문서나 Git에 넣지 않는다.

   ```dotenv
   APP_ENV=development
   DATABASE_URL=sqlite+pysqlite:///./finshield.sqlite3
   PROFILE_ENCRYPTION_KEYS=<생성한 키>
   ```

3. migration 후 서버를 실행한다.

   ```powershell
   .\.venv\Scripts\alembic.exe upgrade head
   .\.venv\Scripts\uvicorn.exe app.main:app --reload --env-file .env
   ```

SQLite는 단일 PC 프로토타입 확인용이다. staging·production에서는 사용할 수 없다.

## PostgreSQL 전환

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<database>
PROFILE_ENCRYPTION_KEYS=<secret-manager가 주입한 키>
```

배포 순서는 DB 백업 → `alembic upgrade head` → 애플리케이션 시작이다. 암호화 키와
DB 자격증명은 서로 다른 secret으로 관리하고 application log에 출력하지 않는다.
TLS, 최소권한 DB 계정, 디스크·backup 암호화, 접근 감사는 별도 인프라 통제다.

## 키 순환

`PROFILE_ENCRYPTION_KEYS=new_key,old_key`처럼 신규 키를 첫 번째에 둔다. 신규 생성과
교체 profile은 첫 키로 암호화되고 기존 row는 key ID를 통해 이전 키로 읽는다. 기존
row 재암호화 작업과 backup 보존기간이 끝나기 전에는 이전 키를 제거하지 않는다.
키 분실 시 암호문을 복구할 수 없으므로 배포 전 복구 절차를 검증해야 한다.

## 삭제·보존 경계

DELETE는 활성 table row를 제거하지만 PostgreSQL WAL, snapshot, backup의 즉시 물리
삭제를 보장하지 않는다. 공개 서비스 전에 보존기간, backup 만료, 사용자 삭제 요청,
법적 보존 예외를 포함한 정책을 확정해야 한다.

## 아직 남은 공개 배포 차단 조건

- 익명 계정 전환·복구와 session/profile 보존기간·정리 정책
- secret manager·KMS와 자동 키 순환 작업
- PostgreSQL 기반 통합·복구·부하 테스트
- 개인정보 처리방침, 동의, 보존·삭제 정책
- 접근 감사로그와 이상 접근 탐지

상세 결정과 위협 경계는 `docs/adr/0002-encrypted-profile-persistence.md`를 따른다.
