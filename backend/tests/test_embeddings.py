from app.services import embeddings
from app.services.embeddings import _client, _fake_embedding, embed_texts


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


def test_local_bge_embeddings_use_sentence_transformer_adapter(monkeypatch):
    class FakeModel:
        def encode(self, texts, **kwargs):
            assert kwargs["normalize_embeddings"] is True
            return [[0.1, 0.2], [0.3, 0.4]]

    monkeypatch.setattr(embeddings.settings, "use_fake_openai", False)
    monkeypatch.setattr(embeddings.settings, "embedding_provider", "local_bge_m3")
    monkeypatch.setattr(embeddings, "_sentence_transformer_model", lambda: FakeModel())

    assert embed_texts(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]
