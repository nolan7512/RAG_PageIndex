import hashlib
import math
import os
from typing import Iterable, List

from openai import OpenAI, OpenAIError

from app.config import get_settings


settings = get_settings()


class OpenAIUnavailable(RuntimeError):
    pass


def _client() -> OpenAI:
    _clear_blank_openai_base_url_env()
    kwargs = {}
    if settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    base_url = (settings.openai_base_url or "").strip()
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _clear_blank_openai_base_url_env() -> None:
    for name in ("OPENAI_BASE_URL", "OPENAI_API_BASE"):
        if os.environ.get(name, "").strip() == "":
            os.environ.pop(name, None)


def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    text_list = [text for text in texts]
    if not text_list:
        return []
    if settings.use_fake_openai:
        return [_fake_embedding(text) for text in text_list]
    if not settings.openai_api_key:
        raise OpenAIUnavailable("OPENAI_API_KEY is not configured")

    try:
        response = _client().embeddings.create(
            model=settings.openai_embedding_model,
            input=text_list,
            dimensions=settings.openai_embedding_dimensions,
            encoding_format="float",
        )
    except OpenAIError as exc:
        raise OpenAIUnavailable(f"OpenAI embedding request failed: {exc}") from exc
    return [item.embedding for item in response.data]


def embed_text(text: str) -> List[float]:
    return embed_texts([text])[0]


def _fake_embedding(text: str) -> List[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    for index in range(settings.openai_embedding_dimensions):
        byte = digest[index % len(digest)]
        values.append((byte / 255.0) - 0.5)
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]
