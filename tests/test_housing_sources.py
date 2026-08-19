"""전세보증금 점검이 인용하는 공식 출처의 무결성.

사기 출처와 같은 검사를 받는다. 규칙은 `app/domain/official_sources.py` 에
한 벌만 있고, 이 파일은 housing 카탈로그가 그 규칙 아래 있는지를 본다.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.housing.policy import ACTION_POLICIES
from app.domain.housing.sources import (
    HOUSING_SOURCE_DATA_PATH,
    HOUSING_SOURCE_REVIEW_INTERVAL_DAYS,
    load_housing_sources,
    stale_housing_sources,
    verify_housing_sources,
)
from app.domain.official_sources import OfficialSourceDataError
from app.main import app


@pytest.fixture
def source_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original = json.loads(Path(HOUSING_SOURCE_DATA_PATH).read_text(encoding="utf-8"))

    def write(records: list[dict]) -> None:
        path = tmp_path / "official_sources.json"
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(
            "app.domain.housing.sources.HOUSING_SOURCE_DATA_PATH", path
        )
        load_housing_sources.cache_clear()

    yield original, write
    load_housing_sources.cache_clear()


def test_future_retrieved_at_is_rejected(source_file) -> None:
    original, write = source_file
    records = [dict(record) for record in original]
    records[0]["retrieved_at"] = (date.today() + timedelta(days=1)).isoformat()
    write(records)

    with pytest.raises(OfficialSourceDataError, match="future retrieved_at"):
        load_housing_sources()


def test_duplicate_source_url_is_rejected(source_file) -> None:
    """같은 페이지를 두 id 로 등록하면 재확인할 때 한쪽 날짜만 갱신된다."""
    original, write = source_file
    duplicate = dict(original[0])
    duplicate["source_id"] = f"{duplicate['source_id']}_copy"
    write([dict(original[0]), duplicate])

    with pytest.raises(OfficialSourceDataError, match="source_url must be unique"):
        load_housing_sources()


def test_old_source_is_reported_stale_but_still_usable(source_file) -> None:
    original, write = source_file
    records = [dict(record) for record in original]
    records[0]["retrieved_at"] = (
        date.today() - timedelta(days=HOUSING_SOURCE_REVIEW_INTERVAL_DAYS + 1)
    ).isoformat()
    write(records)

    assert load_housing_sources()
    assert [source.source_id for source in stale_housing_sources()] == [
        records[0]["source_id"]
    ]
    verify_housing_sources()


def test_recent_sources_are_not_stale() -> None:
    assert stale_housing_sources() == []


def test_every_action_source_exists_and_supports_it() -> None:
    """행동과 출처가 어긋나면 '전입신고 하세요' 옆에 엉뚱한 링크가 붙는다."""
    catalog = load_housing_sources()

    for code, policy in ACTION_POLICIES.items():
        assert policy.source_ids, code
        for source_id in policy.source_ids:
            assert source_id in catalog, (code, source_id)
            assert code in catalog[source_id].supports, (code, source_id)


def test_no_orphan_sources() -> None:
    """어느 행동도 인용하지 않는 출처는 남겨 두지 않는다."""
    referenced = {
        source_id
        for policy in ACTION_POLICIES.values()
        for source_id in policy.source_ids
    }

    assert set(load_housing_sources()) == referenced


def test_supports_only_names_real_action_codes() -> None:
    for source in load_housing_sources().values():
        for code in source.supports:
            assert code in ACTION_POLICIES, (source.source_id, code)


def test_sources_are_official_institutions() -> None:
    """민간 블로그·중개 플랫폼은 근거가 될 수 없다."""
    allowed = {"국가법령정보센터", "법제처 찾기쉬운 생활법령정보", "주택도시보증공사"}

    for source in load_housing_sources().values():
        assert source.organization in allowed, source.source_id
        assert source.source_url.startswith("https://"), source.source_id


def test_startup_verifies_housing_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "app.main.verify_housing_sources", lambda: calls.append("verified")
    )

    with TestClient(app):
        pass

    assert calls == ["verified"]
