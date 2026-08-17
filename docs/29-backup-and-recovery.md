# 29. 백업과 복구 절차

목적: 데이터를 잃었을 때 **실제로 되돌릴 수 있는 상태**를 만들고, 그 절차를 한 문서 안에 둔다. 작성 기준일 2026-08-15.

판단 기준은 하나다. **"백업 파일이 있다"는 복구가 아니다.** 복원해서 프로필이 열려야 복구다.

## 0. 먼저 읽을 것 — 반쪽 백업은 백업이 아니다

FinShield의 금융 프로필은 애플리케이션 레벨에서 암호화돼 DB에 들어간다(`docs/22`, `adr/0002`). 그래서 복구에는 **두 가지가 모두** 필요하다.

| 잃은 것 | 남은 것 | 결과 |
|---|---|---|
| DB | 암호화 키 | 열 대상이 없다 |
| 암호화 키 | DB 덤프 | **열 수 없는 바이트열만 남는다** |
| 둘 다 있음 | — | 복구 가능 |

두 번째 줄이 이 문서가 존재하는 이유다. DB 덤프는 자동화됐지만 `secrets/profile_encryption_keys.txt`는 **자동으로 백업되지 않는다.** 이 파일은 `.gitignore`에 있고 볼륨에도 없다. 키를 따로 보관하지 않으면 백업 파일 7세대가 전부 무용지물이다.

키 보관은 사람이 한다. 자동화하지 않는 이유는, 키를 백업 파일과 같은 곳에 두면 백업 하나만 유출돼도 프로필이 통째로 열리기 때문이다. **DB 덤프와 암호화 키는 서로 다른 장소에 보관한다.**

## 1. 구성

| 부분 | 파일 | 하는 일 |
|---|---|---|
| 백업 루프 | `deploy/backup-loop.sh` | 주기적 `pg_dump` + 세대 회전 + 성공 heartbeat |
| healthcheck | `deploy/backup-healthcheck.sh` | 마지막 **성공** 시각의 나이를 본다 |
| 컨테이너 | `compose.yaml`의 `backup` | `db`와 같은 이미지 digest, `migration` 완료 후 기동 |
| 복원 리허설 | `scripts/rehearse_backup_restore.py` | 덤프 → 임시 DB 복원 → **복호화** → 정리 |
| 복호화 검증 | `scripts/verify_restored_profiles.py`, `app/services/backup_verification.py` | 행이 지금 가진 키로 열리는지 |

### 왜 별도 컨테이너인가

`pg_dump`는 서버보다 major 버전이 낮으면 거부한다. `backup`은 `db`와 **같은 이미지 digest**를 쓴다 — `compose.yaml` 상단의 `x-postgres-image` anchor 한 곳에서만 정의하므로 두 서비스가 어긋날 수 없다.

backend 이미지에 postgres client를 넣는 선택지도 있었다. 그러면 인터넷에 노출된 API 이미지에 덤프 도구가 실리고, 서버와 맞춰야 할 버전이 하나 더 생긴다.

이 컨테이너만 root로 돈다. postgres 이미지는 `USER`를 지정하지 않고, 여기에 uid를 강제하면 호스트 bind mount 소유권과 어긋나 백업이 조용히 실패한다. 대신 `cap_drop: ALL` / `no-new-privileges` / `read_only` / 포트 미개방으로 막았다. 하는 일은 `pg_dump` 호출 하나다.

### 왜 sh인가

postgres 이미지에는 python이 없다. `apk`로 넣으면 해시 고정된 의존성 정책(`docs/28` P0-5)에 구멍이 난다. 그래서 루프는 `sh`로 최소한만 두고, **진짜 확인이 필요한 "복원과 복호화가 되는가"는 backend 이미지에서 python이 맡는다.**

## 2. 설정

| 환경변수 | 기본값 | 의미 |
|---|---|---|
| `FINSHIELD_BACKUP_INTERVAL_SECONDS` | `86400` | 덤프 주기. 30 ~ 604800 |
| `FINSHIELD_BACKUP_KEEP` | `7` | 보관 세대 수. 1 ~ 365 |
| `FINSHIELD_BACKUP_DIR` | `/backups` | 컨테이너 안 저장 위치 |
| `FINSHIELD_BACKUP_HEARTBEAT_PATH` | `/tmp/finshield-backup-heartbeat` | 마지막 성공 시각 |

범위를 벗어나거나 정수가 아니면 컨테이너가 **exit 2로 죽는다.** 설정 오류는 재시도해도 낫지 않는다. 조용히 아무것도 안 하는 것보다 눈에 띄는 편이 낫다.

DB 비밀번호는 `PGPASSWORD`로 넘기지 않는다. 환경변수는 `docker inspect`와 자식 프로세스 전체에 그대로 보인다. 루프가 tmpfs 위에 `0600` pgpass 파일을 만들어 쓴다.

## 3. 저장 위치

호스트의 `./backups`를 컨테이너 `/backups`에 bind mount한다. `postgres-data` 볼륨 **밖**이므로 `docker compose down --volumes`나 볼륨 손상으로 백업이 함께 사라지지 않는다.

파일명은 `finshield-<UTC>.dump` (예: `finshield-20260815T031500Z.dump`), 형식은 `pg_dump --format=custom`이다.

**아직 같은 호스트 안이다.** 호스트가 통째로 사라지면 백업도 같이 사라진다. 호스트 밖 반출은 5절에 남은 작업으로 적었다.

## 4. 복구 절차

### 4-1. 빈 환경에서 서비스 되살리기

```bash
# 0. 손에 있어야 하는 것 두 가지
#    - finshield-<UTC>.dump
#    - secrets/profile_encryption_keys.txt  (자동 백업되지 않는다. 0절 참고)

# 1. 스택 기동 (DB는 비어 있는 상태)
docker compose up --detach db
docker compose run --rm migration

# 2. 덤프를 backup 컨테이너가 보는 위치에 둔다
cp finshield-20260815T031500Z.dump ./backups/

# 3. 복원
docker compose up --detach backup
docker compose exec -T backup sh -ec \
  'pg_restore --dbname="$PGDATABASE" --clean --if-exists --exit-on-error \
     /backups/finshield-20260815T031500Z.dump'

# 4. 복호화까지 확인한다. 여기까지 통과해야 복구다.
docker compose run --rm --no-deps -T backend \
  python -m scripts.verify_restored_profiles

# 5. 나머지 기동
docker compose up --detach
```

4번이 `{"recoverable": true, ...}`를 내고 exit 0이어야 한다. `unavailable_key_ids`에 값이 있으면 **DB는 돌아왔지만 그 세대의 키를 안 들고 온 것이다.** 키 파일을 다시 확인한다.

`pg_restore`에 `--exit-on-error`가 붙어 있다. 기본값은 오류를 세면서 계속 진행하고 종료 코드 0으로 끝나기 때문에, 이게 없으면 **절반만 복원된 DB를 성공으로 읽는다.**

### 4-2. 복원 리허설 (평상시)

운영 DB를 건드리지 않고 같은 절차를 연습한다.

```bash
python scripts/rehearse_backup_restore.py
python scripts/rehearse_backup_restore.py --dump finshield-20260815T031500Z.dump
```

하는 일: 최신 덤프 선택 → 신선도 확인 → 임시 DB `finshield_rehearsal` 생성 → 복원 → **복호화** → 임시 DB 삭제.

출력 예:

```json
{"database":"finshield_rehearsal","decrypted":3,"dump":"finshield-20260815T031500Z.dump",
 "failed":0,"profiles":3,"recoverable":true,"rehearsal":"succeeded","unavailable_key_ids":[]}
```

출력에는 건수와 key id만 담는다. key id는 이미 `encryption_key_id` 열에 평문으로 저장된 값이라 노출 범위가 늘지 않는다. 복호화된 프로필은 어디에도 남기지 않는다.

**권장 주기: 월 1회, 그리고 키를 로테이션한 직후.** 로테이션 중에 뜬 백업은 두 세대의 키로 쓰인 행이 섞여 있어, 옛 키를 내리면 그 시점 이전 백업이 열리지 않는다.

## 5. 무엇이 검증되고 무엇이 안 되는가

검증되는 것:

| 확인 | 어디서 |
|---|---|
| 스케줄이 실제로 파일을 남긴다 | `scripts/verify_compose_runtime.py`의 `verify_backup_schedule()` (CI) |
| 세대 회전이 최신 N개만 남긴다 | `tests/test_backup_loop.py` |
| 실패한 덤프가 멀쩡한 세대를 지우지 않는다 | 같은 파일 |
| 마지막 **성공** 시각이 healthcheck에 반영된다 | 같은 파일 |
| 복원된 행이 실제로 열린다 | `tests/test_backup_verification.py`, 리허설 |
| 키를 잃은 백업이 **실패로 나온다** | `tests/test_backup_verification.py` |

검증되지 않는 것:

- **호스트 전체 손실.** 리허설은 같은 PostgreSQL 인스턴스 안의 임시 DB로 복원한다. 백업 파일을 호스트 밖으로 내보내는 절차와 함께 별도로 훈련해야 한다.
- **암호화 키 보관.** 사람이 하는 절차이고 자동 점검이 없다. 리허설이 통과하는 이유는 지금 이 호스트에 키가 있기 때문이지, 키가 안전하게 보관돼 있기 때문이 아니다.
- **백업 실패 알림.** healthcheck가 unhealthy를 띄워도 사람에게 알리는 경로는 없다(`docs/28` P1-1). 그때까지는 `docker compose ps`를 봐야 안다.

## 6. 왜 기존 검사로는 부족했는가

이전 CI 복원 검사는 이랬다.

```sql
SELECT position('2800000' in encode(encrypted_profile, 'escape')) = 0 FROM financial_profiles
```

"알려진 금융 값이 평문으로 보이지 않는다"만 본다. **이 조건은 무작위 바이트열도 통과한다.** 암호화가 됐다는 것만 확인할 뿐 되돌릴 수 있다는 것은 확인하지 못하고, 그래서 **키를 잃은 백업이 초록불로 나온다.**

지금은 합격 기준이 "행이 돌아왔다"가 아니라 **"행을 복호화했다"**이다. 부수적으로 두 가지가 더 증명된다.

- 봉투 안의 `profile_id`를 행의 것과 대조하므로, 덤프/복원 과정에서 행 결합이 깨지지 않았다는 것
- 행이 0건이면 실패다. 스키마만 돌아온 복원은 복구 가능성에 대해 아무것도 증명하지 않는다

표본만 열어보지 않고 전체를 훑는 것도 같은 이유다. 키 로테이션 중이면 특정 세대 키로 쓰인 행만 안 열리는 상황이 실제로 생긴다.
