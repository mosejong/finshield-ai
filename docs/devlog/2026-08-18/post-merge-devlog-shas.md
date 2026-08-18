# 병합 후 정리 — devlog SHA, 첫 릴리스 실측, rate limit flake

- 날짜: 2026-08-18 (Asia/Seoul)
- 담당 역할: PM 겸 백엔드
- 브랜치: `chore/post-merge-devlog-shas`
- worktree: `c:\Users\user\Desktop\project\finshield-ai`
- 시작 12:20 / 종료 13:35

## 목표와 비범위

**목표**

1. PR #58 squash 병합으로 죽은 참조가 된 devlog SHA 를 main 기준으로 고친다.
2. `Release images` 첫 실행 결과를 실측해 기록하고, **틀린 것으로 드러난 문서를 고친다.**
3. 위 검증 중 발견한 것을 그냥 넘기지 않는다.

**비범위**

- VM 실배포, 도메인·인증서 (P0-4, 사용자 결정 대기)
- rate limit 을 슬라이딩 창으로 바꾸는 것 (아래 판단 참고)

## 변경 이유

세 갈래다.

**1. squash 병합이 devlog 를 깨뜨렸다.** `docs/devlog/2026-08-18/*.md` 두 편이 작업
브랜치 커밋 SHA 를 가리키고 있었는데, PR #58 이 squash 로 들어가면서 그 커밋들은
main 에서 도달할 수 없게 됐다. 브랜치를 지우는 순간 죽은 참조가 된다. 증상만
고치면 다음에 또 생기므로 `docs/14` 에 규칙을 추가했다 — **main 기준 SHA 를 먼저
적고 브랜치 SHA 는 부기한다.**

**2. 문서에 짐작을 사실처럼 적어 뒀다.** `docs/28` P1-3 과 `docs/31` 3-2 에 "워크플로가
처음 만든 ghcr 패키지는 저장소가 public 이어도 private 으로 생성된다" 고 단정해
뒀는데, 실제로 돌려 보니 **둘 다 public 이었다.** 확인하지 않은 일반론을 절차 문서에
넣은 것이 원인이다.

**3. `pytest -q` 가 실패했다.** 문서만 고친 상태에서 `tests/test_rate_limits.py::
test_analyze_is_limited_end_to_end` 가 깨졌다. 재실행하면 통과하는 flake 였다.
"다시 돌리니 되네" 로 넘기면 CI 가 빨간불을 신뢰할 수 없게 된다.

## 구현 및 데이터 흐름

런타임 코드 변경 없음. 변경은 문서와 테스트 fixture 다.

`limited_client` fixture 가 `rate_limit_service()` 를 한 번 만들어 캐시에 올린 뒤,
그 인스턴스의 `_clock` 만 고정 시각 `NOW` 로 바꾼다. `build_rate_limit_service` 의
저장소 선택·비밀 검증 경로는 그대로 지나므로 통합 테스트의 성격이 유지된다.

## 변경 파일

| 파일 | 변경 |
|---|---|
| `docs/28-production-readiness.md` | P1-3 제목·"아직 안 된 것" 갱신, 패키지 공개 범위 문단 정정, rate limit 표에 "창 계산" 행 추가 |
| `docs/31-public-deployment.md` | 3-2 에 익명 확인 명령 추가·private 단정 제거, 11-1 태그 경로 미검증 명시, 11-4 VM 설치 절차 정정 |
| `docs/devlog/2026-08-18/deploy-image-pipeline.md` | 검증 8·9 추가, 위험 항목 갱신 |
| `docs/devlog/2026-08-18/llm-explanation-contract.md` | main 기준 SHA 로 정정 |
| `docs/14-development-workflow.md` | 커밋 SHA 기록 규칙 추가 |
| `tests/test_rate_limits.py` | fixture 시계 고정, 버스트 성질 테스트 1건 추가 |

## 아키텍처·설계 결정

### 고정 창의 버스트를 고치지 않고 명시했다

flake 를 파고들다 창 계산의 실제 성질이 드러났다. `_floor_to_window` 는 **epoch 정렬
고정 창** 이므로, 창이 닫히기 직전에 한도를 채우고 창이 바뀌자마자 다시 채우면
0.3초 안에 **한도의 2배** 가 통과한다.

슬라이딩 창으로 바꾸지 않았다. 이 한도의 목적은 공정 분배가 아니라 "한 명이 서비스를
갈아버리는 것" 의 차단이고(`docs/28` 2절), 지속적 남용은 고정 창으로도 막힌다.
슬라이딩 창은 요청마다 이력을 읽어야 해서 저장소 비용이 오르는데, 1GB VM 에서
그 비용을 지불할 이유가 지금은 없다.

대신 **가정이 굳는 것** 을 막았다. 누군가 "한도가 30이면 어떤 1분에도 30을 넘지
않는다" 고 믿고 다른 통제를 설계하면 그때 사고가 난다. 그래서
`test_a_client_can_burst_twice_the_limit_across_a_boundary` 로 성질을 고정하고
`docs/28` rate limit 표에 한 행을 넣었다. 창 계산을 바꾸면 이 테스트가 깨지므로
문서도 같이 고치게 된다.

### 테스트 시계를 프로덕션 API 로 노출하지 않았다

`build_rate_limit_service` 에 `clock` 인자를 추가하는 방법도 있었지만, 테스트만을
위해 프로덕션 함수 시그니처를 넓히는 셈이다. fixture 안에서 인스턴스 속성 하나를
`monkeypatch` 하는 쪽이 영향 범위가 훨씬 좁다.

## 공식 근거와 provenance

- ghcr 공개 범위: 레지스트리 익명 토큰 + `tags/list` 응답 (2026-08-18 실측, 아래).
- 저장소 공개 범위: `gh repo view --json visibility` → `PUBLIC`.
- 인과("public 저장소라서 public 패키지") 는 **확인하지 못했다.** 문서에 그렇게 적지
  않고 관측 결과만 남겼다.

## 실행한 검증과 실제 결과

**1. flake 를 결정적으로 재현했다**

시계를 창 경계 0.5초 앞에 두고 50ms 씩 전진시키며 32건을 쏘는 스크립트를 만들었다
(스크래치패드, 저장소 밖).

```
statuses: [200 x 32]
200 count: 32   429 count: 0
test assertion holds: False
```

10번째 요청에서 창이 바뀌며 카운터가 리셋됐다. **추측이 아니라 재현된 원인이다.**
실제 실행에서의 발생 확률은 대략 (32건에 걸리는 시간)/60초 다.

**2. 새 테스트가 공허하지 않은지 확인했다**

`_floor_to_window` 의 창 크기를 3600초로 강제하는 변이를 넣고 돌렸다.

```
FAILED tests/test_rate_limits.py::test_a_client_can_burst_twice_the_limit_across_a_boundary
1 failed
```

변이를 되돌린 뒤 `git diff --stat app/services/rate_limits.py` 가 비어 있는 것까지
확인했다. 이 저장소가 과거에 두 번 만든 "절대 실패할 수 없는 검사" 를 반복하지
않으려는 절차다.

**3. ghcr 패키지 공개 범위**

`gh api /user/packages` 는 토큰에 `read:packages` 가 없어 403 이었다. 레지스트리에
직접 익명으로 물었다.

```
finshield-backend -> HTTP 200
finshield-web     -> HTTP 200
```

**둘 다 public.** 문서의 단정이 틀렸다.

**4. VM 설치 명령을 실행 전에 확인했다**

VM 이 뜬 뒤(`finshield`, `us-west1-b`, Debian 12) `docs/31` 11-4 를 그대로 붙여넣기
직전에 패키지 존재 여부를 packages.debian.org 에서 확인했다. **두 개가 틀렸다.**

- `docker-compose-v2` — bookworm 에 **없다** ("No such package"). trixie 부터 들어온다.
  문서대로 하면 `apt-get install` 이 통째로 실패한다.
- `python3-venv` — bookworm 에서 **별도 패키지** (3.11.2-1+b1). 없으면 다음 줄의
  `python3 -m venv` 가 `ensurepip is not available` 로 죽는다.

Docker 공식 설치 절차(docs.docker.com/engine/install/debian)로 교체하고
`python3-venv` 를 추가했다. `docker-buildx-plugin` 은 이 VM 이 빌드하지 않으므로
일부러 뺐다. **아직 VM 에서 실행해 보지는 않았다** — 다음 단계다.

**5. 전체 테스트 (2회 연속)**

```
553 passed, 2 skipped in 19.22s
553 passed, 2 skipped in 18.33s
```

552 → 553 (버스트 테스트 1건 추가).

## 보안·개인정보 영향

- **런타임 코드 변경 없음.** 새 외부 통신·업로드·도구·민감 필드 없음.
- **rate limit 의 실제 강도는 바뀌지 않았다.** 고친 것은 테스트뿐이고, 창 계산은
  그대로다. 다만 그 강도의 한계(경계 버스트)가 이제 문서와 테스트에 드러나 있다.
- ghcr 패키지가 public 인 것은 이미 검토된 상태다 — 이미지에 비밀이 들어가지 않고
  `secrets/` 는 런타임 mount 다 (`docs/31` 11-1).
- 재현 스크립트는 저장소 밖 스크래치패드에 두었고 커밋하지 않는다.

## 실패, 수정, 리뷰 이력

**1. 문서에 짐작을 사실로 적었다.** "패키지는 private 으로 생성된다" 는 확인하지 않은
일반론이었고 실측이 뒤집었다. 두 문서를 관측 결과로 고치고, 다음 사람이 다시 짐작하지
않도록 **확인 명령 자체** 를 절차에 넣었다.

**2. 테스트 실패를 재실행으로 덮을 뻔했다.** 단독 실행은 통과, 전체 재실행도 통과라
"환경 문제" 로 넘길 수 있는 모양이었다. 재현해 보니 실제 결함이었고, 그 과정에서
문서에 없던 창 성질까지 드러났다.

**3. 재현 스크립트가 처음에 임포트 순서로 죽었다.** `DATABASE_URL` 을 `app.main`
임포트 전에 설정했더니 `app/api/routes/profiles.py` 가 모듈 로드 시점에
`ProfileStorageConfigurationError` 를 냈다. 실제 fixture 는 임포트 후에 환경변수를
설정한다. 순서를 맞춰 해결했다.

## 알려진 위험과 다음 작업

**위험**

- **태그 push 경로 미검증.** run #1 은 `workflow_dispatch` 라 `sha-` 태그만 붙었다.
  `v*` 를 밀었을 때의 동작은 아직 모른다.
- **VM 실배포 미검증.** pull 은 개발 머신에서만 확인했다. e2-micro 1GB 는 별개 문제다.
- **경계 버스트는 남아 있다.** 명시했을 뿐 없애지 않았다. 인증 없는 `/analyze` 가
  비싸지면 재검토 대상이다.
- **`feature/frontend-accessibility-e2e` 를 아직 지우면 안 된다.** 이 브랜치가
  병합되기 전까지 그 브랜치가 옛 SHA 를 살려 두는 유일한 참조다.

**다음**

1. P0-4 — 도메인 · ACME 연락처 · `secrets/profile_encryption_keys.txt` 오프호스트
   보관 위치. 셋 다 사용자 결정 대기.
2. P2-2 — 프로바이더를 `evaluation/` 에 연결해 `llm_only` 를 `not_run` 에서 뺀다.
   Gemini 키가 `secrets/gemini_api_key.txt` 에 들어와야 시작할 수 있다.

## 커밋 SHA

병합 후 main 기준으로 갱신한다 (`docs/14` 규칙).

- **main**: 미병합
- 브랜치 `chore/post-merge-devlog-shas`: `de0a05b` (devlog SHA 정정), 이번 커밋

## PR

미생성.
