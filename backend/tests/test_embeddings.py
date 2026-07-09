from app.services.embeddings import _client, _fake_embedding


def test_fake_embedding_is_deterministic_and_normalized():
    first = _fake_embedding("hello")
    second = _fake_embedding("hello")
    total = sum(value * value for value in first)

    assert first == second
    assert 0.99 <= total <= 1.01


def test_openai_client_ignores_blank_base_url_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "")

    client = _client()

    assert str(client.base_url).startswith("https://api.openai.com")
