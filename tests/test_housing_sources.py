"""전세보증금 점검이 인용하는 공식 출처의 무결성.

사기 출처와 같은 검사를 받는다. 규칙은 `app/domain/official_sources.py` 에
한 벌만 있고, 이 파일은 housing 카탈로그가 그 규칙 아래 있는지를 본다.
"""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.clock import today_kst
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
    records[0]["retrieved_at"] = (today_kst() + timedelta(days=1)).isoformat()
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
        today_kst() - timedelta(days=HOUSING_SOURCE_REVIEW_INTERVAL_DAYS + 1)
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


def test_statute_links_use_a_form_that_renders_the_article() -> None:
    """조문 직링크는 실제로 본문이 열리는 형태만 쓴다.

    `lsInfoP.do` 는 조문 본문을 열지 못했고, 일련번호를 추측해서 만든 링크는
    한 번 엉뚱한 법령(국토기본법 시행령)을 가리켰다. 링크가 열리는 것과 그
    링크가 우리가 인용한 조문인 것은 다른 문제라, 형태만이라도 고정해 둔다.
    """
    working_forms = ("lsLinkProc.do", "lsLinkCommonInfo.do")

    for source in load_housing_sources().values():
        if source.organization != "국가법령정보센터":
            continue
        assert any(form in source.source_url for form in working_forms), (
            source.source_id
        )


def test_priority_repayment_cites_the_statute_not_only_the_plain_language_guide() -> (
    None
):
    """확정일자 안내는 생활법령 해설만으로 두지 않는다.

    우선변제권은 보증금 전액이 걸린 권리다. 해설 페이지는 개편되면 문장이
    바뀌지만 조문은 조문이므로, 사용자가 원문을 직접 열 수 있어야 한다.
    """
    catalog = load_housing_sources()
    source_ids = ACTION_POLICIES["GET_CONFIRMED_DATE"].source_ids

    assert "housing_lease_act_article3_2" in source_ids
    assert catalog["housing_lease_act_article3_2"].organization == "국가법령정보센터"


def test_startup_verifies_housing_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "app.main.verify_housing_sources", lambda: calls.append("verified")
    )

    with TestClient(app):
        pass

    assert calls == ["verified"]
