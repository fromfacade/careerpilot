def test_ai_status_endpoint_does_not_expose_secrets(client):
    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"enabled", "provider", "model", "configured", "available"}
    assert isinstance(body["enabled"], bool)
    assert "api_key" not in str(body).lower()
    assert "gemini_api_key" not in str(body)
