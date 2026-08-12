from fastapi.testclient import TestClient

from app.main import app
from app.services.wealth_guidance import get_wealth_guidance


client = TestClient(app)


def test_wealth_guidance_endpoint_returns_reviewed_modules_and_sources() -> None:
    response = client.get("/api/v1/guidance/wealth")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "0.1"
    assert [module["order"] for module in body["modules"]] == [1, 2, 3, 4]
    assert [module["code"] for module in body["modules"]] == [
        "money_flow",
        "saving_plan",
        "debt_credit",
        "investment_risk",
    ]
    assert all(
        source["retrieved_at"] == "2026-08-12"
        for source in body["official_sources"]
    )
    assert all(
        source["source_url"].startswith("https://")
        for source in body["official_sources"]
    )
    investment_module = body["modules"][-1]
    assert "kcie-investor-protection" in investment_module["source_ids"]


def test_wealth_guidance_has_bidirectional_source_support() -> None:
    guidance = get_wealth_guidance()
    sources = {source.source_id: source for source in guidance.official_sources}

    for module in guidance.modules:
        assert module.source_ids
        for source_id in module.source_ids:
            assert module.code in sources[source_id].supports


def test_wealth_guidance_does_not_include_product_or_trade_recommendations() -> None:
    guidance = get_wealth_guidance()
    educational_content = " ".join(
        text
        for module in guidance.modules
        for text in [
            module.title,
            module.summary,
            *module.check_questions,
            module.next_action,
        ]
    )

    for prohibited_phrase in (
        "종목 추천",
        "매수하세요",
        "매도하세요",
        "수익률 보장",
        "원금 보장",
    ):
        assert prohibited_phrase not in educational_content


def test_wealth_guidance_openapi_contract_is_exposed() -> None:
    schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/api/v1/guidance/wealth"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]
