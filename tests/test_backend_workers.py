"""backend 컨테이너를 **어떤 프로세스 모양으로** 띄우는지 검사한다.

2026-08-18 GCP e2-micro 배포에서 백엔드가 영구적으로 굳었다. 증상은 컨테이너가
`Up (unhealthy)` 로 남고 로그에 `Waiting for child process` 와 `Child process
died` 만 무한히 찍히는 것이었다 - **트레이스백은 한 줄도 없었다.**

원인은 uvicorn 의 멀티워커 감시자다. 워커가 2개 이상이면 `Multiprocess` 가
0.5초마다 자식에게 ping 을 보내고, `timeout_worker_healthcheck`(기본 5초) 안에
답이 없으면 SIGKILL 한 뒤 새 워커를 띄운다. 그런데 워커는 fork 가 아니라
spawn 이라 매번 인터프리터가 처음부터 부팅되고, ping 에 답하는 스레드는 부팅이
끝난 뒤에야 생긴다. 기동 경합으로 그 창이 5초를 넘으면 부모가 자식을 죽이고 새
인터프리터를 두 개 더 띄운다 - 경합이 원인인데 대응이 경합을 키운다. SIGKILL
이라 파이썬은 아무것도 남기지 못한다.

그래서 여기서 보는 것은 두 가지다.

1. **워커 수가 이미지에 박혀 있지 않은가.** 호스트 크기에 따라 달라져야 하는
   값이다. uvicorn 은 `--workers` 를 넘기지 않았을 때만 `WEB_CONCURRENCY` 를
   읽으므로, 플래그가 CMD 로 돌아오는 순간 compose 의 설정이 조용히 무시된다.
2. **느린 기동이 영구적인 고장으로 번지지 않는가.** 기본 5초는 그렇게 번졌다.

`docker` 를 부르지 않는다. 이 두 가지는 파일만 읽어도 판정할 수 있고, pytest 는
Docker 없는 개발 머신에서도 돌아야 한다. 대신 플래그가 **고정된 uvicorn 버전에
실제로 존재하는지** 는 설치된 패키지에 직접 물어본다 - 이미지가 뜨지 않는 형태의
고장이라, 의존성을 올릴 때 여기서 걸려야 한다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from uvicorn import main as uvicorn_cli

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"
BASE_COMPOSE = REPO_ROOT / "compose.yaml"

# uvicorn 이 응답 없는 워커를 SIGKILL 하기까지 기다리는 기본 초. 이 값이 위
# 고장을 만들었으므로, 기본값 그대로 돌아가면 안 된다.
UVICORN_DEFAULT_HEALTHCHECK_TIMEOUT = 5

# 호스트가 워커 수를 정하는 손잡이. uvicorn 이 읽는 이름은 `WEB_CONCURRENCY` 로
# 고정이지만, compose 에 `web` 서비스가 따로 있어서 호스트 `.env` 에서는 이
# 이름을 쓴다.
WORKER_COUNT_VARIABLE = "FINSHIELD_UVICORN_WORKERS"


def _dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _command() -> list[str]:
    """Dockerfile 의 CMD 를 exec 형식 그대로 읽는다."""
    for line in _dockerfile().splitlines():
        if line.startswith("CMD "):
            return json.loads(line[len("CMD ") :])
    raise AssertionError("Dockerfile 에 exec 형식 CMD 가 없다")


def _flag_value(command: list[str], flag: str) -> str | None:
    if flag not in command:
        return None
    index = command.index(flag)
    assert index + 1 < len(command), f"{flag} 에 값이 없다"
    return command[index + 1]


def _image_worker_default() -> str:
    match = re.search(r"^ENV WEB_CONCURRENCY=(\S+)$", _dockerfile(), re.MULTILINE)
    assert match, "Dockerfile 이 WEB_CONCURRENCY 기본값을 선언하지 않는다"
    return match.group(1)


def _backend_environment() -> dict[str, Any]:
    compose = yaml.safe_load(BASE_COMPOSE.read_text(encoding="utf-8"))
    return compose["services"]["backend"]["environment"]


def _uvicorn_options() -> set[str]:
    """고정된 uvicorn 이 실제로 받는 CLI 옵션 이름."""
    return {
        option
        for parameter in uvicorn_cli.params
        for option in list(parameter.opts) + list(parameter.secondary_opts)
    }


def test_the_command_still_starts_this_application() -> None:
    """빈 파싱으로 아래 검사들이 전부 참이 되는 것을 막는다.

    CMD 를 못 찾거나 다른 것을 실행하고 있으면 "`--workers` 가 없다" 는 아무
    의미가 없다.
    """
    command = _command()

    assert command[0] == "uvicorn"
    assert "app.main:app" in command


def test_the_image_does_not_hardcode_the_worker_count() -> None:
    """워커 수는 이미지가 아니라 호스트가 정한다.

    uvicorn 은 `--workers` 를 넘기지 **않았을 때만** `WEB_CONCURRENCY` 를 읽는다
    (`uvicorn/config.py`). 그래서 플래그가 CMD 로 돌아오면 compose 와 `.env` 의
    설정이 에러 없이 무시된다 - 1GB 호스트가 다시 2개로 돌게 되고, 그 사실은
    아무 데도 표시되지 않는다.
    """
    assert "--workers" not in _command()


def test_the_image_declares_its_own_worker_default() -> None:
    """compose 없이 `docker run` 만 해도 워커 수가 정해져 있어야 한다.

    선언을 지우면 uvicorn 기본값 1 로 조용히 떨어진다. 값이 바뀌는 것 자체보다,
    이미지를 직접 돌리는 사람과 compose 로 돌리는 사람이 서로 다른 것을 얻는
    상태가 문제다.
    """
    assert _image_worker_default().isdigit()
    assert int(_image_worker_default()) >= 1


def test_the_worker_healthcheck_timeout_is_raised_above_the_default() -> None:
    """느린 기동을 "굳었다" 로 오판하지 않게 만든 부분.

    이것이 실제 결함 수정이다. 워커 수는 호스트 사양 문제지만, 기본 5초는
    **어떤 호스트에서든** 기동이 느려지는 순간 자기강화 루프로 들어간다.
    """
    timeout = _flag_value(_command(), "--timeout-worker-healthcheck")

    assert timeout is not None, "워커 healthcheck 타임아웃을 지정하지 않았다"
    assert int(timeout) > UVICORN_DEFAULT_HEALTHCHECK_TIMEOUT


def test_the_worker_healthcheck_timeout_stays_under_the_container_healthcheck() -> None:
    """uvicorn 이 컨테이너보다 먼저 판정해야 한다.

    타임아웃을 컨테이너 healthcheck 예산보다 길게 두면, 진짜로 굳은 워커를
    uvicorn 이 되살리기 전에 Docker 가 컨테이너를 통째로 unhealthy 로 만든다.
    그러면 워커 하나짜리 고장이 서비스 전체 재기동이 된다.
    """
    compose = yaml.safe_load(BASE_COMPOSE.read_text(encoding="utf-8"))
    healthcheck = compose["services"]["backend"]["healthcheck"]
    budget = int(healthcheck["interval"].rstrip("s")) * int(healthcheck["retries"])

    timeout = _flag_value(_command(), "--timeout-worker-healthcheck")
    assert timeout is not None
    assert int(timeout) < budget


def test_every_flag_in_the_command_exists_in_the_pinned_uvicorn() -> None:
    """의존성을 올렸을 때 CMD 가 먼저 깨지도록 한다.

    uvicorn 이 모르는 플래그를 받으면 exit code 2 로 즉시 죽는다. 이미지가 아예
    뜨지 않는 형태의 고장이라, 배포가 아니라 여기서 걸려야 한다.
    """
    options = _uvicorn_options()
    unknown = [
        token
        for token in _command()
        if token.startswith("--") and token not in options
    ]

    assert not unknown, f"고정된 uvicorn 이 모르는 플래그: {unknown}"


def test_compose_lets_the_host_choose_the_worker_count() -> None:
    """`.env` 한 줄로 워커 수를 바꿀 수 있어야 한다.

    e2-micro 에서 처음 이걸 고칠 때는 추적되지 않는 override 파일을 VM 에
    직접 만들어야 했다. 그 상태로 두면 저장소를 다시 받는 순간 되돌아간다.
    """
    value = _backend_environment().get("WEB_CONCURRENCY")

    assert value is not None, "backend 가 WEB_CONCURRENCY 를 받지 않는다"
    assert value.startswith("${" + WORKER_COUNT_VARIABLE + ":-"), (
        f"기본값 있는 {WORKER_COUNT_VARIABLE} 보간이어야 한다: {value}"
    )


def test_the_image_default_and_the_compose_default_agree() -> None:
    """두 기본값이 갈라지면 어느 쪽으로 띄웠는지에 따라 동작이 달라진다.

    한쪽만 고치는 것이 자연스러운 실수라서 검사로 묶어 둔다.
    """
    value = _backend_environment()["WEB_CONCURRENCY"]
    compose_default = value.removeprefix("${" + WORKER_COUNT_VARIABLE + ":-").removesuffix("}")

    assert compose_default == _image_worker_default()
