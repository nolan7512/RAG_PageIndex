from functools import lru_cache
from typing import List

from app.config import get_settings


settings = get_settings()


def rerank_scores(query: str, passages: List[str]) -> List[float]:
    if settings.reranker_provider != "local_bge_m3" or not passages:
        return []
    try:
        model = _cross_encoder_model()
        scores = model.predict([(query, passage) for passage in passages])
    except Exception:
        return []
    values = scores.tolist() if hasattr(scores, "tolist") else scores
    return [float(value) for value in values]


@lru_cache(maxsize=1)
def _cross_encoder_model():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(settings.local_reranker_model, device=settings.local_reranker_device)
