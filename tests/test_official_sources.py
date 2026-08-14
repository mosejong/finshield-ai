"""공식 출처 데이터의 무결성과 신선도 정책을 검증한다.

이전에는 retrieved_at 이 특정 날짜와 다르면 ValueError 를 던져서, 링크를 하나만
재확인해도 분석 요청이 500 이 되었다. 게다가 기동 시 검증이 없어 startup 과
health check 는 통과했다.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.fraud.sources import (
    SOURCE_DATA_PATH,
    SOURCE_REVIEW_INTERVAL_DAYS,
    OfficialSourceDataError,
    load_official_sources,
    stale_official_sources,
    verify_official_sources,
)
from app.main import app


@pytest.fixture
def source_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """official_sources.json 을 임시 파일로 바꿔 원본을 건드리지 않는다."""
    original = json.loads(Path(SOURCE_DATA_PATH).read_text(encoding="utf-8"))

    def write(records: list[dict]) -> None:
        path = tmp_path / "official_sources.json"
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr("app.domain.fraud.sources.SOURCE_DATA_PATH", path)
        load_official_sources.cache_clear()

    yield original, write
    load_official_sources.cache_clear()


def test_re_verifying_one_source_does_not_break_analysis(source_file) -> None:
    """링크 하나를 오늘 재확인해 날짜를 갱신해도 정상 동작해야 한다."""
    original, write = source_file
    records = [dict(record) for record in original]
    records[0]["retrieved_at"] = date.today().isoformat()
    write(records)

    catalog = load_official_sources()

    assert catalog[records[0]["source_id"]].retrieved_at == date.today().isoformat()


def test_future_retrieved_at_is_rejected(source_file) -> None:
    """미래 날짜는 데이터 오류다."""
    original, write = source_file
    records = [dict(record) for record in original]
    records[0]["retrieved_at"] = (date.today() + timedelta(days=1)).isoformat()
    write(records)

    with pytest.raises(OfficialSourceDataError, match="future retrieved_at"):
        load_official_sources()


def test_malformed_retrieved_at_is_rejected(source_file) -> None:
    original, write = source_file
    records = [dict(record) for record in original]
    records[0]["retrieved_at"] = "2026-13-99"
    write(records)

    with pytest.raises(OfficialSourceDataError, match="ISO-8601"):
        load_official_sources()


def test_duplicate_source_id_is_rejected(source_file) -> None:
    original, write = source_file
    records = [dict(original[0]), dict(original[0])]
    write(records)

    with pytest.raises(OfficialSourceDataError, match="source_id must be unique"):
        load_official_sources()


def test_old_source_is_reported_stale_but_still_usable(source_file) -> None:
    """재확인 주기가 지나도 분석을 막지 않는다. 안전 안내를 끊는 쪽이 더 위험하다."""
    original, write = source_file
    records = [dict(record) for record in original]
    stale_date = date.today() - timedelta(days=SOURCE_REVIEW_INTERVAL_DAYS + 1)
    records[0]["retrieved_at"] = stale_date.isoformat()
    write(records)

    assert load_official_sources()  # 예외 없이 로드된다
    assert [source.source_id for source in stale_official_sources()] == [
        records[0]["source_id"]
    ]
    verify_official_sources()  # 경고만 남기고 통과한다


def test_recent_sources_are_not_stale() -> None:
    """현재 저장된 실제 데이터는 재확인 주기 안에 있어야 한다."""
    assert stale_official_sources() == []


def test_startup_verifies_official_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """기동 시 검증이 실제로 호출되는지 확인한다.

    이 호출이 빠지면 잘못된 데이터가 health check 를 통과하고 분석에서만 터진다.
    """
    calls: list[str] = []
    monkeypatch.setattr(
        "app.main.verify_official_sources", lambda: calls.append("verified")
    )

    with TestClient(app):
        pass

    assert calls == ["verified"]
