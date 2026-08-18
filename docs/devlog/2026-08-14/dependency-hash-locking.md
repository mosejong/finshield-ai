# 파이썬 의존성 해시 잠금 (P0-5)

- 날짜: 2026-08-14
- 브랜치: `feature/frontend-accessibility-e2e`
- 범위: `requirements*.in`, `requirements*.txt`, `Dockerfile`, `.github/workflows/ci.yml`, 문서

## 배경

`docs/28` 6절이 P0-5를 맨 앞에 둔 이유는 순서 문제다. rate limit이나 백업 복원을
검증해도 의존성이 매 빌드 달라지면 그 결과가 다음 빌드에서 재현된다는 보장이 없다.
기준선을 먼저 고정해야 이후 측정이 의미를 가진다.

문제였던 상태는 반쪽 재현성이다. base 이미지는 digest로 고정(`python:3.12.10-slim-bookworm@sha256:fd95fa...`)했는데
패키지는 `fastapi>=0.116,<1.0` 같은 범위 지정이었다. 같은 커밋을 이틀 뒤에 빌드하면
다른 이미지가 나온다. 장애가 났을 때 "어제와 무엇이 달라졌는가"에 답할 수 없다.

작업하면서 하나 더 나왔다. `pytest`가 런타임 `requirements.txt`에 있었다. 즉
**프로덕션 이미지에 테스트 프레임워크가 실려 나가고 있었다.** 공격 표면과 이미지
크기 양쪽에서 불필요하다.

## 설계 판단 — 왜 `uv --universal`인가

개발은 Windows, 배포는 Linux다. 이 조합이 해시 고정에서 특히 까다롭다.

`pip-compile`이든 `uv pip compile`이든 기본값은 **해석한 플랫폼 기준**으로 lock을
만든다. Windows에서 만들면 `colorama`(win32 전용)가 들어가고 `uvloop`(non-win32)이
빠진다. 그 lock을 Linux 이미지에 `--require-hashes`로 설치하면 uvicorn이 요구하는
`uvloop`이 lock에 없어서 빌드가 실패한다. 반대로 Linux에서 만들면 Windows 개발자가
`colorama` 누락으로 설치하지 못한다. 플랫폼마다 lock을 따로 두는 선택지는 두 파일이
서로 다른 버전 집합으로 갈라질 수 있어서 재현성 목적 자체를 훼손한다.

`uv pip compile --universal`은 플랫폼 조건을 marker로 남긴 한 파일을 만든다.

```
colorama==0.4.6 ; sys_platform == 'win32'
uvloop==0.22.1 ; platform_python_implementation != 'PyPy' and sys_platform != 'cygwin' and sys_platform != 'win32'
```

설치할 때 각 플랫폼이 자기 몫만 가져간다. 버전 집합은 하나로 유지된다.

`uv`는 lock 생성 도구일 뿐 런타임 의존성이 아니므로 `requirements-dev.in`에만 넣었다.
도구 자체도 lock 안에 고정해야 재생성하는 사람마다 다른 resolver를 쓰는 일이 없다.

### `--no-deps`를 쓰지 않은 이유

pip-tools 관례는 `pip install --no-deps --require-hashes`다. 여기서는 `--no-deps`를
뺐다. `--no-deps`가 있으면 pip가 의존성을 확인하지 않으므로, lock에 전이 의존성이
빠져 있어도 설치가 성공하고 런타임에 ImportError로 터진다. `--require-hashes`만
쓰면 pip가 의존성을 해석하면서 lock에 없는 패키지를 발견할 때 설치를 실패시킨다.
빌드 시점에 터지는 쪽이 낫다.

## 구조

| 파일 | 성격 | 쓰는 곳 |
|---|---|---|
| `requirements.in` | 사람이 고침 (런타임) | lock 원본 |
| `requirements-dev.in` | 사람이 고침 (`-r requirements.in` + pytest, uv) | lock 원본 |
| `requirements.txt` | 생성물, 해시 고정 | 컨테이너 이미지, `container-runtime` job |
| `requirements-dev.txt` | 생성물, 해시 고정 | 로컬 개발, `test`·`deps-lock` job |

`.in`의 범위 상한(`<1.0` 등)은 그대로 뒀다. 실제 고정은 lock이 하지만, 상한은
`--upgrade`를 붙였을 때 major 버전이 예고 없이 넘어가는 것을 막는 역할로 남는다.

## CI

`deps-lock` job을 추가해 `.in`과 lock이 어긋난 채 병합되는 것을 막는다.

거짓 실패를 피하는 게 관건이었다. 재컴파일이 매번 최신 버전을 당겨오면 상류에 새
릴리스가 나올 때마다 CI가 빨개진다. `uv pip compile`은 `--upgrade` 없이는 기존
출력 파일의 pin을 유지하므로 이 문제가 없다. 가정하지 않고 실제로 확인했다 —
아무것도 바꾸지 않고 재생성한 결과가 byte 단위로 동일했다.

`container-runtime` job의 `pip install "cryptography>=45.0,<47.0"`도 런타임 lock
설치로 바꿨다. 그 스크립트는 cryptography만 쓰지만, 범위 지정으로 따로 설치하면
이 job만 lock 밖의 버전으로 도는 구멍이 남는다.

## 검증

| 확인 | 방법 | 결과 |
|---|---|---|
| Windows 설치 | 새 venv에 `pip install --require-hashes -r requirements-dev.txt` | 성공 |
| 잠긴 버전에서 회귀 | 그 venv로 `pytest -q` | 277 passed, 1 skipped |
| Linux 설치 | `docker build` (linux/amd64) | 성공 |
| 재컴파일 멱등성 | `--upgrade` 없이 재생성 후 byte diff | 동일 |
| 이미지 = lock | 이미지 `pip freeze` vs lock pin 대조 | 32개 전부 일치, lock 밖 0개 |
| 개발 의존성 분리 | 이미지 안에서 import 확인 | `pytest`·`uv` 없음 |
| 플랫폼 marker | 같은 확인 | `uvloop` 있음, `colorama` 없음 |
| CI YAML | `yaml.safe_load`로 job·step 파싱 | test 4 / deps-lock 6 / web 7 / container-runtime 12 |

lock이 해석한 버전은 기존 설치보다 올라갔다 (`fastapi 0.141.1`, `starlette 1.6.0`,
`cryptography 46.0.7`, `sqlalchemy 2.0.52`). 범위 지정이었으므로 원래도 언젠가
설치됐을 버전이지만, 회귀를 확인하지 않고 넘어갈 수 없어 잠긴 버전으로 전체
스위트를 다시 돌렸다. 통과했다.

## 남은 것

**고정은 그 자체로 위험을 만든다.** lock은 사람이 `--upgrade`를 붙일 때만 움직이므로,
취약점 패치가 나와도 저장소는 조용하다. 범위 지정일 때는 최소한 다시 빌드하면
올라갔지만 이제는 그것도 없다. 상승을 관측할 경로가 필요하다 — Dependabot 또는
주기적 `--upgrade` PR. `docs/28`에 P1-5로 기록했다. 자동 병합은 하지 않는다.

프론트엔드는 이미 `package-lock.json`이 있어 이번 범위 밖이다. 다만 npm lock은
무결성 해시를 담지만 CI가 `npm ci`로만 검증하고 lock 드리프트 job은 없다. 파이썬
쪽과 동일한 수준으로 맞출지는 P1-5와 함께 판단한다.
