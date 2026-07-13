import re
from typing import List, Tuple

from openai import OpenAIError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Conversation, ConversationMessage, User
from app.services.chunking import excerpt
from app.services.embeddings import OpenAIUnavailable, _client
from app.services.retrieval import RetrievedChunk, retrieve_chunks


settings = get_settings()

SYSTEM_PROMPT = """Bạn là trợ lý tài liệu nội bộ.
Chỉ trả lời dựa trên ngữ cảnh tài liệu được cung cấp.
BẮT BUỘC trả lời bằng tiếng Việt nếu người dùng hỏi bằng tiếng Việt.
Không tự chuyển sang tiếng Anh, không giải thích bằng tiếng Anh.
Nếu ngữ cảnh không đủ thông tin, nói rõ rằng thông tin không được tìm thấy trong các tài liệu đã cung cấp.
Không bịa số liệu, ngày tháng, điều khoản, tên nguồn.
Trả lời ngắn gọn, trực tiếp, không đưa phần suy luận nội bộ.
"""


def answer_question(
    db: Session,
    user: User,
    message: str,
    conversation_id: str = None,
) -> Tuple[str, Conversation, List[dict]]:
    retrieved = retrieve_chunks(db, user, message, limit=max(settings.chat_context_limit * 2, 8))
    context_chunks = _select_chat_context(message, retrieved)
    conversation = _get_or_create_conversation(db, user, conversation_id, message)
    citations = [_citation_dict(item) for item in context_chunks]

    db.add(ConversationMessage(conversation_id=conversation.id, role="user", content=message, citations=[]))
    answer = _generate_answer(message, context_chunks)
    if _is_no_information_answer(answer):
        answer = _no_information_answer(message)
        citations = []
    db.add(
        ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            citations=citations,
        )
    )
    db.commit()
    db.refresh(conversation)
    return answer, conversation, citations


def _get_or_create_conversation(db: Session, user: User, conversation_id: str, message: str) -> Conversation:
    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
            .one_or_none()
        )
        if conversation is not None:
            return conversation

    title = message.strip()[:80] or "New conversation"
    conversation = Conversation(user_id=user.id, title=title)
    db.add(conversation)
    db.flush()
    return conversation


def _select_chat_context(message: str, retrieved: List[RetrievedChunk]) -> List[RetrievedChunk]:
    selected = [
        item
        for item in retrieved
        if item.score >= settings.chat_min_relevance_score and item.lexical_score >= settings.chat_min_lexical_score
    ]
    if not selected and retrieved:
        top = retrieved[0]
        if top.score >= max(0.78, settings.chat_min_relevance_score) and top.lexical_score > 0:
            selected = [top]
    return selected[: max(1, settings.chat_context_limit)]


def _generate_answer(message: str, retrieved: List[RetrievedChunk]) -> str:
    if not retrieved:
        return "Không tìm thấy thông tin phù hợp trong các tài liệu hiện có."
    if settings.use_fake_openai:
        return "Đây là câu trả lời giả lập cho môi trường test. Vui lòng cấu hình OPENAI_API_KEY để dùng mô hình thật."
    if not settings.openai_api_key:
        raise OpenAIUnavailable("OPENAI_API_KEY is not configured")

    context = _build_limited_context(retrieved)
    user_prompt = f"""Ngữ cảnh tài liệu:
{context}

Câu hỏi của người dùng:
{message}

Yêu cầu trả lời:
- Trả lời bằng tiếng Việt.
- Chỉ dùng thông tin trong ngữ cảnh tài liệu.
- Nếu không đủ thông tin, trả lời đúng mẫu: "Thông tin không được tìm thấy trong các tài liệu đã cung cấp."
"""

    client = _client()
    try:
        if settings.api_provider == "openai" and not settings.openai_base_url and hasattr(client, "responses"):
            response = client.responses.create(
                model=settings.openai_chat_model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=settings.openai_temperature,
            )
            text = getattr(response, "output_text", None)
            if text:
                return _clean_model_answer(text)

        response = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.openai_temperature,
        )
    except OpenAIError as exc:
        raise OpenAIUnavailable(f"OpenAI chat request failed: {exc}") from exc
    return _clean_model_answer(response.choices[0].message.content)


def _clean_model_answer(answer: str) -> str:
    text = (answer or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    text = re.sub(r"^\s*(answer|final answer)\s*:\s*", "", text, flags=re.IGNORECASE).strip()
    return text


def _is_no_information_answer(answer: str) -> bool:
    normalized = answer.lower()
    markers = [
        "không tìm thấy",
        "không được tìm thấy",
        "khong tim thay",
        "khong duoc tim thay",
        "không có trong tài liệu",
        "khong co trong tai lieu",
        "not found in the document",
        "not found in the documents",
    ]
    return any(marker in normalized for marker in markers)


def _no_information_answer(message: str) -> str:
    topic = re.sub(r"\s+", " ", message.strip(" \t\r\n?.!")).strip()
    replacements = [
        r"^tài liệu\s+có\s+nói\s+về\s+",
        r"^tai lieu\s+co\s+noi\s+ve\s+",
        r"^có\s+nói\s+về\s+",
        r"^co\s+noi\s+ve\s+",
        r"^cho\s+tôi\s+biết\s+về\s+",
        r"^cho\s+toi\s+biet\s+ve\s+",
        r"\s+như\s+thế\s+nào$",
        r"\s+nhu\s+the\s+nao$",
        r"\s+không$",
        r"\s+khong$",
    ]
    for pattern in replacements:
        topic = re.sub(pattern, "", topic, flags=re.IGNORECASE).strip()
    topic = re.sub(r"\btết\b", "Tết", topic, flags=re.IGNORECASE)
    if not topic or len(topic) > 120:
        return "Thông tin không được tìm thấy trong các tài liệu đã cung cấp."
    return f"Thông tin về {topic} không được tìm thấy trong các tài liệu đã cung cấp."


def _build_limited_context(retrieved: List[RetrievedChunk]) -> str:
    parts = []
    used_chars = 0
    for index, item in enumerate(retrieved, start=1):
        content = item.chunk.content.strip()
        if len(content) > settings.chat_chunk_max_chars:
            content = content[: settings.chat_chunk_max_chars].rstrip() + "..."
        header = f"[{index}] File: {item.document.filename} | Page: {item.chunk.page_number} | Chunk: {item.chunk.id}"
        part = f"{header}\n{content}"
        if used_chars + len(part) > settings.chat_context_max_chars:
            remaining = settings.chat_context_max_chars - used_chars
            if remaining > 240:
                parts.append(part[:remaining].rstrip() + "...")
            break
        parts.append(part)
        used_chars += len(part)
    return "\n\n".join(parts)


def _citation_dict(item: RetrievedChunk) -> dict:
    return {
        "document_id": item.document.id,
        "filename": item.document.filename,
        "page_number": item.chunk.page_number,
        "chunk_id": item.chunk.id,
        "excerpt": excerpt(item.chunk.content),
    }
