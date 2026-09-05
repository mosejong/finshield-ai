"""공개 도메인이 어느 요청을 어디로 보내는지 고정한다.

2026-09-05 외부 검수가 `https://<도메인>/health` 와 `/health/ready` 가 둘 다
Next.js 404 라고 보고했다. 배포가 망가진 것이 아니었다 — `deploy/Caddyfile` 이
**모든** 요청을 `web:3000` 으로 보내고 있었고, FastAPI 에 세 경로가 다 있어도
밖에서는 닿을 방법이 없었다. 설계대로 404 였다.

같은 종류의 실패가 하나 더 있었다. `docs/31` 의 재배포 명령줄에
`compose.public-data.yaml` 이 빠져 있어서 공개 서비스의 금융상품이 전부 503
이었다. 이쪽도 문법 오류가 아니라 **적어 둔 목록이 실제로 필요한 것보다 짧았던**
경우다.

두 실패의 공통점은 "코드는 맞는데 배포 설정이 그 코드에 닿지 못한다" 이고,
`docker compose config` 도 `caddy validate` 도 문법만 보기 때문에 둘 다 통과한다.
그래서 여기서는 문법이 아니라 **대응 관계** 를 본다 (`test_deploy_images.py` 와
같은 이유다). Docker 를 부르지 않으므로 Docker 없는 개발 머신에서도 돌아간다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api.routes.health import router as health_router
from app.api.routes.observability import router as observability_router

REPO_ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = REPO_ROOT / "deploy" / "Caddyfile"
DEPLOYMENT_DOC = REPO_ROOT / "docs" / "31-public-deployment.md"

# 밖에서 볼 수 있어야 하는 상태 확인 경로. 심사자·모니터링이 서비스가 살아
# 있는지 확인하는 유일한 공개 수단이고, 인증이 없어도 새는 것이 없다.
PUBLIC_HEALTH_PATHS = ("/health", "/health/live", "/health/ready")

# 공개하지 않는다. 어떤 요청이 얼마나 오는지, 설명 계층이 몇 번 실패했는지를
# 그대로 드러낸다. `app/api/routes/observability.py` 의 주석이 "배포에서
# 리버스 프록시가 막는 경로" 라고 적고 있고, 이 파일이 그 문장을 지킨다.
INTERNAL_ONLY_PATHS = ("/internal/metrics",)

# 운영 스택이 필요로 하는 compose 조합. 하나라도 빠지면 그 기능만 조용히 죽는다.
# `compose.acme-staging.yaml` 만 예외다 — 첫 발급 예행연습 전용이고, 운영에
# 얹으면 브라우저가 믿지 않는 인증서가 나간다.
STAGING_ONLY_COMPOSE = {"compose.acme-staging.yaml"}


def _strip_comments(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )


def _block_after(text: str, header: str) -> str:
    """`header` 로 시작하는 블록의 중괄호 안쪽을 돌려준다."""
    start = text.index(header) + len(header)
    depth = 1
    for offset, character in enumerate(text[start:], start=start):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start:offset]
    raise AssertionError(f"닫히지 않은 블록: {header!r}")


def _router_paths(router) -> set[str]:
    """라우터가 실제로 등록한 경로. `route.path` 에 prefix 가 이미 들어 있다."""
    return {route.path for route in router.routes}


@pytest.fixture(scope="module")
def caddyfile() -> str:
    return _strip_comments(CADDYFILE.read_text(encoding="utf-8"))


class TestHealthRouting:
    def test_public_health_matcher_lists_exactly_the_three_paths(self, caddyfile: str) -> None:
        matcher = re.search(r"^\s*@public_health\s+path\s+(.+)$", caddyfile, re.M)
        assert matcher is not None, "@public_health matcher 가 없다"
        assert tuple(matcher.group(1).split()) == PUBLIC_HEALTH_PATHS

    def test_health_requests_reach_the_backend(self, caddyfile: str) -> None:
        block = _block_after(caddyfile, "handle @public_health {")
        assert "reverse_proxy backend:8000" in block

    def test_health_requests_carry_a_host_the_backend_trusts(self, caddyfile: str) -> None:
        """공개 도메인 Host 를 그대로 넘기면 TrustedHostMiddleware 가 400 을 낸다.

        `compose.https.yaml` 의 `FINSHIELD_TRUSTED_HOSTS` 에는 공개 도메인이
        없다. 넣어서 푸는 대신 Caddy 가 Host 를 바꿔 보낸다 - 밖에서 온 Host
        값이 backend 에 닿지 않는 쪽이 좁다.
        """
        block = _block_after(caddyfile, "handle @public_health {")
        assert "header_up Host backend:8000" in block

    def test_everything_else_still_goes_to_the_web_app(self, caddyfile: str) -> None:
        block = _block_after(caddyfile, "handle {")
        assert "reverse_proxy web:3000" in block

    def test_the_backend_is_reachable_through_exactly_one_route(self, caddyfile: str) -> None:
        """backend 로 가는 문이 하나뿐이어야 위 세 검사가 의미를 갖는다."""
        assert caddyfile.count("backend:8000") == 2  # reverse_proxy 와 header_up Host

    def test_internal_metrics_is_not_published(self, caddyfile: str) -> None:
        for path in INTERNAL_ONLY_PATHS:
            assert path not in caddyfile


class TestRoutingMatchesTheApplication:
    """Caddy 가 아는 경로와 FastAPI 가 실제로 가진 경로가 같아야 한다.

    이 검사가 없으면 경로 이름을 바꿨을 때 두 파일이 조용히 갈라지고, 결과는
    다시 404 다. 이번에 사람이 잡은 것이 정확히 그 404 였다.
    """

    def test_published_paths_are_exactly_the_health_router(self) -> None:
        assert _router_paths(health_router) == set(PUBLIC_HEALTH_PATHS)

    def test_internal_paths_exist_but_are_not_published(self) -> None:
        assert _router_paths(observability_router) == set(INTERNAL_ONLY_PATHS)


class TestDeploymentComposeList:
    """`docs/31` 의 재배포 명령줄이 실제로 필요한 override 를 전부 담는가.

    금융상품이 공개 서비스에서 503 이던 이유가 이것이다. `compose.public-data.yaml`
    만 `PUBLIC_DATA_SERVICE_KEY_FILE` 과 secret 을 backend 에 붙이는데, 재배포
    명령줄에 그 파일이 한 번도 없었다. 문서가 짧았고, 짧은 것은 검사되지 않았다.
    """

    @staticmethod
    def _redeploy_compose_files() -> set[str]:
        text = DEPLOYMENT_DOC.read_text(encoding="utf-8")
        line = re.search(r'^DC="docker compose (.+)"$', text, re.M)
        assert line is not None, "docs/31 에 DC= 재배포 명령줄이 없다"
        return set(re.findall(r"-f (compose[\w.-]*\.yaml)", line.group(1)))

    def test_redeploy_line_includes_every_production_override(self) -> None:
        available = {path.name for path in REPO_ROOT.glob("compose*.yaml")}
        required = available - STAGING_ONLY_COMPOSE
        assert self._redeploy_compose_files() == required

    def test_redeploy_line_does_not_include_the_staging_override(self) -> None:
        assert not (self._redeploy_compose_files() & STAGING_ONLY_COMPOSE)

    def test_the_public_data_override_is_what_configures_the_product_catalog(self) -> None:
        """이 검사가 무엇을 지키는지 분명히 해 둔다.

        `PUBLIC_DATA_SERVICE_KEY` 를 주는 파일이 `compose.public-data.yaml`
        하나뿐이라는 사실이 위 검사의 전제다. 나중에 그 값이 `compose.yaml`
        으로 옮겨가면 위 검사는 여전히 통과하지만 이유가 달라진다.
        """
        sources = [
            path.name
            for path in REPO_ROOT.glob("compose*.yaml")
            if "PUBLIC_DATA_SERVICE_KEY" in path.read_text(encoding="utf-8")
        ]
        assert sources == ["compose.public-data.yaml"]
