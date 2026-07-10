from app.models import Document, DocumentChunk
from app.services import chat
from app.services.retrieval import RetrievedChunk


def _retrieved(score=0.8, lexical_score=0.5, content="Tai nạn lao động"):
    document = Document(id="doc-1", filename="doc.pdf", storage_path="/tmp/doc.pdf", uploaded_by="user-1")
    chunk = DocumentChunk(
        id="chunk-1",
        document_id="doc-1",
        page_number=1,
        content=content,
        content_type="text",
        token_count=10,
    )
    return RetrievedChunk(chunk=chunk, document=document, score=score, lexical_score=lexical_score)


def test_select_chat_context_requires_lexical_relevance():
    selected = chat._select_chat_context("chính sách thưởng tết", [_retrieved(score=0.82, lexical_score=0)])

    assert selected == []


def test_select_chat_context_keeps_relevant_chunks():
    item = _retrieved(score=0.82, lexical_score=0.4)

    assert chat._select_chat_context("tai nạn lao động", [item]) == [item]


def test_build_limited_context_caps_chunk_text(monkeypatch):
    monkeypatch.setattr(chat.settings, "chat_chunk_max_chars", 20)
    monkeypatch.setattr(chat.settings, "chat_context_max_chars", 120)

    context = chat._build_limited_context([_retrieved(content="x" * 100)])

    assert "x" * 21 not in context
    assert context.endswith("...")


def test_no_information_answer_detection():
    assert chat._is_no_information_answer("Thông tin này không tìm thấy trong tài liệu.")
    assert chat._is_no_information_answer("Thông tin về chính sách thưởng Tết không được tìm thấy trong các tài liệu đã cung cấp.")
    assert not chat._is_no_information_answer("Ngày hiệu lực là 01/01/2024.")


def test_no_information_answer_formats_topic():
    answer = chat._no_information_answer("chính sách thưởng tết như thế nào ?")

    assert answer == "Thông tin về chính sách thưởng Tết không được tìm thấy trong các tài liệu đã cung cấp."
