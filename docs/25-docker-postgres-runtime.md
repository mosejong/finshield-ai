# 25. Docker·PostgreSQL 실행과 복구 검증

## 목적

개발 PC와 CI에서 동일한 PostgreSQL·migration·FastAPI·Next 실행 순서를 재현하고, 암호화 profile이
다중 worker와 backend 재시작을 지나 유지되는지 확인한다. 실제 Docker secret, DB volume과 backup
artifact는 Git에 넣지 않는다.

## 구성

```text
PostgreSQL healthy
  → Alembic migration completed successfully
    → FastAPI 2 workers healthy
      → Next standalone server healthy
```

- `db`: host port를 열지 않는 PostgreSQL 16, named volume 사용
- `migration`: backend image로 `alembic upgrade head`를 한 번 실행하고 성공해야 종료
- `backend`: Python 3.12.10, non-root UID 10001, read-only filesystem, worker 2개
- `web`: Node 22, Next `output: standalone`, non-root UID 10001, read-only filesystem
- DB 비밀번호와 Fernet key: `/run/secrets/*` file secret으로만 주입

Compose는 공식 Docker 시작 순서 계약의 `service_healthy`와 `service_completed_successfully`를 사용한다.
Next는 공식 self-hosting 권장 방식인 standalone output으로 필요한 runtime file만 복사한다.

공식 설계 근거:

- Docker Compose startup order: `https://docs.docker.com/compose/how-tos/startup-order/`
- Docker Python/FastAPI guide: `https://docs.docker.com/guides/python/`
- Next.js deployment: `https://nextjs.org/docs/app/getting-started/deploying`

## 최초 로컬 실행

Docker Desktop 설치·실행 뒤 저장소 루트에서 다음을 실행한다.

```powershell
Copy-Item .env.docker.example .env.docker
.\.venv\Scripts\python.exe scripts\create_local_docker_secrets.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up --detach --build
.\.venv\Scripts\python.exe scripts\verify_compose_runtime.py
```

- 기존 개발 서버와 충돌하지 않도록 기본 host 주소는 backend `http://127.0.0.1:18000`, web
  `http://127.0.0.1:13000`이다.
- 컨테이너끼리는 host port가 아니라 `http://backend:8000`, `db:5432`로 통신한다.
- `.env.docker`와 `secrets/` 디렉터리 전체는 Git에서 제외된다. 확장자가 아니라 디렉터리로 거른다 — `secrets/*.txt`로 두면 `.txt`를 안 붙인 키 파일이 커밋 가능해진다. `tests/test_runtime_secrets.py`가 `git check-ignore`로 실제 동작을 확인한다.
- secret 생성기는 기존 파일이 하나라도 있으면 덮어쓰지 않고 중단한다.
- Linux에서는 secret 디렉터리를 owner-only `0700`, 내부 파일을 container non-root UID가 읽을 수 있는
  `0644`로 만든다. 다른 host 사용자는 상위 디렉터리를 통과할 수 없다.

공식 금융상품 live 조회까지 컨테이너에서 확인하려면 포털의 일반 인증키만 담은
`secrets/public_data_service_key.txt`를 직접 만들고 선택 override를 함께 사용한다. 이 파일도 Git에서
제외되며 인증키는 container 환경값이나 image에 포함되지 않는다.

```powershell
docker compose -f compose.yaml -f compose.public-data.yaml --env-file .env.docker up --detach --build
```

인증키 파일이 없거나 읽히지 않으면 상품 endpoint는 기존 계약대로 일반화된 503을 반환한다. 키를 가짜
기본값으로 채우거나 상품 없음으로 바꾸지 않는다.

## 운영 검증기가 확인하는 것

`scripts/verify_compose_runtime.py`는 실명·계좌번호가 없는 고정 합성 profile만 사용한다.
실행 전 원본 3개 table이 모두 0건인지 확인하며 한 건이라도 있으면 기존 데이터를 지우지 않고 중단한다.

1. backend와 web health 확인
2. 200KB 본문이 파싱 이전에 413으로 잘리는지, 한도 초과가 429 + `Retry-After`가 되는지
3. Next same-origin proxy를 통해 익명 세션과 암호화 profile 생성, metrics 조회
4. backend container 재시작 후 같은 세션으로 profile 재조회
5. `backup` service가 **제 주기에** 남긴 최신 dump를 기다린 뒤 복원 리허설로 넘겨 **복호화까지** 확인
6. backend·backup log에 profile 값과 식별자가 없는지 확인
7. 익명 계정 전체 삭제 후 기존 세션 401 확인
8. 원본 DB의 users, auth_sessions, financial_profiles 0건 확인
9. 만료 데이터가 `retention` 주기 안에 자동으로 사라지는지 확인

5번은 검증기가 직접 `pg_dump`를 부르지 않는다. 직접 부르면 백업 스케줄이 아예 없어도 통과한다.
임시 복원 DB는 `scripts/rehearse_backup_restore.py`가 자기 정리 구간에서 지운다. backup 파일은
검증기가 만든 산출물이 아니라 `backup` service의 산출물이므로 지우지 않고 세대 회전에 맡긴다.

기본 주기(정리 1시간, 백업 하루)로는 5·9번을 기다릴 수 없다. 두 검증을 돌리려면 스택과 검증기에
같은 짧은 주기를 준다 (CI는 각각 60초).

```powershell
$env:FINSHIELD_RETENTION_INTERVAL_SECONDS = "60"; $env:FINSHIELD_BACKUP_INTERVAL_SECONDS = "60"
docker compose --env-file .env.docker up --detach --build
.\.venv\Scripts\python.exe scripts\verify_compose_runtime.py
```

## 종료와 데이터 삭제

컨테이너만 종료하고 DB volume을 보존한다.

```powershell
docker compose --env-file .env.docker down
```

로컬 검증 DB volume까지 삭제하려면 데이터가 불필요한지 확인한 뒤에만 실행한다.

```powershell
docker compose --env-file .env.docker down --volumes
```

두 번째 명령은 복구 불가능한 로컬 PostgreSQL volume 삭제다. 공용·운영 환경에서는 사용하지 않는다.

## 로컬과 공개 배포의 차이

로컬 Compose 기본 `APP_ENV=development`는 HTTP 검증 때문에 Secure cookie를 사용하지 않는다. 공개
staging/production은 반드시 reverse proxy TLS 뒤에서 `APP_ENV=production`을 설정해야 하며, 이때 앱은
PostgreSQL과 Secure cookie를 강제한다. 단순히 이 Compose 파일을 인터넷에 노출하는 것은 배포 완료가 아니다.

## Backup 운영 경계

- bind mount `backups/`의 실제 dump는 Git에서 제외한다.
- dump에는 암호화 profile과 세션 hash가 있으므로 접근통제·저장 암호화·보존기간이 필요하다.
- 복원 검증은 암호화 키 복구 검증을 대체하지 않는다. 운영 복구 훈련은 DB dump와 같은 시점의 key version을
  함께 사용할 수 있어야 한다.
- 온라인 row 삭제는 이미 생성된 dump·WAL의 즉시 물리 삭제를 보장하지 않는다.

## CI

GitHub Actions `container-runtime` job은 임시 secret을 생성하고 Compose config, 두 image build, 전체 stack과
운영 검증기를 실행한 뒤 항상 container·volume을 제거한다. 이 job이 통과하기 전에는 Docker P0를 완료로
표시하지 않는다.

## 현재 로컬 제약

2026-08-13 15:42 KST 확인 시 PM Windows 환경에는 Docker CLI/Desktop이 설치되어 있지 않았다. 따라서 image와
PostgreSQL live 검증은 GitHub Actions에서 먼저 수행하고, Docker Desktop 설치 후 같은 운영 검증기를 로컬에서
재실행한다.
