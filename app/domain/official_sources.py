"""출처 카탈로그의 공통 무결성 규칙.

`fraud` 와 `housing` 이 같은 형식의 출처 파일을 쓴다. 규칙을 두 벌로 두면
한쪽에만 검사가 추가되고 다른 쪽은 조용히 느슨해진다. 그 상태는 "출처가
검증됐다" 는 말을 도메인별로 다른 뜻으로 만든다.

여기 있는 것은 **데이터 검사**뿐이다. 어떤 행동이 어떤 출처를 갖느냐는
도메인 정책이므로 각 도메인 모듈에 남는다.
"""

from datetime import date, timedelta
from typing import Protocol

from app.schemas.analysis import OfficialSource


class OfficialSourceDataError(ValueError):
    """출처 파일 자체가 잘못된 경우.

    요청 시점이 아니라 기동 시점에 드러나야 한다. 잘못된 근거를 단 응답을
    내보내는 것보다 뜨지 않는 편이 낫다.
    """


class SupportedAction(Protocol):
    """행동 정책이 최소한 만족해야 하는 모양.

    도메인마다 `Action` 타입이 다르므로 구조로만 받는다.
    """

    code: str
    source_ids: list[str]


def parse_retrieved_at(source: OfficialSource) -> date:
    try:
        return date.fromisoformat(source.retrieved_at)
    except ValueError as exc:
        raise OfficialSourceDataError(
            f"official source {source.source_id} has a non ISO-8601 retrieved_at: "
            f"{source.retrieved_at}"
        ) from exc


def build_catalog(sources: list[OfficialSource]) -> dict[str, OfficialSource]:
    """검증하고 `source_id` 로 색인한다.

    URL 중복까지 막는 이유: 같은 페이지를 두 id 로 등록하면 재확인할 때
    한쪽 날짜만 갱신되고, 화면에는 같은 링크가 두 번 붙는다.
    """
    source_ids = [source.source_id for source in sources]
    source_urls = [source.source_url for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise OfficialSourceDataError("official source_id must be unique")
    if len(source_urls) != len(set(source_urls)):
        raise OfficialSourceDataError("official source_url must be unique")

    today = date.today()
    for source in sources:
        # 형식 오류와 미래 날짜만 데이터 오류로 막는다. 오래된 것은 경고로 다룬다.
        if parse_retrieved_at(source) > today:
            raise OfficialSourceDataError(
                f"official source {source.source_id} has a future retrieved_at: "
                f"{source.retrieved_at}"
            )

    return {source.source_id: source for source in sources}


def select_stale(
    catalog: dict[str, OfficialSource],
    interval_days: int,
    today: date | None = None,
) -> list[OfficialSource]:
    cutoff = (today or date.today()) - timedelta(days=interval_days)
    return [
        source
        for source in catalog.values()
        if parse_retrieved_at(source) < cutoff
    ]


def sources_for_actions(
    catalog: dict[str, OfficialSource], actions: list[SupportedAction]
) -> list[OfficialSource]:
    """행동에 붙은 출처만 골라 낸다.

    `supports` 를 확인하는 것이 핵심이다. 출처 id 가 존재하기만 하면 통과시키면
    "전입신고 하세요" 옆에 스미싱 안내 링크가 붙어도 아무도 못 잡는다.
    """
    related_ids: set[str] = set()

    for action in actions:
        for source_id in action.source_ids:
            source = catalog.get(source_id)
            if source is None:
                raise ValueError(f"unknown official source_id: {source_id}")
            if action.code not in source.supports:
                raise ValueError(
                    f"official source {source_id} does not support action {action.code}"
                )
            related_ids.add(source_id)

    return [
        source for source_id, source in catalog.items() if source_id in related_ids
    ]
