from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_money_mule_signal() -> None:
    response = client.post(
        "/api/v1/analyze",
        json={
            "text": "계좌로 입금받고 다시 보내주시면 됩니다.",
            "persona": "early_career",
            "state": "received_only",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["risk_score"] > 0
    assert any(signal["code"] == "money_mule" for signal in body["signals"])


def test_benign_message_starts_low() -> None:
    response = client.post(
        "/api/v1/analyze",
        json={"text": "내일 오전 10시에 회의가 있습니다."},
    )
    assert response.status_code == 200
    assert response.json()["risk_level"] == "low"
