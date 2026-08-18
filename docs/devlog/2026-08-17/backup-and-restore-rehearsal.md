# 백업 자동화와 복원 리허설 (P0-3)

- 날짜: 2026-08-17
- 브랜치: `feature/frontend-accessibility-e2e`
- 범위: `deploy/backup-{loop,healthcheck}.sh`, `compose.yaml`,
  `app/{services,core}/backup_verification.py`, `app/security/profile_encryption.py`,
  `scripts/{rehearse_backup_restore,verify_restored_profiles,verify_compose_runtime}.py`,
  `tests/test_backup_{loop,verification}.py`, `.github/workflows/ci.yml`, 문서

## 배경

P0-3의 알려진 문제는 "운영 백업 스케줄이 없다"였다. `pg_dump`/restore 로직은
`scripts/verify_compose_runtime.py` 안, 즉 CI 검증 경로에만 있었다. 복구가 필요한 시점에
백업이 없는 상태와 "백업 코드가 있는" 상태는 같은 결과가 된다.

작업하면서 더 나쁜 것을 발견했다. **기존 복원 검사는 실패할 수 없는 검사였다.**

```sql
SELECT position('2800000' in encode(encrypted_profile, 'escape')) = 0 FROM financial_profiles
```

"알려진 금융 값이 평문으로 보이지 않는다"만 본다. 이 조건은 **무작위 바이트열도 통과한다.**
프로필은 애플리케이션 레벨 암호화라(`docs/22`, `adr/0002`) 키를 잃으면 DB를 완벽히 복원해도
남는 것은 열 수 없는 바이트열인데, 그 상태의 백업이 이 검사에서 초록불로 나왔다.

즉 P0-3이 요구한 완료 기준("백업이 생성된다가 아니라 복원이 성공한다")을 기존 검사는 측정할
능력 자체가 없었다. 이번 작업의 절반은 스케줄을 만드는 일이었고, 나머지 절반은 **합격 기준을
"행이 돌아왔다"에서 "행을 복호화했다"로 옮기는 일**이었다.

## 설계 판단 1 — 이미지는 db와 같은 digest를 강제한다

`pg_dump`는 서버보다 major 버전이 낮으면 거부한다. `backup` 서비스가 `db`와 다른 이미지를 쓰면
어느 날 한쪽만 올라갔을 때 백업이 멈춘다. 그것도 조용히 — 컨테이너는 살아 있고 로그만 쌓인다.

`compose.yaml` 상단에 anchor를 하나 두고 두 서비스가 그것을 참조하게 했다.

```yaml
x-postgres-image: &postgres-image postgres:16-alpine@sha256:57c72fd2...
```

버전을 맞추라고 문서에 적는 대신 **어긋날 수 없는 구조로 만들었다.** 이미지를 올릴 때 한 곳만
고치면 되고, 한쪽만 고치는 실수가 불가능하다.

backend 이미지에 postgres client를 넣는 선택지도 있었다. 파일은 줄지만 인터넷에 노출된 API
이미지에 덤프 도구가 실리고, 서버와 맞춰야 할 버전이 하나 더 생긴다.

## 설계 판단 2 — 루프는 sh, 검증은 python

postgres 이미지에는 python이 없다. `apk add python3`로 넣으면 P0-5에서 세운 해시 고정 의존성
정책에 구멍이 난다. 이미지 digest는 고정돼 있는데 그 안에서 패키지를 받아오면 고정한 의미가
없다.

그래서 갈랐다.

| 하는 일 | 어디서 | 왜 |
|---|---|---|
| 주기 dump, 세대 회전, heartbeat | `sh` (postgres 이미지) | `pg_dump`가 있어야 하고, 로직이 단순하다 |
| 복원 + **복호화** 검증 | python (backend 이미지) | 키와 봉투 형식을 아는 쪽만 할 수 있다 |

`sh`라고 검증을 포기하지는 않았다. `tests/test_backup_loop.py`가 가짜 `pg_dump`/`pg_restore`를
PATH 앞에 두고 **실제 `sh`로** 루프를 돌린다. PostgreSQL 없이 회전 정책·heartbeat·실패 처리가
그대로 확인된다.

## 설계 판단 3 — 회전은 성공한 뒤에만

```sh
mv -- "$temporary" "$target"   # 성공
pruned="$(rotate)"             # 그 다음에 지운다
```

먼저 지우고 뜨는 쪽이 디스크 사용량 최고점은 낮다. 하지만 새 백업이 실패하는 날 **멀쩡한 세대를
하나 잃은 채로 끝난다.** 백업이 필요한 날은 대개 뭔가 잘못된 날이고, 그날 세대가 하나 줄어드는
것은 최악의 타이밍이다.

같은 이유로 회전은 `*.tmp`를 세지 않는다. 중단된 쓰기가 세대 하나로 잡히면 실제 보관 수가
조용히 줄어든다.

## 설계 판단 4 — `pg_dump`가 0으로 끝난 것은 증거가 아니다

새 dump마다 `pg_restore --list`를 걸어 TOC가 읽히는지 본다. 통과 못 하면 파일을 버리고
`"stage":"verify"`로 실패를 남긴다.

이게 없으면 깨진 파일이 세대 하나를 차지한 채 남고, **복원해야 하는 날에야** 알게 된다.
리허설 쪽에도 같은 계열의 함정이 있어서 `pg_restore --exit-on-error`를 붙였다. 기본값은 오류를
세면서 계속 진행하고 종료 코드 0으로 끝나기 때문에, 그대로 두면 절반만 복원된 DB를 성공으로
읽는다.

## 설계 판단 5 — heartbeat는 liveness가 아니다

P0-2에서 쓴 것과 같은 형태다. 성공한 실행만 시각을 기록하고, healthcheck는 그 나이를 본다.
임계값은 `interval * 2 + 60`초 — 한 주기 놓친 것은 순간 장애지만 두 주기 연속은 고장이다.

**계속 실패하는 루프도 프로세스는 살아 있다.** liveness를 보면 백업이 한 달째 실패해도
`healthy`로 뜬다.

시각은 epoch 초로 적었다. 정리 스케줄러(python) 쪽은 ISO 문자열을 쓰지만, `sh`에는 ISO를
신뢰성 있게 파싱할 방법이 없다. 형식을 맞추려다 healthcheck가 문자열 파싱에서 틀리는 쪽이
더 나쁘다.

## 설계 판단 6 — 비밀번호를 환경변수로 넘기지 않는다

`PGPASSWORD`는 `docker inspect`와 자식 프로세스 전체에 그대로 보인다. tmpfs 위에 `0600`
pgpass 파일을 만들고 `PGPASSFILE`로 가리킨다. pgpass 형식에서 `:`와 `\`는 escape가 필요하다.

여기서 두 번 걸렸다.

**첫째, 경로를 스크립트 안에서만 export하면 안 된다.** `docker compose exec`는 새 프로세스를
띄우고 **루프의 환경을 물려받지 않는다.** 복원 리허설의 `psql`이 비밀번호를 못 찾는다. 경로를
compose `environment:`에 둬서 컨테이너 전체가 같은 값을 보게 했다.

**둘째, 데이터베이스 칸을 `finshield`로 고정하면 안 된다.** pgpass는 데이터베이스별로
매칭된다. 리허설은 `postgres`(임시 DB 존재 확인)와 `finshield_rehearsal`(복원 대상)에도
접속하는데, 그 두 접속만 비밀번호를 못 찾아 `psql: exit 2`가 났다. 백업은 잘 뜨는데 리허설만
실패하는, 원인을 짚기 어려운 형태였다. 데이터베이스 칸만 `*`로 열고 host·port·user는 고정했다.
둘 다 실제 컨테이너를 띄워보고서야 나왔다 — `docker compose config`로는 안 잡힌다.

## 설계 판단 7 — 합격 기준을 복호화로 옮겼다

`app/services/backup_verification.py`가 복원된 DB의 프로필을 **전부** 열어본다.

```python
@property
def recoverable(self) -> bool:
    return self.profiles > 0 and self.failed == 0
```

`profiles > 0`이 붙은 이유: 행이 0건인데 성공으로 처리하면, 백업이 빈 DB를 담고 있어도 리허설은
매번 초록불이 된다. **증명한 게 없는 것과 복구 가능한 것은 다르다.**

표본이 아니라 전체를 훑는 이유: 키 로테이션 중이면 특정 세대 키로 쓰인 행만 안 열리는 상황이
실제로 생긴다. 표본 몇 개를 열어보면 그걸 놓친다.

부수적으로 두 가지가 더 증명된다. 봉투 안의 `profile_id`를 행의 것과 대조하므로 **덤프/복원
과정에서 행 결합이 깨지지 않았다**는 것, 그리고 `unavailable_key_ids`가 "DB는 돌아왔는데 이
세대의 키를 안 들고 왔다"를 정확히 짚어준다는 것.

출력에는 건수와 key id만 담는다. key id는 이미 `encryption_key_id` 열에 평문으로 저장된
값이라 노출 범위가 늘지 않고, 복호화된 프로필은 어디에도 남기지 않는다(`adr/0004`).

## CI 검증도 갈아치웠다

`verify_compose_runtime.py`가 직접 `pg_dump`를 부르던 블록을 지웠다. 대신 `backup` 서비스가
**제 주기에 남긴** 최신 파일을 기다렸다가 복원 리허설에 넘긴다.

P0-2에서 배운 것과 같다. 검증기가 직접 덤프를 뜨면 **백업 스케줄이 아예 없어도 통과한다.**
그게 정확히 P0-3이 막으려던 상황이다.

기준 시각은 컨테이너 시계로 잡는다(`date -u` in `backup`). 그 시점 이후에 생긴 파일이라야 방금
만든 프로필이 그 안에 들어 있고, 기동 직후의 빈 백업으로 통과하는 것도 같은 조건이 막는다.
CI는 이를 위해 `FINSHIELD_BACKUP_INTERVAL_SECONDS=60`으로 스택을 띄운다.

## 검증

`pytest -q` 417 passed, 1 skipped (+34).

셸 테스트는 로컬에서도 돈다. Windows에서 `sh`는 PATH 밖(`Git/usr/bin`)에 있어 `shutil.which`로
안 잡히는데, 그대로 두면 파일 전체가 조용히 skip되고 셸 스크립트는 CI에서 처음 실행된다. `git`
위치에서 유도해 찾도록 했다.

컨테이너 실기동:

| 확인 | 결과 |
|---|---|
| 백업이 주기에 뜬다 | `{"status":"succeeded","bytes":8093,"generations":1,"pruned":0}` |
| `backup` healthcheck | `healthy` |
| pgpass가 `postgres` DB에도 통한다 | `psql -d postgres -Atc "SELECT 1"` → `1` |
| 전체 실기동 검증 | `scripts/verify_compose_runtime.py` exit 0 |

`FINSHIELD_BACKUP_INTERVAL_SECONDS=60`으로 띄운 스택에서 검증기가 낸 값:

```json
"backup_schedule": {
  "decrypted": 1,
  "dump": "finshield-20260817T022522Z.dump",
  "healthy": true,
  "scheduled_within_interval_seconds": 60
}
```

`dump` 파일명의 시각은 프로필을 만든 뒤 컨테이너 시계로 찍은 기준 시각보다 뒤다. 검증기가 만든
덤프가 아니라 `backup` 서비스가 제 주기에 남긴 것이고, `decrypted: 1`은 그 안의 프로필이 임시 DB로
복원된 뒤 실제로 열렸다는 뜻이다.

로컬 스택 기동 중 `migration`이 `password authentication failed`로 죽었다. P0-3와 무관한
환경 문제였다 — `postgres-data` 볼륨이 2026-08-13자로 남아 있어 그때의 비밀번호를 들고 있었고,
그 뒤 secrets가 재생성됐다. 볼륨에 사용자 데이터가 0건인 것을 확인한 뒤 볼륨을 지우는 대신
`ALTER ROLE`로 비밀번호만 맞췄다.

## 후속 — 리눅스 CI에서 처음 드러난 것: root인데 쓸 수 없었다

이 브랜치를 처음 push했을 때 `container-runtime` 잡이 이렇게 죽었다.

```
RuntimeError: backup service did not produce a dump within its interval
```

컨테이너 로그를 보니 원인은 분명했다.

```
pg_dump: error: could not open output file "/backups/finshield-...dump.tmp": Permission denied
{"event":"backup_run","status":"failed","stage":"dump"}
```

**root로 도는 컨테이너가 파일을 못 만들었다.** root의 그 능력은 uid 0이 아니라 `CAP_DAC_OVERRIDE`에서 나오는데, 위에서 자랑스럽게 붙인 `cap_drop: ALL`이 그걸 뺐다. `./backups`는 CI runner(uid 1001) 소유 `0755`라 uid 0은 "others"에 걸린다.

같은 이미지로 재현했다. `chown 1001:1001` 한 디렉터리에 `--cap-drop=ALL`로 붙어서:

```
uid=0(root) gid=0(root)
TEST_W_SAYS_WRITABLE
REAL_WRITE_DENIED
```

윗줄이 두 번째 발견이다. 루프 기동부의 `[ -w "$BACKUP_DIR" ]`는 **통과했다.** busybox의 `test`는 euid가 0이면 모드를 보지 않고 "root는 뭐든 읽고 쓸 수 있다"며 참을 돌려준다. 이 컨테이너에서 그 줄은 어떤 입력에서도 실패할 수 없는 검사였고, 그래서 설정 오류가 `misconfigured` exit 2(즉시, 눈에 띄게)가 아니라 3분 넘게 이어지는 주기 실패로 나타났다. 이 문서 위쪽에서 SQL 검사를 두고 쓴 것과 **정확히 같은 형태**다.

Windows·macOS Docker Desktop은 bind mount 권한을 흉내만 내기 때문에 로컬 실기동에서는 통과했다. 이 브랜치의 P0-3 커밋들이 push된 적이 없어 CI에서 리눅스로 처음 돈 것이 이번이었다.

고친 것은 둘이다.

| 무엇 | 어떻게 |
|---|---|
| 실제 권한 | `backup` 서비스에만 `cap_add: DAC_OVERRIDE`. uid를 호스트에 맞추는 방법은 배포할 때마다 정확히 넘겨야 하고, 안 넘기면 지금과 똑같이 조용히 실패한다 |
| 거짓말하는 점검 | `[ -w ]` 대신 탐침 파일을 실제로 만들고 지운다. `pg_dump`가 할 일과 같은 동작 |

같은 이미지에서 고친 스크립트로 다시 확인했다.

| 조건 | 결과 |
|---|---|
| `--cap-drop=ALL`, 남의 소유 디렉터리 | `{"status":"misconfigured","reason":"backup_dir_not_writable"}`, exit 2 |
| `--cap-drop=ALL --cap-add=DAC_OVERRIDE` | 점검 통과 후 `pg_dump`까지 진행(DB 없는 임시 컨테이너라 연결 실패), 탐침 파일 잔여 없음 |

회귀 테스트 3개를 `tests/test_backup_loop.py`에 넣었다. 디렉터리 자리에 일반 파일이 있는 경우는 어디서나 돌고, 모드를 실제로 뺏는 경우는 권한이 강제되는 POSIX 환경에서만 돈다 — Windows나 root로 돌리면 그 테스트 자체가 실패할 수 없는 검사가 되므로 통과시키는 대신 skip한다.

## 남은 것

**백업이 아직 같은 호스트 안이다.** `./backups`는 `postgres-data` 볼륨 밖이라 볼륨 손상이나
`docker compose down --volumes`에는 안전하지만, 호스트가 통째로 사라지면 같이 사라진다. 리허설도
같은 PostgreSQL 인스턴스 안의 임시 DB로 복원하므로 호스트 전체 손실은 훈련되지 않는다.

**암호화 키 보관은 사람이 하는 절차다.** 리허설이 통과하는 이유는 지금 이 호스트에 키가 있기
때문이지 키가 안전하게 보관돼 있기 때문이 아니다. 키를 덤프와 같은 곳에 두면 백업 하나 유출로
프로필이 통째로 열리므로 자동화하지 않았고, 대신 `docs/29` 0절에 "둘 중 하나만 있으면 복구
불가"를 표로 먼저 적었다.

**백업 실패 알림 경로가 없다.** healthcheck가 unhealthy를 띄워도 사람에게 알리는 경로는
P1-1이다. 그때까지는 `docker compose ps`를 봐야 안다.
