"""`compose.deploy.yaml` 이 `compose.yaml` 을 따라가는지 본다.

배포 override 는 빌드하는 서비스마다 한 줄씩 손으로 적어야 한다. 그래서 새 서비스를
`compose.yaml` 에 추가하고 여기를 잊는 실패가 가능하다. 그 실패는 조용하다 -
`docker compose config` 는 통과하고, VM 에서 `up` 을 하는 순간 e2-micro 가 빌드를
시작하다 OOM 으로 죽는다. CI 의 `config --quiet` 검사도 이건 못 잡는다. 문법은
멀쩡하기 때문이다.

그래서 여기서는 문법이 아니라 **대응 관계** 를 본다.

`docker compose config` 를 부르지 않는 이유: 그 명령은 Docker 를 요구하고, 이 파일이
잡으려는 실패는 Docker 없이도 판정할 수 있다. pytest 는 Docker 없는 개발 머신에서도
돌아야 한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE = REPO_ROOT / "compose.yaml"
DEPLOY_COMPOSE = REPO_ROOT / "compose.deploy.yaml"

# 배포 때 우리가 만들어 올리는 이미지의 접두사. 여기서 벗어난 값이 들어오면
# 리뷰 없이 새 레지스트리를 쓰기 시작한 것이다.
IMAGE_PREFIX = "ghcr.io/${FINSHIELD_IMAGE_OWNER:-mosejong}/finshield-"

# override 가 태그를 필수로 받게 하는 문법. 기본값을 주는 순간(`:-latest`) 무엇이
# 돌고 있는지 알 수 없게 되고, 모르는 것은 되돌릴 수도 없다.
REQUIRED_TAG_MARKER = "${FINSHIELD_IMAGE_TAG:?"


class _ComposeLoader(yaml.SafeLoader):
    """`!reset` 을 아는 로더.

    Compose 확장 태그라 `safe_load` 는 모른다. 우리 목적에서는 "이 키를 지운다" 는
    표시이므로 sentinel 하나로 충분하다.
    """


class _Reset:
    def __repr__(self) -> str:  # pragma: no cover - 실패 메시지용
        return "!reset"


RESET = _Reset()

_ComposeLoader.add_constructor("!reset", lambda loader, node: RESET)


def _load(path: Path) -> dict[str, Any]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader)


def _services(path: Path) -> dict[str, dict[str, Any]]:
    services = _load(path).get("services") or {}
    return {name: (body or {}) for name, body in services.items()}


BASE_SERVICES = _services(BASE_COMPOSE)
DEPLOY_SERVICES = _services(DEPLOY_COMPOSE)
BUILT_SERVICES = sorted(name for name, body in BASE_SERVICES.items() if "build" in body)


def test_the_base_file_still_builds_something() -> None:
    """이 파일 전체가 공허해지는 경우를 막는다.

    `compose.yaml` 에서 `build:` 가 전부 사라지면 아래 parametrize 가 빈 목록이 되고
    테스트는 아무것도 검사하지 않으면서 초록으로 남는다. 이 저장소가 이미 두 번
    밟은 함정이다.
    """
    assert BUILT_SERVICES, "compose.yaml 에 build: 를 쓰는 서비스가 하나도 없다"


@pytest.mark.parametrize("service", BUILT_SERVICES)
def test_every_built_service_is_overridden(service: str) -> None:
    assert service in DEPLOY_SERVICES, (
        f"{service} 는 compose.yaml 에서 빌드하는데 compose.deploy.yaml 에 없다. "
        "이대로 배포하면 VM 이 빌드를 시작한다"
    )


@pytest.mark.parametrize("service", BUILT_SERVICES)
def test_every_override_drops_the_build_section(service: str) -> None:
    override = DEPLOY_SERVICES.get(service, {})
    assert override.get("build") is RESET, (
        f"{service} 의 build: 가 !reset 으로 지워지지 않았다. "
        "image: 와 build: 가 공존하면 어떤 명령은 pull 하고 어떤 명령은 빌드한다"
    )


@pytest.mark.parametrize("service", BUILT_SERVICES)
def test_every_override_pins_an_image(service: str) -> None:
    image = DEPLOY_SERVICES.get(service, {}).get("image")
    assert isinstance(image, str) and image.strip(), f"{service} 에 image: 가 없다"
    assert image.strip().startswith(IMAGE_PREFIX), (
        f"{service} 의 image 가 예상 밖의 곳을 가리킨다: {image!r}"
    )


@pytest.mark.parametrize("service", BUILT_SERVICES)
def test_every_override_requires_an_explicit_tag(service: str) -> None:
    image = DEPLOY_SERVICES.get(service, {}).get("image", "")
    assert REQUIRED_TAG_MARKER in image, (
        f"{service} 의 태그가 필수가 아니다: {image!r}. "
        "기본 태그를 주면 무엇이 돌고 있는지 모르는 배포가 된다"
    )


def test_the_override_adds_no_service_of_its_own() -> None:
    """override 는 기존 서비스를 덮어쓰기만 한다.

    여기서 새 서비스가 생기면 `compose.yaml` 만 읽은 사람은 그 존재를 모른다.
    """
    unknown = sorted(set(DEPLOY_SERVICES) - set(BASE_SERVICES))
    assert not unknown, f"compose.deploy.yaml 에만 있는 서비스: {unknown}"


def test_the_override_touches_only_image_and_build() -> None:
    """override 의 역할은 "빌드 대신 pull" 하나다.

    환경변수나 포트가 여기에 섞이면 배포 환경만 다르게 동작하고, 로컬에서 재현되지
    않는 차이가 생긴다.
    """
    allowed = {"image", "build"}
    for name, body in DEPLOY_SERVICES.items():
        extra = sorted(set(body) - allowed)
        assert not extra, f"{name} 에 image/build 외의 키가 있다: {extra}"


def test_the_backend_image_is_shared_by_all_python_services() -> None:
    """migration / backend / retention 은 같은 이미지를 쓴다.

    같은 코드베이스이므로 갈라질 이유가 없고, 갈라지면 마이그레이션이 적용한 스키마와
    backend 가 기대하는 스키마가 어긋난다.
    """
    python_services = [
        name for name in ("migration", "backend", "retention") if name in DEPLOY_SERVICES
    ]
    assert len(python_services) == 3, f"예상한 서비스가 없다: {python_services}"

    images = {DEPLOY_SERVICES[name]["image"] for name in python_services}
    assert len(images) == 1, f"파이썬 서비스들이 서로 다른 이미지를 쓴다: {sorted(images)}"


def test_services_without_a_build_are_left_alone() -> None:
    """db / backup 처럼 외부 이미지를 쓰는 서비스는 override 대상이 아니다.

    그쪽 이미지는 이미 digest 로 고정돼 있다. 여기서 다시 건드리면 고정이 풀린다.
    """
    pulled = sorted(name for name, body in BASE_SERVICES.items() if "build" not in body)
    assert pulled, "외부 이미지를 쓰는 서비스가 하나도 없다"

    overridden = sorted(set(pulled) & set(DEPLOY_SERVICES))
    assert not overridden, f"pull 서비스를 override 가 건드린다: {overridden}"
