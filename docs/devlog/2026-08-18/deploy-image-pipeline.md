# 배포 이미지 파이프라인과 롤백 전략 개발일지

- 날짜: 2026-08-18 (Asia/Seoul)
- 담당: backend / infra
- 브랜치: `feature/frontend-accessibility-e2e`
- worktree: 없음 (기본 작업 트리)
- 시작: 13:20 · 종료: 14:35
- 목표: `docs/28` P1-3 을 착지시킨다. GitHub Actions 가 이미지를 만들어 `ghcr.io` 로
  올리고, VM 은 pull 만 하게 한다. 그 부수 효과로 생기는 **되돌릴 지점** 을
  절차로 굳힌다.
- 비범위: 실제 태그 push, 실제 배포, 롤백 리허설, expand/contract 를 강제하는
  자동 검사, Dependabot.

## 변경 이유

두 가지가 겹쳤다.

**첫째, e2-micro 에서는 빌드가 불가능하다.** always-free `e2-micro` 는 1GB 다
(`docs/31` 11-1). `docker compose build` 의 Next 빌드는 2GB 이상을 쓰고, OOM 은
조용히 죽어서 원인이 잘 안 보인다. 즉 이 머신을 고른 순간 "VM 에서 빌드한다" 는
선택지가 사라졌고, P1-3 이 P0-4 의 **선행조건** 이 됐다.

**둘째, 지금 배포에는 되돌릴 대상이 없다.** 태그 붙은 이미지가 없으니 "이전 버전"
이라는 말이 가리킬 곳이 없다. 되돌리려면 이전 커밋을 다시 빌드해야 하는데 그
빌드가 죽는다. 즉 첫 번째 문제를 풀지 않으면 롤백 절차를 아무리 잘 적어도 실행할
수단이 없다.

그래서 순서를 이렇게 잡았다 — **되돌릴 수 있는 물건을 먼저 만들고, 그다음 절차를
적는다.** 반대로 했다면 문서만 늘고 실행은 여전히 불가능했을 것이다.

## 구현 및 데이터 흐름

```
git tag v0.3.0 && git push origin v0.3.0
        |
        v
.github/workflows/release.yml   (matrix: backend, web)
        |  docker/metadata-action  -> 태그 + sha-<full>
        |  docker/build-push-action -> linux/amd64
        v
ghcr.io/mosejong/finshield-backend:v0.3.0
ghcr.io/mosejong/finshield-web:v0.3.0
        |
        v  (VM)
FINSHIELD_IMAGE_TAG=v0.3.0
docker compose -f compose.yaml -f compose.https.yaml -f compose.deploy.yaml pull
        |
        v
compose.deploy.yaml 이 build: 를 !reset 으로 지우고 image: 를 박는다
```

롤백은 같은 그림에서 `FINSHIELD_IMAGE_TAG` 만 이전 값으로 바꾼 것이다. 마이그레이션은
되돌리지 않는다 — 아래 "아키텍처 결정" 참고.

## 변경 파일

| 파일 | 상태 | 내용 |
|---|---|---|
| `.github/workflows/release.yml` | 신규 | `v*` 태그 / `workflow_dispatch` 로 두 이미지를 ghcr 에 push |
| `compose.deploy.yaml` | 신규 | 네 서비스의 `build:` 제거 + ghcr 이미지 고정 |
| `tests/test_deploy_images.py` | 신규 | 두 compose 파일의 대응 관계 검사 (21건) |
| `.github/workflows/ci.yml` | 수정 | 배포 조합 `config --quiet` + 태그 없을 때 거부 확인 |
| `requirements-dev.in` | 수정 | `pyyaml>=6.0,<7.0` 을 직접 의존성으로 선언 |
| `requirements-dev.txt` | 재생성 | pyyaml 이 `-r requirements-dev.in` 경유로 기록됨 |
| `docs/28-production-readiness.md` | 수정 | P1-3 전면 재작성, 6절 항목 번호 정정 |
| `docs/31-public-deployment.md` | 수정 | 3-2 신설·이후 절 재번호, 9절을 9-1/9-2 로 분리, 2절 환경변수 셋으로 |

## 아키텍처 결정

**1. `latest` 태그를 만들지 않는다.**

`compose.deploy.yaml` 은 `${FINSHIELD_IMAGE_TAG:?...}` 로 태그를 필수로 받고,
`release.yml` 도 `latest` 를 붙이지 않는다. `latest` 는 편의를 주고 되돌릴 능력을
가져간다 — 지금 무엇이 돌고 있는지 모르면 "이전 것으로 돌린다" 를 실행할 수 없고,
그 사실을 사고 조사 중에 알게 되는 것이 최악이다. 불편한 쪽을 택했다.

**2. 롤백은 `alembic downgrade` 가 아니다.**

이게 이번 작업에서 가장 중요한 판단이다. `migrations/versions/` 의 세 `downgrade()`
는 전부 `drop_table` / `drop_index` / `drop_constraint` 다. 즉 **실행하면 되돌리기가
아니라 데이터 삭제다.** 사고 대응 중에 칠 명령이 아니다.

그래서 롤백을 "이전 태그로 다시 올린다" 로 정의하고, 스키마는 새 버전 그대로 둔다.
이게 성립하려면 마이그레이션이 이전 이미지에서도 안전해야 한다 → expand/contract:

- 추가는 nullable 또는 기본값 있음 (구 코드가 무시할 수 있어야 한다)
- 삭제·이름 변경은 그 컬럼을 안 쓰게 된 릴리스에서 하지 않고 한 릴리스 뒤로 미룬다
- rename 은 rename 으로 하지 않는다. "추가 → 양쪽 쓰기 → 읽기 이전 → 삭제" 로 쪼갠다
- 파괴적 마이그레이션은 코드 변경과 섞지 않고 릴리스를 혼자 쓴다

대가는 컬럼 하나 지우는 데 릴리스 두 번이 필요하다는 것이다. 되돌릴 수 없는 배포를
하는 것보다 낫다고 판단했다.

**3. digest 를 job summary 에 남긴다.**

태그는 옮겨 붙을 수 있고 digest 는 그렇지 않다. "그때 무엇이 돌고 있었나" 에 답할
수 있어야 사고 조사가 성립한다.

**4. `linux/amd64` 만 만든다.**

e2-micro 는 x86_64 다. arm64 를 같이 만들면 빌드 시간만 두 배가 되고 아무도 쓰지
않는다. 필요해지는 날 추가한다.

**5. 드리프트를 CI 가 아니라 pytest 로 잡는다.**

`docker compose config --quiet` 는 이 실패를 못 잡는다. 새 빌드 서비스를
`compose.yaml` 에 추가하고 override 를 잊어도 **문법은 멀쩡하기 때문이다.**
그래서 `tests/test_deploy_images.py` 가 문법이 아니라 대응 관계를 본다. Docker 를
요구하지 않으므로 Docker 없는 개발 머신에서도 돈다.

## 공식 근거와 provenance

해당 없음 — 금융 사실·상품·요율을 다루지 않는 인프라 작업이다.

## 실행한 검증과 실제 결과

**1. 배포 override 해석 (로컬 Docker Compose v5.3.1)**

```
$ FINSHIELD_IMAGE_TAG=v0.0.0-ci ... docker compose -f compose.yaml \
    -f compose.https.yaml -f compose.deploy.yaml config
backend:   image: ghcr.io/mosejong/finshield-backend:v0.0.0-ci
migration: image: ghcr.io/mosejong/finshield-backend:v0.0.0-ci
retention: image: ghcr.io/mosejong/finshield-backend:v0.0.0-ci
web:       image: ghcr.io/mosejong/finshield-web:v0.0.0-ci
```

7개 서비스 전부 `image:` 를 가지고 `build:` 는 **하나도 남지 않았다.** db / backup /
proxy 는 원래대로 digest 고정 이미지를 유지했다.

**2. 태그를 빼면 거부하는지**

```
error while interpolating x-backend-image: required variable
FINSHIELD_IMAGE_TAG is missing a value: FINSHIELD_IMAGE_TAG 를 지정한다
```

**3. 문서에 적은 세 조합 전부 통과**

- `compose.yaml + https + deploy` → OK
- `compose.yaml + https + deploy + acme-staging` → OK (3-3 절)
- `compose.yaml + deploy` → OK (9-2 절, HTTPS 내린 상태)

**4. 드리프트 가드가 실제로 터지는지**

`compose.deploy.yaml` 에서 `web` 항목을 지우고 돌렸다.

```
FAILED test_every_built_service_is_overridden[web]
FAILED test_every_override_drops_the_build_section[web]
FAILED test_every_override_pins_an_image[web]
FAILED test_every_override_requires_an_explicit_tag[web]
4 failed, 17 passed
```

복구 후 21 passed. **검사가 통과하는 것만 보지 않고, 깨져야 할 때 깨지는지도 봤다.**

**5. 워크플로 YAML 파싱**

`release.yml` → `jobs: ['build']`, matrix `['backend', 'web']`,
`permissions: {contents: read, packages: write}`.
`ci.yml` → 4개 job 유지.

**6. lock 재생성**

CI 와 같은 명령으로 두 lock 을 재생성했다. `requirements.txt` 무변경,
`requirements-dev.txt` 는 pyyaml 의 `# via` 주석만 바뀌었다 (`uvicorn` →
`-r requirements-dev.in` + `uvicorn`). `deps-lock` job 의 `git diff --exit-code`
가 통과할 상태다.

**7. 전체 테스트**

```
552 passed, 2 skipped in 19.39s
```

(531 → 552, 신규 21건)

## 보안·개인정보 영향

- **새 외부 통신 없음.** 런타임 코드 변경이 없다. `release.yml` 은 CI 안에서만 돈다.
- **`GITHUB_TOKEN` 권한을 최소로 잡았다.** `contents: read` + `packages: write`.
  워크플로 기본 권한에 의존하지 않고 job 에 명시했다.
- **이미지에 비밀이 들어가지 않는다.** `secrets/` 는 런타임 mount 이고
  (`compose.yaml` 의 `x-backend-secrets`), `Dockerfile` 은 이를 복사하지 않는다.
  그래서 ghcr 패키지를 공개로 둘 수 있다.
- **ghcr 패키지 기본 공개 범위가 함정이다.** 워크플로가 처음 만든 패키지는 저장소가
  public 이어도 private 으로 생성된다. VM 에서 pull 이 인증 오류로 죽고 원인이
  코드에 없어서 헤매게 되므로 `docs/31` 3-2 에 명시했다.
- **로그 노출 없음.** digest 와 태그만 job summary 에 남는다.

## 실패, 수정, 리뷰 이력

**1. `release.yml` 첫 줄에 깨진 문자가 들어갔다.** 파일 선두에 `« ` 가 붙어 YAML 이
아닌 상태로 저장됐다. 파싱 검증에서 잡아 제거했다. 이 저장소에서 한국어 텍스트를
파일로 쓸 때 반복되는 인코딩 문제와 같은 계열이다 (앞선 devlog 의 heredoc 실패).

**2. `docs/28` 6절 항목 번호가 밀려 있었다.** P1-3 을 6번으로 끼워 넣을 때 그 아래
설명 문단의 "6번은 코드·구성·검증기가 모두 준비됐고…" 가 갱신되지 않아, P0-4 를
설명하는 문장이 P1-3 을 가리키고 있었다. 이번에 7번으로 고치고, 6번(P1-3)에 대한
문단을 따로 추가했다.

**3. pyyaml 이 우연히 들어와 있었다.** 두 lock 에 `pyyaml==6.0.3` 이 있지만
`uvicorn[standard]` 경유의 전이 의존성이었다. 새 테스트가 이걸 직접 쓰므로, 그 extra
가 빠지는 날 collect 단계에서 깨진다. `requirements-dev.in` 에 선언하고 lock 을
재생성했다.

**4. "검사가 통과한다" 만 보지 않았다.** 이 저장소는 busybox `[ -w ]` 와 백업 SQL
검사에서 **절대 실패할 수 없는 검사** 를 두 번 만들었다. 그래서 이번에는 (a) `web`
항목을 실제로 지워 4건이 FAIL 하는 것을 확인했고, (b) `BUILT_SERVICES` 가 빈 목록이
되면 parametrize 가 통째로 공허해지므로 `test_the_base_file_still_builds_something`
을 따로 뒀다.

## 알려진 위험과 다음 작업

**위험**

- **한 번도 배포해 본 적이 없다.** `release.yml` 은 아직 돌지 않았다. 검증된 것은
  YAML 파싱과 compose 해석까지다. 첫 태그 push 가 곧 첫 검증이다.
- **expand/contract 는 규칙일 뿐 강제되지 않는다.** 어기면 리뷰에서만 걸린다.
  `downgrade()` 에 `drop_` 이 있는 마이그레이션을 감지하는 검사를 붙일 수 있지만,
  그건 정당한 경우까지 막으므로 판단이 더 필요하다.
- **롤백 리허설이 없다.** `docs/29` 의 복원 리허설처럼 실제로 이전 태그로 되돌려
  보기 전까지는 9-1 절도 "적어 둔 절차" 에 불과하다.
- `docker/*-action` 을 태그(`@v4`, `@v6`)로 고정했다. 저장소 다른 곳은 digest 고정
  기준인데 여기만 다르다. Dependabot(`docs/28` P1-5)이 붙으면 같이 정리한다.

**다음**

1. `workflow_dispatch` 로 이미지 빌드만 먼저 돌려 본다 (도메인과 무관하게 가능).
2. ghcr 패키지 공개 범위를 확인한다.
3. P0-4 — 도메인·ACME 연락처·`secrets/profile_encryption_keys.txt` 의 오프호스트
   보관 위치. 셋 다 사용자 결정 대기.
4. P2-2 — 프로바이더를 `evaluation/` 에 연결해 `llm_only` 를 `not_run` 에서 뺀다.

## 커밋 SHA

- (커밋 후 기입)

## PR

- #58 (`feature/frontend-accessibility-e2e`)
