"""인증서 감시 워크플로가 **실제로 돌고, 실패할 수 있는가**를 검사한다.

이 워크플로의 가치는 전부 "조용히 안 도는 상태가 아니다" 에 있다. 검사 로직은
이미 `app/core/public_deployment.py` 에 있고 거기서 따로 테스트된다. 여기서
보는 것은 그 로직을 **주기적으로 부르는 배선**이다.

배선이 끊기는 방식이 세 가지고, 셋 다 조용하다.

1. `schedule` 트리거가 빠진다 -> 파일은 남아 있지만 영원히 안 돈다.
2. 주기가 경보 기준보다 길어진다 -> 갱신이 멈춘 21일 창을 통째로 건너뛴다.
3. `--insecure` 가 붙는다 -> 체인 검증을 건너뛰므로 `certificate_trusted` 가
   실패할 수 없게 된다. `docs/28` P0-3 에서 겪은 "실패할 수 없는 검사" 와
   같은 함정이다.

셋 중 무엇이 일어나도 초록불은 그대로다. 그래서 여기서 잡는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.public_deployment import CERTIFICATE_WARN_DAYS

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "certificate-watch.yml"

# 경보 창 안에 최소 몇 번은 검사가 돌아야 하는가. 한 번만 돌고 그 실행이
# 러너 장애로 건너뛰어지면 창을 통째로 놓친다.
MINIMUM_CHECKS_INSIDE_WARNING_WINDOW = 3


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    """`on:` 을 꺼낸다.

    YAML 1.1 은 맨 `on` 을 불리언 참으로 읽는다. PyYAML 도 그래서 이 키가
    문자열 `"on"` 이 아니라 `True` 로 들어온다.
    """
    return workflow.get("on") or workflow[True]


def _check_step(workflow: dict[str, Any]) -> dict[str, Any]:
    steps = workflow["jobs"]["certificate"]["steps"]
    for step in steps:
        if "verify_public_deployment" in step.get("run", ""):
            return step
    raise AssertionError("검사기를 부르는 단계가 없다")


def test_the_workflow_is_scheduled() -> None:
    """예약 트리거가 없으면 이 파일은 장식이다.

    `workflow_dispatch` 만 남겨두면 사람이 기억해서 눌러야 하는데, 기억할 수
    있으면 애초에 감시가 필요 없다.
    """
    schedule = _triggers(_workflow()).get("schedule")

    assert schedule, "schedule 트리거가 없다 - 이 워크플로는 저절로 돌지 않는다"
    assert all(entry.get("cron") for entry in schedule)


def test_it_runs_often_enough_to_catch_a_stalled_renewal() -> None:
    """주기가 경보 창보다 촘촘해야 한다.

    `CERTIFICATE_WARN_DAYS` 는 "갱신이 이미 멈춰 있다" 고 판정하는 남은 일수다.
    검사 간격이 그 창에 가까워지면, 창 안에서 한 번도 안 돌고 지나갈 수 있다.
    기준을 상수에 묶어 둔 이유는 둘 중 **어느 쪽을 고쳐도** 여기서 걸리게
    하기 위해서다.
    """
    crons = [entry["cron"] for entry in _triggers(_workflow())["schedule"]]

    for cron in crons:
        minute, hour, day_of_month, month, day_of_week = cron.split()

        # 하루 한 번 형태만 받는다. `*/3` 같은 표현을 일수로 환산하려면 cron
        # 해석기를 여기 들여와야 하고, 그러면 검사보다 검사기가 복잡해진다.
        # 주기를 바꾸려면 이 검사를 고치면서 근거를 다시 쓰게 된다.
        assert (day_of_month, month, day_of_week) == ("*", "*", "*"), (
            f"하루 한 번이 아니다: {cron}"
        )
        assert minute != "*" and hour != "*", f"매분·매시 실행이다: {cron}"

    interval_days = 1
    assert interval_days * MINIMUM_CHECKS_INSIDE_WARNING_WINDOW <= CERTIFICATE_WARN_DAYS


def test_the_check_can_actually_fail() -> None:
    """`--insecure` 는 체인 검증을 건너뛴다.

    예행연습용 플래그다. 이게 붙으면 `certificate_trusted` 가 항상 통과하므로,
    매일 도는 초록불이 아무것도 증명하지 않게 된다.
    """
    command = _check_step(_workflow())["run"]

    assert "--certificate-only" in command
    assert "--insecure" not in command


def test_the_domain_is_passed_as_an_environment_variable() -> None:
    """`${{ }}` 를 셸 명령 문자열에 직접 끼워 넣지 않는다.

    표현식은 셸이 보기 전에 치환된다. 값에 셸 메타문자가 들어 있으면 러너에서
    그대로 실행된다. 공개 저장소라 이 형태는 복사돼 나간다.
    """
    step = _check_step(_workflow())

    assert "${{" not in step["run"], "명령 문자열 안에서 표현식을 치환하고 있다"
    assert "DOMAIN" in step.get("env", {}), "도메인을 env 로 넘기지 않는다"


def test_the_workflow_does_not_ask_for_write_access() -> None:
    """검사만 하는 작업이라 기본 토큰 권한을 줄여 둔다."""
    permissions = _workflow()["permissions"]

    assert permissions == {"contents": "read"}
