from app.services.embeddings import _fake_embedding


def test_fake_embedding_is_deterministic_and_normalized():
    first = _fake_embedding("hello")
    second = _fake_embedding("hello")
    total = sum(value * value for value in first)

    assert first == second
    assert 0.99 <= total <= 1.01
