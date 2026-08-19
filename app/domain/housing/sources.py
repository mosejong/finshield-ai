"""전세보증금 점검이 인용하는 공식 출처.

사기 분석과 파일을 나눈 이유는 두 가지다.

첫째, `supports` 가 행동 코드다. 한 파일에 두 도메인의 행동 코드를 섞으면
"이 출처가 저 행동을 뒷받침하는가" 를 사람이 눈으로 봐야 알 수 있다.

둘째, **재확인 주기가 다르게 흐른다.** 법령 조문과 스미싱 안내 페이지는
바뀌는 속도가 다르다. 나눠 두면 어느 쪽이 오래됐는지 따로 보인다.

여기 실린 여섯 건은 2026-08-19 에 실제로 열어 내용을 확인한 것만 남긴 것이다.
확인하지 못한 링크는 넣지 않는다 — 근거를 지어내는 것보다 근거가 적은 편이 낫다.
"""

import json
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter

from app.domain.official_sources import build_catalog, select_stale
from app.domain.official_sources import sources_for_actions as _sources_for_actions
from app.schemas.analysis import OfficialSource
from app.schemas.housing import DepositRiskAction


logger = logging.getLogger(__name__)

HOUSING_SOURCE_DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "housing" / "official_sources.json"
)

HOUSING_SOURCE_REVIEW_INTERVAL_DAYS = 365


@lru_cache(maxsize=1)
def load_housing_sources() -> dict[str, OfficialSource]:
    raw_data = json.loads(HOUSING_SOURCE_DATA_PATH.read_text(encoding="utf-8"))
    sources = TypeAdapter(list[OfficialSource]).validate_python(raw_data)
    return build_catalog(sources)


def stale_housing_sources(today: date | None = None) -> list[OfficialSource]:
    return select_stale(
        load_housing_sources(), HOUSING_SOURCE_REVIEW_INTERVAL_DAYS, today=today
    )


def verify_housing_sources() -> None:
    """기동 시 검증한다. 잘못된 근거 데이터는 요청이 아니라 기동에서 터져야 한다."""
    load_housing_sources()
    stale = stale_housing_sources()
    if stale:
        logger.warning(
            "housing official sources need re-verification",
            extra={"stale_source_ids": [source.source_id for source in stale]},
        )


def sources_for_actions(actions: list[DepositRiskAction]) -> list[OfficialSource]:
    return _sources_for_actions(load_housing_sources(), actions)
