import json
from functools import lru_cache
from pathlib import Path

from app.schemas.wealth_guidance import WealthGuidanceResponse


GUIDANCE_DATA_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "wealth" / "guidance_v0_1.json"
)
REVIEWED_DATE = "2026-08-12"


@lru_cache(maxsize=1)
def get_wealth_guidance() -> WealthGuidanceResponse:
    raw_data = json.loads(GUIDANCE_DATA_PATH.read_text(encoding="utf-8"))
    guidance = WealthGuidanceResponse.model_validate(raw_data)

    module_codes = [module.code for module in guidance.modules]
    module_orders = [module.order for module in guidance.modules]
    if len(module_codes) != len(set(module_codes)):
        raise ValueError("wealth guidance module code must be unique")
    if module_orders != list(range(1, len(guidance.modules) + 1)):
        raise ValueError("wealth guidance module order must be contiguous")

    source_ids = [source.source_id for source in guidance.official_sources]
    source_urls = [source.source_url for source in guidance.official_sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("wealth guidance source_id must be unique")
    if len(source_urls) != len(set(source_urls)):
        raise ValueError("wealth guidance source_url must be unique")
    if any(
        source.retrieved_at != REVIEWED_DATE
        for source in guidance.official_sources
    ):
        raise ValueError("wealth guidance source review date is stale")

    source_catalog = {
        source.source_id: source for source in guidance.official_sources
    }
    for module in guidance.modules:
        for source_id in module.source_ids:
            source = source_catalog.get(source_id)
            if source is None:
                raise ValueError(f"unknown wealth guidance source_id: {source_id}")
            if module.code not in source.supports:
                raise ValueError(
                    f"wealth guidance source {source_id} does not support {module.code}"
                )

    return guidance
