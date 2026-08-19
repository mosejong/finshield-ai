"""요청 한도 정책과 판정.

**식별자는 client IP 하나만 쓴다.** 세션 토큰을 함께 쓰면 NAT 뒤 사용자를
구분할 수 있어 좋아 보이지만, 세션은 공격자가 스스로 만들 수 있다. 세션마다
따로 세면 세션을 n 개 발급받아 한도를 n 배로 늘린다. IP 는 공격자가 임의로
바꿀 수 없는 유일한 축이라 여기서 상한이 실제 상한이 된다.

대가는 CGNAT·회사망처럼 여러 사용자가 한 IP 를 쓸 때 함께 묶인다는 것이다.
그래서 한도를 넉넉하게 잡는다. 이 제한의 목적은 정교한 공정 분배가 아니라
"한 명이 서비스를 갈아버리는 것"을 막는 것이다.

저장소가 죽으면 **통과시킨다.** 사기 분석은 안전 기능이다. DB 장애 때문에
위험한 문자를 확인하지 못하게 만드는 쪽이, 그동안 한도가 열리는 것보다
나쁘다. `app/domain/fraud/sources.py` 에서와 같은 판단이다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
import logging
from hashlib import sha256

from app.repositories.rate_limits import (
    RateLimitCleanupSummary,
    RateLimitRepository,
    RateLimitStorageError,
)

logger = logging.getLogger("finshield.rate_limit")

UNIDENTIFIED_CLIENT = "unidentified"


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    limit: int
    window_seconds: int
    path_prefix: str
    methods: frozenset[str] | None = None
    exact_path: bool = False

    def matches(self, method: str, path: str) -> bool:
        if self.methods is not None and method.upper() not in self.methods:
            return False
        if self.exact_path:
            return path == self.path_prefix
        return path.startswith(self.path_prefix)


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    policy: RateLimitPolicy | None = None
    remaining: int = 0
    retry_after_seconds: int = 0
    reset_at: datetime | None = None


# 위에서부터 먼저 맞는 정책 하나만 적용한다. 여러 정책을 겹쳐 세면
# 요청 한 건에 저장소 쓰기가 여러 번 일어나고, 정작 무엇에 걸렸는지도
# 흐려진다.
#
# `/health`·`/readyz` 는 어떤 정책에도 걸리지 않는다. 컨테이너 healthcheck 가
# 주기적으로 때리는 경로라, 여기에 한도를 걸면 스스로를 unhealthy 로 만든다.
DEFAULT_POLICIES: tuple[RateLimitPolicy, ...] = (
    # 세션 발급은 users/auth_sessions 행을 새로 만든다. 반복 호출은
    # 곧 저장소를 무제한으로 늘리는 행위다. 정상 사용자는 브라우저당
    # 한 번이면 충분하므로 가장 좁게 잡는다.
    RateLimitPolicy(
        name="auth_session",
        limit=20,
        window_seconds=3_600,
        path_prefix="/api/v1/auth/session",
        methods=frozenset({"POST"}),
        exact_path=True,
    ),
    # 설명은 분석보다 비싸다. 유료 외부 호출이 나가고, 대체 모델까지 가면 한 요청에
    # 두 번 나간다. 그리고 `analyze` 정책은 `exact_path` 라서 이 경로를 덮지 않는다 -
    # 이 항목이 없으면 아래 `write` 정책(60/분)으로 떨어져, 더 비싼 경로가 더 헐거운
    # 한도를 갖게 된다. 반드시 `analyze` 보다 위에 있어야 한다.
    #
    # IP 단위 한도라 분산된 남용은 못 막는다. 그건 여기가 아니라 프로바이더 쪽
    # 예산 한도로 막을 문제다(`docs/34`).
    RateLimitPolicy(
        name="analyze_explanation",
        limit=10,
        window_seconds=60,
        path_prefix="/api/v1/analyze/explanation",
        methods=frozenset({"POST"}),
        exact_path=True,
    ),
    # 분석은 이 서비스에서 가장 비싼 경로이고 인증이 없다.
    RateLimitPolicy(
        name="analyze",
        limit=30,
        window_seconds=60,
        path_prefix="/api/v1/analyze",
        methods=frozenset({"POST"}),
        exact_path=True,
    ),
    RateLimitPolicy(
        name="write",
        limit=60,
        window_seconds=60,
        path_prefix="/api/v1/",
        methods=frozenset({"POST", "PUT", "PATCH", "DELETE"}),
    ),
    RateLimitPolicy(
        name="read",
        limit=240,
        window_seconds=60,
        path_prefix="/api/v1/",
    ),
)


class RateLimitService:
    def __init__(
        self,
        repository: RateLimitRepository,
        *,
        secret: str,
        policies: Sequence[RateLimitPolicy] = DEFAULT_POLICIES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not secret:
            raise ValueError("rate limit secret must not be empty")
        self._repository = repository
        self._secret = secret.encode("utf-8")
        self._policies = tuple(policies)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def policies(self) -> tuple[RateLimitPolicy, ...]:
        return self._policies

    def verify_storage(self) -> None:
        self._repository.verify()

    def select_policy(self, method: str, path: str) -> RateLimitPolicy | None:
        for policy in self._policies:
            if policy.matches(method, path):
                return policy
        return None

    def check(
        self, *, method: str, path: str, client_ip: str | None
    ) -> RateLimitDecision:
        policy = self.select_policy(method, path)
        if policy is None:
            return RateLimitDecision(allowed=True)

        now = self._utc_now()
        window = timedelta(seconds=policy.window_seconds)
        window_start = _floor_to_window(now, policy.window_seconds)
        window_end = window_start + window

        try:
            hit_count = self._repository.increment(
                bucket_key=self._bucket_key(policy, client_ip),
                window_start=window_start,
                window_end=window_end,
            )
        except RateLimitStorageError:
            # 메시지에 식별자를 넣지 않는다. 로그가 접속 기록이 되면 안 된다.
            logger.warning(
                "rate limit storage unavailable; allowing request",
                extra={"policy": policy.name},
            )
            return RateLimitDecision(allowed=True, policy=policy)

        remaining = max(policy.limit - hit_count, 0)
        retry_after = max(int((window_end - now).total_seconds()), 1)
        return RateLimitDecision(
            allowed=hit_count <= policy.limit,
            policy=policy,
            remaining=remaining,
            retry_after_seconds=retry_after,
            reset_at=window_end,
        )

    def cleanup_expired(self, *, execute: bool = False) -> RateLimitCleanupSummary:
        return self._repository.cleanup_expired(
            now=self._utc_now(),
            execute=execute,
        )

    def _bucket_key(self, policy: RateLimitPolicy, client_ip: str | None) -> str:
        """식별자를 그대로 저장하지 않는다.

        IPv4 는 값이 2^32 개뿐이라 단순 해시는 표를 만들어 되돌릴 수 있다.
        서버 비밀을 섞은 HMAC 이어야 저장된 행이 접속 기록이 되지 않는다.
        """
        identity = client_ip or UNIDENTIFIED_CLIENT
        message = f"{policy.name}|{identity}".encode("utf-8")
        return hmac.new(self._secret, message, sha256).hexdigest()

    def _utc_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)


def _floor_to_window(value: datetime, window_seconds: int) -> datetime:
    epoch_seconds = int(value.timestamp())
    return datetime.fromtimestamp(
        epoch_seconds - (epoch_seconds % window_seconds),
        tz=timezone.utc,
    )
