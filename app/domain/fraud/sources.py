import json
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter

from app.domain.official_sources import (
    OfficialSourceDataError,
    build_catalog,
    select_stale,
)
from app.domain.official_sources import sources_for_actions as _sources_for_actions
from app.schemas.analysis import Action, OfficialSource


logger = logging.getLogger(__name__)

SOURCE_DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "fraud" / "official_sources.json"
)

# 공식 출처 링크는 기관 개편으로 바뀐다. 이 주기를 넘기면 재확인 대상으로 본다.
# 기간이 지났다는 이유로 분석을 중단하지는 않는다. 안전 안내를 끊는 쪽이 더 위험하다.
SOURCE_REVIEW_INTERVAL_DAYS = 365

__all__ = [
    "OfficialSourceDataError",
    "SOURCE_DATA_PATH",
    "SOURCE_REVIEW_INTERVAL_DAYS",
    "load_official_sources",
    "sources_for_actions",
    "stale_official_sources",
    "verify_official_sources",
]


@lru_cache(maxsize=1)
def load_official_sources() -> dict[str, OfficialSource]:
    raw_data = json.loads(SOURCE_DATA_PATH.read_text(encoding="utf-8"))
    sources = TypeAdapter(list[OfficialSource]).validate_python(raw_data)
    return build_catalog(sources)


def stale_official_sources(today: date | None = None) -> list[OfficialSource]:
    """재확인 주기가 지난 출처 목록. 기동 시 경고와 운영 점검에 쓴다."""
    return select_stale(
        load_official_sources(), SOURCE_REVIEW_INTERVAL_DAYS, today=today
    )


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
    return _sources_for_actions(load_official_sources(), actions)
