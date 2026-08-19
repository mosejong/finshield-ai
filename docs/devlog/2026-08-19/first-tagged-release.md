# 2026-08-19 — 첫 태그 릴리스 `v0.1.0` 과 재배포 절차

## 왜 지금

제출물 ③(웹서비스 URL)이 막혀 있었다. 공개 URL 이 설명 엔드포인트를 404 로
돌려주고 있었고, 원인을 "VM 이 아직 pull 을 안 했다" 로 알고 있었다.

**그게 아니었다.** ghcr 를 확인하니 이미지가 두 개뿐이었고 둘 다
`workflow_dispatch` 로 만든 `sha-…` 태그였다. 최신 것이 `4457f0e`
(2026-08-18, PR #60) 이다. 설명 계층은 그 뒤에 병합됐다.

**설명 엔드포인트를 담은 이미지는 애초에 존재한 적이 없다.** VM 에서 아무리
pull 해도 404 는 안 없어진다. 먼저 만들어야 했고, 그건 내가 할 수 있는 일이다.

## 한 일

| | |
|---|---|
| 태그 | `v0.1.0` (annotated) — 커밋 `30ba35b` |
| 워크플로 | `Release images` run #3, backend/web 두 job 모두 성공 |
| backend digest | `sha256:c9c0864ccc28cd5ff500f548b617a3f21200103f3efbd7a1140cd24fc2f00ffe` |
| web digest | `sha256:38ed9740a6d320fae3b174187246ac5f99202b4da8f383b811502f7e9fb25f15` |
| 공개 범위 | 둘 다 익명 `tags/list` `200` = public. VM 에서 `docker login` 불필요 |

문서 변경 세 곳.

- `docs/31` **3-6 재배포 절차** — 이미 인증서·DNS 가 있는 서버에서 이미지만 바꾸는 경로
- `docs/31` **12 릴리스 대장** — 태그·커밋·digest·되돌릴 대상
- `docs/28` P1-3 — "태그 push 경로는 안 돌려 봤다" 를 실측으로 닫음

## 아키텍처 결정

### 첫 태그를 `v0.1.0` 으로 한다

문서 예시가 `v0.3.0` 을 쓰고 있어서 잠깐 헷갈렸는데, 그건 placeholder 다.
실제 태그는 **하나도 없었다.** `app.version` 이 `0.1.0` 이므로 첫 릴리스를
`v0.1.0` 으로 맞췄다. 없는 v0.2·v0.3 이 있었던 것처럼 보이게 만들 이유가 없다.

### 404 를 없애는 것과 설명을 켜는 것은 다른 단계다

`compose.gemini.yaml` 은 `./secrets/gemini_api_key.txt` 를 **파일로** 요구하고,
compose 의 `secrets:` 는 파일이 없으면 스택 자체를 못 올린다. 그래서 재배포
절차를 두 단계로 쪼갰다.

| 단계 | 결과 |
|---|---|
| override 없이 이미지 교체 | 404 → **200 + `available: false`** |
| 키 파일을 올리고 override 추가 | 200 + 설명 문장 |

키가 아직 서버에 없어도 첫 단계는 지금 할 수 있다. 그리고 첫 단계만으로도
"경로가 없다" 와 "계층이 꺼져 있다" 가 구분된다 — 진단 가능한 상태가 된다.

### 키를 셸 히스토리에 남기지 않는 방법을 절차에 박았다

```bash
read -rsp 'Gemini API key: ' KEY && printf '%s' "$KEY" > secrets/gemini_api_key.txt
unset KEY
```

`echo '키' > 파일` 로 쓰면 `~/.bash_history` 에 그대로 박힌다. Cloud Shell 은
홈 디렉터리가 세션 간에 유지되므로 그 기록도 남는다. `printf '%s'` 인 이유는
`echo` 가 붙이는 개행이 그대로 키의 일부가 되어 인증을 깨기 때문이다.

### 되돌릴 대상을 문서에 적어 둔다

`v0.1.0` 직전에 돌던 것은 버전 태그가 아니라
`sha-4457f0efa3ec0053ae2b5ab0135167fdec80bc7c` 다. 사고 중에 "직전 태그가
뭐였지" 를 찾는 상황을 만들지 않으려고 대장에 미리 적었다.

`4457f0e..30ba35b` 사이에 `migrations/` 변경이 없다는 것도 확인해 적었다.
이 되돌리기는 스키마를 건드리지 않는다.

## 검증

```
gh run view <run>          backend: success / web: success
ghcr tags/list (익명)      finshield-backend 200, finshield-web 200, 둘 다 v0.1.0 포함
manifest digest            backend c9c0864… / web 38ed974…
git diff 4457f0e..30ba35b -- migrations/    (비어 있음)
```

공개 URL 은 아직 옛 이미지다. 이 시점 실측:

```
POST /api/proxy/analyze              200
POST /api/proxy/analyze/explanation  404
```

**이 404 는 이제 "이미지가 없다" 가 아니라 "VM 이 아직 안 받았다" 다.** 원인이
바뀌었고, 남은 조치는 한 사람의 터미널 세션 하나다.

## 보안 영향

- 이미지는 public 레지스트리에 올라간다. **이미지 안에 비밀이 없다** — 키·인증서는
  전부 런타임 mount 로 받는다(`compose.gemini.yaml`, `compose.public-data.yaml`).
  이 전제는 새로 만든 것이 아니라 `docs/28` P1-3 에 이미 있던 것이고, 이번에
  태그 경로에서도 성립하는지 확인했다.
- 키 값은 이 저장소·문서·대화 어디에도 없다. 절차는 사람이 서버에서 직접 입력하는
  형태로만 적었다.
- 새 외부 호출·업로드·민감 필드 없음. 코드는 한 줄도 바뀌지 않았다.

## 남은 것

1. **VM 에서 `v0.1.0` pull → `up -d`** — `docs/31` 3-6. Cloud Shell 접속이 필요하다.
2. 키 파일을 서버에 올려 설명 계층 켜기 (1번과 같은 세션에서 가능).
3. 밖에서 `scripts/verify_public_deployment.py` 재실행.
4. 롤백 리허설 — 대장에 되돌릴 대상은 적었지만 **실제로 되돌려 본 적은 없다.**
5. Google Cloud 예산 알림·일일 상한.

## 커밋 SHA

`d7af623` — squash 병합 결과. 작업 브랜치의 `e9e9120` 은 squash 로 사라졌다.

**태그 `v0.1.0` 은 `30ba35b` 을 가리키며 이 커밋을 포함하지 않는다.** 문서만
바뀌었으므로 이미지 내용은 같다 — 태그를 옮겨 붙이지 않는다. 태그가 움직이면
대장의 digest 가 거짓말이 된다.

## PR

[#74](https://github.com/mosejong/finshield-ai/pull/74) — CI 8/8 통과 후 병합.
