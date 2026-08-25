# 2026-08-25 — 공개 URL 을 `v0.3.0` 으로 올리고, 그러다 서비스를 한 번 내렸다

## 왜 지금

사용자가 홈페이지에 직접 들어가 보겠다고 했다. 그전에 밖에서 경로를 몇 개
찍어 봤고, 거기서 나온 답이 이 회차 전체를 만들었다.

## 발견 — 이미지를 만든 것과 배포한 것은 다르다

태그는 셋 있었다.

```
2026-08-19  v0.1.0  cd1a834
2026-08-23  v0.2.0  5b0fb42
2026-08-25  v0.3.0  76441ab
```

공개 URL 은 그중 아무것도 돌리고 있지 않았다. 경로별 응답으로 좁혔다.

| 경로 | 응답 | 그 경로가 들어온 커밋 |
|---|---|---|
| `/learn/wealth` | `200` | `d2ce019` (#34) |
| `/check/deposit` | `404` | `bd69925` (#78) |
| `POST /api/proxy/analyze/explanation` | `404` | `c5fca16` (#67) |

`#34` 는 있고 `#67` 은 없는 이미지는 하나뿐이다 —
`sha-4457f0efa3ec0053ae2b5ab0135167fdec80bc7c`, 2026-08-18 빌드. VM 에서
`docker compose images` 로 확인하니 네 컨테이너 전부 그 digest 였고 7일
됐다고 찍혀 있었다. **공개 URL 은 v0.1.0 도 v0.2.0 도 받은 적이 없다.**

여기서 두 가지가 걸렸다.

### `verify_public_deployment` 는 이 상태를 못 잡는다

27개 검사가 **전부 통과한 상태에서** 화면 하나가 통째로 없었다. 그 스크립트가
재는 것은 TLS·보안 헤더·닫힌 포트이지 *어떤 빌드가 떠 있는가* 가 아니다.
통과했다는 사실이 배포됐다는 뜻이 아닌데, 그동안 그렇게 읽고 있었다.

그래서 재배포 절차에 **이번 릴리스에서 처음 들어온 경로를 하나 골라 찍는**
단계를 넣었다(`docs/31` 3-6). 새 경로 하나면 옛 이미지와 새 이미지가 갈린다.

### 릴리스 대장에 만든 날만 있고 올린 날이 없었다

대장을 보면 세 릴리스가 나란히 있어 다 올라간 것처럼 읽힌다. 그래서 표를
하나 더 만들었다 — **배포 대장.** `v0.1.0` 과 `v0.2.0` 은 그 표에 줄이
없다. 줄이 없는 것이 그 표가 하는 일이다.

## 사고 — 내가 문서에 적어 둔 `chmod 600` 이 서비스를 내렸다

이미지 교체 자체는 한 번에 끝났다. 시간을 쓴 것은 그다음이다.

Gemini 키 파일을 올리는 절차가 `docs/31` 3-6 에 있었고 이렇게 적혀 있었다.

```bash
read -rsp 'Gemini API key: ' KEY && printf '%s' "$KEY" > secrets/gemini_api_key.txt
chmod 600 secrets/gemini_api_key.txt
```

그대로 했더니 백엔드가 unhealthy 로 죽었고 `/api/proxy/analyze` 가 `502` 가
됐다. 재배포 전에는 `200` 이던 경로다. **설명 계층을 켜려다 서비스를 내렸다.**

원인은 세 가지가 겹친 자리에 있다.

1. compose 의 file secret 은 호스트 파일의 **uid/gid/mode 를 그대로**
   컨테이너 안으로 옮긴다.
2. 컨테이너는 `USER finshield` 로 돌고 그 uid/gid 는 **10001** 이다
   (`Dockerfile:8-9,26`). 호스트에서 만든 파일은 uid 1000 소유다.
3. `600` 은 소유자만 읽는다. uid 10001 에게는 읽기 거부다.

`chmod 644` 로 푸는 것은 답이 아니다 — VM 의 모든 계정이 키를 읽게 된다.
소유자를 컨테이너 uid 로 넘기고 잠갔다.

```bash
sudo chown 10001:10001 secrets/gemini_api_key.txt
sudo chmod 400 secrets/gemini_api_key.txt
ls -ln secrets/gemini_api_key.txt      # -r-------- 1 10001 10001
```

호스트 계정은 그 뒤로 키를 못 읽지만 읽을 일이 없다. 마운트는 root 로 도는
docker 데몬이 한다.

### 왜 설명이 아니라 백엔드 전체가 죽었나

`app/main.py:43-52` 의 lifespan 이 시작할 때 런타임을 **실제로 조립해 본다**
(`verify_llm_runtime_configuration` → `build_explanation_runtime`). 키를 못
읽으면 거기서 예외가 나고 `Application startup failed` 로 끝난다.

이건 의도된 설계다. `runtime.py:159` 에 "켜 놓고 안 되는 것과 끈 것은 다른
상태다" 라고 적혀 있다. 맞는 말이고, 그 값이 얼마인지가 오늘 처음 실측됐다 —
**있으면 좋고 없어도 되는 기능이 필수 경로를 끌고 내려간다.** 사기 문자를
판정하는 것은 결정론 엔진이고 LLM 없이도 된다. 그런데 LLM 설정 하나가
그 엔진까지 못 뜨게 했다.

고칠지 말지는 정하지 않았다. 값이 측정됐다는 것만 기록한다.

### 오진을 유도하는 에러 메시지

로그에 찍힌 것은 이것이다.

```
LlmRuntimeConfigurationError: FINSHIELD_LLM_PROVIDER is google_ai_studio
but the API key is missing
```

**키가 없다는 뜻이 아니다.** 파일은 53바이트로 멀쩡히 있었다.
`read_secret_setting` 의 `OSError`(권한 거부)가 `RuntimeSecretConfigurationError`
→ `GoogleAiStudioConfigurationError` → 이 문장까지 접혀 온 것이다. 세 겹을
지나면서 "못 읽는다" 가 "없다" 로 바뀐다.

`--tail` 을 짧게 주면 뿌리가 잘려서 이것만 보인다. 문서에 `--tail=40` 과
"이 문장은 키가 없다는 뜻이 아니다" 를 같이 적었다.

## 그다음 — 같은 `403` 이 두 번, 원인은 서로 달랐다

백엔드는 살아났는데 설명이 `status: failed` 로 돌아왔다. **1.7초** 만에
왔다는 게 단서였다 — 정상 호출은 6~8초다. 모델을 부르기도 전에 거절당한
것이다.

키를 드러내지 않고 컨테이너 안에서 확인했다. 키 길이와 상태 코드만 찍고,
에러 본문에는 `.replace(k, "<RED>")` 를 걸었다.

```
key_len 53
list_status 403
"Gemini API has not been used in project 1079633468584 before or it is disabled."
```

**키가 유효한 것과 그 키의 프로젝트에서 API 가 켜져 있는 것은 다른 조건이다.**
AI Studio 에서 키를 만들었다고 `generativelanguage.googleapis.com` 이
활성화되지는 않는다.

```bash
gcloud services enable generativelanguage.googleapis.com --project=finshield-5734
```

켜기 전에 예산 알림부터 걸었다(₩10,000/월). 이 프로젝트에는 결제 계정이 붙어
있고, 켜는 순간 상한 없는 유료 호출 경로가 하나 열린다. 예산은 알림이지
차단이 아니다 — 실제 제동은 `analyze_explanation` 요청 한도(60초당 10회,
IP 기준)가 건다.

그런데 켠 뒤에도 `403` 이었다. 문구가 달랐다.

```
Requests to this API generativelanguage.googleapis.com method
... ListModels are blocked.  PERMISSION_DENIED
```

**"켜져 있지 않다" 가 아니라 "차단됐다" 다.** 앞의 것은 프로젝트 상태이고
이것은 키 자신의 제한이다. 콘솔에서 열어 보니 이 키는 2026-08-19 에 Vertex
Express 경로로 만들어져 서비스 계정에 묶여 있었고, API 제한이
`Agent Platform API` 하나로 걸려 있었다.

목록에 `Gemini API` 를 **더할 수 없었다** — 체크박스가 비활성화되고 "현재
선택된 API 제한사항과 결합할 수 없습니다" 가 뜬다. 둘은 상호 배타다.
`Agent Platform API` 를 먼저 해제해야 `Gemini API` 가 선택된다. 더하는 것이
아니라 **바꾸는 것**이라는 게 그 화면에서 안 보인다.

바꾸자 재배포 없이 다음 호출부터 성공했다.

세 가지가 전부 `403` 이고 전부 다른 조치를 요구한다. 문서에 갈라 적었다.

| 본문 | 원인 | 조치 |
|---|---|---|
| `API key not valid` | 키 값 자체 | 키를 다시 만든다 |
| `has not been used in project …` | 프로젝트에서 API 가 꺼짐 | `gcloud services enable` |
| `Requests to this API … are blocked` | 키의 API 제한 목록 | 콘솔에서 제한을 바꾼다 |

## 마지막 오진은 내 쪽이었다

설명이 처음 성공했을 때 이런 문장이 왔다.

> 수신하신 문자의 글자가 깨져 있어서 … 위험 수준은 낮습니다

검찰청 사칭 + 안전계좌 이체 요구인데 `low` 다. 서비스 결함으로 보고 파기
전에, 내 curl 부터 의심했다. Git Bash 에서 `--data-binary` 로 한글을 인라인
붙여 보내고 있었다.

payload 를 Python 으로 UTF-8 로 써서 `@file` 로 다시 보냈다.

```
level   : high
signals : urgency, authority_impersonation, secrecy_isolation, money_transfer_request
types   : authority_impersonation, isolation_coercion
actions : 3건
```

**엔진은 정상이었다.** 깨진 입력을 받고 "글자가 깨졌다" 고 말한 것은 오히려
맞는 동작이다. 그리고 `actions: [None, None, None]` 로 보이던 것도 내 프로브가
없는 키(`priority`)를 찍은 탓이었다 — 실제 필드는
`id/title/detail/kind/contactPhone/contactLabel/evidenceIds` 다.

두 번 다 도구가 만든 가짜 증상이었다. 밖에서 한글 payload 를 보낼 때는
파일로 쓴다는 것을 환경 메모에 남겼다.

## 검증

| | 전 | 후 |
|---|---|---|
| `/check/deposit` | 404 | **200** |
| `POST /api/proxy/analyze` | 200 | 200 (사고 중 일시 502) |
| `POST /api/proxy/analyze/explanation` | 404 | **200 `status: ready`** |
| 설명 모델 / 지연 | — | `gemini-3.6-flash` / 7.1초 |
| `verify_public_deployment` | 27/27 | **27/27, exit 0** |
| 컨테이너 이미지 | `sha-4457f0e…` | `v0.3.0` |

DNS 도 확인했다 — `finshield-ai.duckdns.org` → `104.198.12.219`, VM 의
외부 IP 와 같다.

## 보안 영향

- 키 값은 저장소·문서·로그·대화 어디에도 없다. 입력은 `read -rsp`,
  기록은 `printf '%s'`(개행 없음), 진단 출력은 길이와 상태 코드만.
- `.env` 가 `644` 로 월드 리더블이었다. 그 안에 DB 비밀번호와 프로필 암호화
  키가 있다. `600` 으로 잠갔다.
- 키 파일은 이제 `400`, 소유자 uid 10001. 호스트 계정도 못 읽는다.
- 남은 강화 하나 — 키의 **애플리케이션 제한**이 아직 "없음" 이다. VM
  외부 IP 하나로 묶을 수 있다.
- 새 외부 호출·업로드·민감 필드 없음. 코드는 한 줄도 바뀌지 않았다.

## 남은 것

1. **키의 애플리케이션 제한을 IP `104.198.12.219` 로 건다.**
2. **선택 계층이 startup 을 막는 구조를 정한다** — 오늘 값이 측정됐다.
3. 롤백 리허설. 되돌릴 대상은 대장에 적혀 있지만 **실제로 되돌려 본 적이 없다.**
4. 설명 품질 분모 채우기 — 유료 경로가 열렸으니 이제 잴 수 있다
   (`docs/34` 9절, held-out 3-way 비교).

## 문서 변경

- `docs/31` **3-6** — `chown 10001:10001` + `chmod 400`, 확인 표에 5갈래
  (`404`/`status: off`/`status: failed`/`502`/설명 문장), 1~2초 대 6~8초
  판별, 컨테이너 안 진단, `403` 세 가지 구분
- `docs/31` **3-6** — 릴리스에서 처음 생긴 경로를 찍는 단계 신설
- `docs/31` **12** — 배포 대장 신설, 재배포 5단계 기록
