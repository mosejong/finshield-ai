import json
import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter

from app.schemas.analysis import Action, OfficialSource


logger = logging.getLogger(__name__)

SOURCE_DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "fraud" / "official_sources.json"
)

# 공식 출처 링크는 기관 개편으로 바뀐다. 이 주기를 넘기면 재확인 대상으로 본다.
# 기간이 지났다는 이유로 분석을 중단하지는 않는다. 안전 안내를 끊는 쪽이 더 위험하다.
SOURCE_REVIEW_INTERVAL_DAYS = 365


class OfficialSourceDataError(ValueError):
    """official_sources.json 자체가 잘못된 경우. 요청 시점이 아니라 기동 시점에 드러나야 한다."""


def _parse_retrieved_at(source: OfficialSource) -> date:
    try:
        return date.fromisoformat(source.retrieved_at)
    except ValueError as exc:
        raise OfficialSourceDataError(
            f"official source {source.source_id} has a non ISO-8601 retrieved_at: "
            f"{source.retrieved_at}"
        ) from exc


@lru_cache(maxsize=1)
def load_official_sources() -> dict[str, OfficialSource]:
    raw_data = json.loads(SOURCE_DATA_PATH.read_text(encoding="utf-8"))
    sources = TypeAdapter(list[OfficialSource]).validate_python(raw_data)

    source_ids = [source.source_id for source in sources]
    source_urls = [source.source_url for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise OfficialSourceDataError("official source_id must be unique")
    if len(source_urls) != len(set(source_urls)):
        raise OfficialSourceDataError("official source_url must be unique")

    today = date.today()
    for source in sources:
        # 형식 오류와 미래 날짜만 데이터 오류로 막는다. 오래된 것은 경고로 다룬다.
        if _parse_retrieved_at(source) > today:
            raise OfficialSourceDataError(
                f"official source {source.source_id} has a future retrieved_at: "
                f"{source.retrieved_at}"
            )

    return {source.source_id: source for source in sources}


def stale_official_sources(today: date | None = None) -> list[OfficialSource]:
    """재확인 주기가 지난 출처 목록. 기동 시 경고와 운영 점검에 쓴다."""
    cutoff = (today or date.today()) - timedelta(days=SOURCE_REVIEW_INTERVAL_DAYS)
    return [
        source
        for source in load_official_sources().values()
        if _parse_retrieved_at(source) < cutoff
    ]


def verify_official_sources() -> None:
    """기동 시 출처 데이터를 미리 검증한다.

    이 호출이 없으면 잘못된 데이터가 startup 과 health check 를 통과하고
    분석 요청에서만 500 으로 드러난다.
    """
    load_official_sources()
    stale = stale_official_sources()
    if stale:
        logger.warning(
            "official sources need re-verification",
            extra={"stale_source_ids": [source.source_id for source in stale]},
        )


def sources_for_actions(actions: list[Action]) -> list[OfficialSource]:
    source_catalog = load_official_sources()
    related_ids: set[str] = set()

    for action in actions:
        for source_id in action.source_ids:
            source = source_catalog.get(source_id)
            if source is None:
                raise ValueError(f"unknown official source_id: {source_id}")
            if action.code not in source.supports:
                raise ValueError(
                    f"official source {source_id} does not support action {action.code}"
                )
            related_ids.add(source_id)

    return [
        source for source_id, source in source_catalog.items() if source_id in related_ids
    ]
