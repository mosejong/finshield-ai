import json
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter

from app.schemas.analysis import Action, OfficialSource


SOURCE_DATA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "fraud" / "official_sources.json"
)


@lru_cache(maxsize=1)
def load_official_sources() -> dict[str, OfficialSource]:
    raw_data = json.loads(SOURCE_DATA_PATH.read_text(encoding="utf-8"))
    sources = TypeAdapter(list[OfficialSource]).validate_python(raw_data)

    source_ids = [source.source_id for source in sources]
    source_urls = [source.source_url for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("official source_id must be unique")
    if len(source_urls) != len(set(source_urls)):
        raise ValueError("official source_url must be unique")
    if any(source.retrieved_at != "2026-08-12" for source in sources):
        raise ValueError("official source retrieved_at is not the reviewed date")

    return {source.source_id: source for source in sources}


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
