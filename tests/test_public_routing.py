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
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from app.api.routes.health import router as health_router
from app.api.routes.observability import router as observability_router

REPO_ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = REPO_ROOT / "deploy" / "Caddyfile"
DEPLOYMENT_DOC = REPO_ROOT / "docs" / "31-public-deployment.md"
REDEPLOY_SCRIPT = REPO_ROOT / "deploy" / "redeploy.sh"

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


class _ComposeLoader(yaml.SafeLoader):
    """`!reset` 을 아는 로더. `compose.deploy.yaml` 이 그 태그를 쓴다."""


_ComposeLoader.add_constructor("!reset", lambda loader, node: None)


def _compose_services() -> set[str]:
    names: set[str] = set()
    for path in REPO_ROOT.glob("compose*.yaml"):
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader)
        names.update((document or {}).get("services") or {})
    return names


# `$DC exec …` / `"${DC[@]}" run …` 한 줄에서 뒤쪽을 통째로 잡는다.
_INVOCATION = re.compile(r"""(?:\$DC|"\$\{DC\[@\]\}")\s+(exec|run)\s+([^\n]+)""")

# 값을 먹지 않는 플래그와 먹는 플래그. 모르는 플래그가 나오면 검사가 멈춘다 —
# 조용히 잘못 읽고 통과하는 것보다 낫다.
_BARE_FLAGS = frozenset({"-T", "-i", "-t", "--rm", "--no-deps", "--service-ports"})
_VALUED_FLAGS = frozenset({"--entrypoint", "-u", "--user", "-w", "--workdir", "-e"})


def _service_of(rest: str) -> str:
    """`exec`/`run` 뒤 플래그를 지나 서비스 이름 자리에 오는 토큰."""
    tokens = rest.split()
    index = 0
    while index < len(tokens) and tokens[index].startswith("-"):
        flag = tokens[index]
        if flag in _VALUED_FLAGS:
            index += 2
        elif flag in _BARE_FLAGS:
            index += 1
        else:
            raise AssertionError(f"모르는 플래그 {flag!r}. 검사를 먼저 고친다")
        continue
    assert index < len(tokens), f"서비스 이름이 없다: {rest!r}"
    return tokens[index]


class TestComposeCommandsNameRealServices:
    """문서와 스크립트가 부르는 compose 서비스가 실제로 있는가.

    2026-09-05 재배포에서 `$DC exec caddy caddy validate` 와 그 다음 줄의
    `reload` 가 `service "caddy" is not running` 만 찍고 **아무 일도 하지 않았다.**
    이 스택에서 Caddy 를 돌리는 서비스 이름은 `proxy` 다.

    없는 서비스를 부르는 것은 오타처럼 보이지만 결과는 다르다 — 두 명령이 조용히
    지나갔고, 사람은 절차를 다 밟았다고 믿었고, `/health` 는 계속 404 였다.
    **절차서의 명령이 실행되지 않는 것은 절차서가 틀린 것과 같다.**
    """

    @pytest.mark.parametrize(
        "path",
        [DEPLOYMENT_DOC, REDEPLOY_SCRIPT],
        ids=lambda path: path.name,
    )
    def test_every_named_service_exists(self, path: Path) -> None:
        services = _compose_services()
        text = path.read_text(encoding="utf-8")
        named = {_service_of(rest) for _, rest in _INVOCATION.findall(text)}
        assert named, f"{path.name} 에 compose 서비스를 부르는 줄이 없다"
        assert named <= services, f"{path.name}: 없는 서비스 {sorted(named - services)}"


class TestCaddyfileChangesAreForcedIn:
    """바뀐 `deploy/Caddyfile` 이 실제로 읽히는가.

    `caddy reload` 로는 안 된다. 단일 파일 bind mount 는 경로가 아니라 inode 에
    붙고, `git checkout` 은 새로 써서 이름을 바꿔 달아 inode 를 바꾼다. 컨테이너는
    이름이 사라진 옛 inode 를 계속 읽으므로 `validate` 도 `reload` 도 **옛 내용을
    상대로 정직하게 성공한다.** 2026-09-05 에 둘 다 통과했는데 `/health` 는 404
    였고, 호스트의 `grep -c public_health` 는 2, 컨테이너 안은 0 이었다.

    통과하는 확인 명령이 반영을 뜻하지 않는다는 것이 이 파일이 세 번째로 적는
    같은 이야기다.
    """

    @pytest.mark.parametrize(
        "path",
        [DEPLOYMENT_DOC, REDEPLOY_SCRIPT],
        ids=lambda path: path.name,
    )
    def test_the_proxy_is_recreated_not_reloaded(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        assert "--force-recreate proxy" in text
        assert "caddy reload" not in text, "reload 는 옛 inode 를 상대로 성공한다"

    @pytest.mark.parametrize(
        "path",
        [DEPLOYMENT_DOC, REDEPLOY_SCRIPT],
        ids=lambda path: path.name,
    )
    def test_validation_runs_in_a_fresh_container(self, path: Path) -> None:
        """떠 있는 컨테이너 안에서 문법을 보면 옛 파일을 본다.

        `run --rm` 으로 만든 컨테이너만 지금 디스크에 있는 파일을 mount 한다.
        """
        text = path.read_text(encoding="utf-8")
        validations = [
            rest
            for command, rest in _INVOCATION.findall(text)
            if "validate" in rest
        ]
        assert validations, f"{path.name} 에 Caddyfile 문법 확인이 없다"
        for command, rest in _INVOCATION.findall(text):
            if "validate" in rest:
                assert command == "run", "validate 를 exec 로 하면 옛 내용을 본다"


class TestRedeployScriptComposeList:
    """스크립트가 들고 있는 override 목록도 저장소를 따라가는가.

    `docs/31` 의 `DC=` 줄과 같은 이유다. 스크립트는 순서까지 적어 두는데(알파벳
    순으로 두면 `compose.yaml` 이 마지막이 되어 `!reset` 으로 지운 `build:` 가
    되살아나고 e2-micro 가 OOM 으로 죽는다), 그 목록이 저장소보다 짧아지는 것이
    원래의 사고였다.
    """

    @staticmethod
    def _script_compose_files() -> list[str]:
        text = REDEPLOY_SCRIPT.read_text(encoding="utf-8")
        block = re.search(r"^readonly COMPOSE_ORDER=\(\n(.+?)^\)$", text, re.M | re.S)
        assert block is not None, "redeploy.sh 에 COMPOSE_ORDER 가 없다"
        return block.group(1).split()

    def test_the_script_list_matches_the_repository(self) -> None:
        available = {path.name for path in REPO_ROOT.glob("compose*.yaml")}
        assert set(self._script_compose_files()) == available - STAGING_ONLY_COMPOSE

    def test_the_base_file_is_merged_first(self) -> None:
        """마지막에 오면 지운 `build:` 가 되살아난다."""
        assert self._script_compose_files()[0] == "compose.yaml"


class TestTheScriptSurvivesRewritingItself:
    """`git checkout` 은 이 스크립트 **자신**을 바꾼다.

    bash 는 스크립트를 통째로 읽어 두지 않고 실행하면서 조금씩 읽는다. 3절에서
    태그를 checkout 하는 순간 파일 내용이 그 자리에서 바뀌고, 남은 절반은 엉뚱한
    바이트 위치부터 읽힌다 — 운이 좋으면 문법 오류로 죽고, 나쁘면 줄 하나가
    반쯤 잘린 채 실행된다. `docs/31` 에 적힌 손 절차에는 없던 위험이고,
    자동화하면서 새로 생긴다.

    사본을 만들어 `exec` 하는 것 하나로 막는다. 아래 두 시험은 그 사본이
    **checkout 보다 먼저** 만들어지는지, 그리고 사본에서 `$0` 을 다시 쓰지
    않는지를 본다 (사본의 `$0` 은 /tmp 경로다).
    """

    @staticmethod
    def _lines() -> list[str]:
        """주석은 빈 줄로 바꾼다. 줄 번호는 유지해서 실패 메시지가 쓸모 있게."""
        return [
            "" if line.lstrip().startswith("#") else line
            for line in REDEPLOY_SCRIPT.read_text(encoding="utf-8").splitlines()
        ]

    @staticmethod
    def _first(lines: list[str], needle: str) -> int:
        for index, line in enumerate(lines):
            if needle in line:
                return index
        raise AssertionError(f"redeploy.sh 에 {needle!r} 가 없다")

    def test_the_copy_is_made_before_the_checkout(self) -> None:
        lines = self._lines()
        assert self._first(lines, "exec bash") < self._first(lines, "git checkout")

    def test_nothing_after_the_guard_reads_dollar_zero(self) -> None:
        """사본의 `$0` 은 저장소 밖을 가리킨다."""
        lines = self._lines()
        guard = self._first(lines, "FINSHIELD_REDEPLOY_COPY")
        end = self._first(lines[guard:], "rm -f -- ") + guard
        offenders = [
            f"{i + 1}: {line.strip()}"
            for i, line in enumerate(lines)
            if i > end and "$0" in line
        ]
        assert not offenders, "사본에서 $0 을 쓰면 /tmp 를 가리킨다: " + "; ".join(offenders)

    @pytest.mark.skipif(shutil.which("bash") is None, reason="bash 가 없다")
    def test_it_reports_its_repository_path_not_the_copy(self) -> None:
        """사본에서 돌아도 사람에게는 저장소 안의 이름을 보여야 한다."""
        finished = subprocess.run(
            [shutil.which("bash"), str(REDEPLOY_SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO_ROOT,
        )
        assert finished.returncode == 2, finished.stderr
        # 사본의 경로도, 부른 사람이 친 절대경로도 아닌 저장소 안의 이름 하나.
        assert finished.stderr.splitlines()[0] == "사용법: deploy/redeploy.sh <태그>"
