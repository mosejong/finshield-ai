"""서버가 말하는 "오늘" 이 사용자가 사는 날짜와 같은지.

컨테이너는 UTC 로 돈다. 한국 시각 00:00~09:00 사이에는 UTC 날짜가 하루 뒤처져
있고, 그 구간에서 `date.today()` 를 쓰면 사용자가 방금 한 일이 미래가 된다.
여기 있는 테스트는 그 9시간을 실제로 재현해서 고정한다.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.core.clock import SEOUL, now_kst, today_kst
from app.schemas.housing import DepositRiskRequest, LeaseStage


UTC = timezone.utc


def test_seoul_is_nine_hours_ahead_of_utc() -> None:
    assert SEOUL.utcoffset(None) == timedelta(hours=9)


def test_now_kst_carries_the_offset() -> None:
    """naive datetime 을 돌려주면 호출한 쪽에서 다시 서버 시간대로 해석된다."""
    assert now_kst().utcoffset() == timedelta(hours=9)


def test_today_kst_is_the_korean_date_not_the_server_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한국 시각 2026-03-02 07:00 = UTC 2026-03-01 22:00.

    이 순간 `date.today()` 는 3월 1일을, 사용자는 3월 2일을 본다.
    """
    frozen = datetime(2026, 3, 1, 22, 0, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return frozen.astimezone(tz) if tz else frozen.replace(tzinfo=None)

    monkeypatch.setattr("app.core.clock.datetime", FrozenDatetime)

    assert today_kst() == date(2026, 3, 2)


def test_move_in_report_today_is_accepted_before_nine_in_the_morning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """오전 7시에 전입신고를 마친 사람이 오늘 날짜를 넣을 수 있어야 한다.

    이 검증이 UTC 기준이면 그 사용자는 자기가 방금 한 일을 입력하지 못한다.
    화면에는 "미래 날짜" 라고 뜨는데 사용자 입장에서는 미래가 아니다.
    """
    monkeypatch.setattr("app.schemas.housing.today_kst", lambda: date(2026, 3, 2))

    request = DepositRiskRequest(
        stage=LeaseStage.MOVED_IN,
        deposit_krw=100_000_000,
        move_in_reported_on=date(2026, 3, 2),
    )

    assert request.move_in_reported_on == date(2026, 3, 2)


def test_tomorrow_is_still_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.schemas.housing.today_kst", lambda: date(2026, 3, 2))

    with pytest.raises(ValidationError):
        DepositRiskRequest(
            stage=LeaseStage.MOVED_IN,
            deposit_krw=100_000_000,
            move_in_reported_on=date(2026, 3, 3),
        )


def test_source_retrieved_today_does_not_block_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """오늘 확인한 링크를 오늘 날짜로 적고 아침에 배포하면 앱이 떠야 한다.

    UTC 기준이면 기동 시점 무결성 검사가 그 날짜를 미래로 보고 예외를 던진다.
    그때 죽는 것은 출처 하나가 아니라 서비스 전체다.
    """
    from app.domain import official_sources

    monkeypatch.setattr(official_sources, "today_kst", lambda: date(2026, 3, 2))

    catalog = official_sources.build_catalog(
        [
            _source("a", "2026-03-02"),
        ]
    )

    assert set(catalog) == {"a"}


def _source(source_id: str, retrieved_at: str):
    from app.schemas.analysis import OfficialSource

    return OfficialSource(
        source_id=source_id,
        organization="국가법령정보센터",
        title="테스트 출처",
        source_url=f"https://law.go.kr/{source_id}",
        retrieved_at=retrieved_at,
        supports=["CHECK_REGISTRY"],
    )
