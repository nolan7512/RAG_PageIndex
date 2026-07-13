from app.models import Document, DocumentChunk
from app.services import retrieval
from app.services.retrieval import RetrievedChunk, result_to_dict


def test_result_to_dict_maps_citation_fields():
    document = Document(
        id="doc-1",
        filename="contract.pdf",
        storage_path="/tmp/contract.pdf",
        uploaded_by="user-1",
        relative_path="HR/Contracts/contract.pdf",
        folder_path="HR/Contracts",
    )
    chunk = DocumentChunk(
        id="chunk-1",
        document_id="doc-1",
        page_number=7,
        content="The payment term is thirty days from invoice receipt.",
        content_type="text",
        token_count=10,
    )
    result = RetrievedChunk(chunk=chunk, document=document, score=0.91234)

    payload = result_to_dict(result)

    assert payload["document_id"] == "doc-1"
    assert payload["filename"] == "contract.pdf"
    assert payload["relative_path"] == "HR/Contracts/contract.pdf"
    assert payload["folder_path"] == "HR/Contracts"
    assert payload["page_number"] == 7
    assert payload["chunk_id"] == "chunk-1"
    assert payload["score"] == 0.9123
    assert payload["rerank_score"] == 0.0
    assert "payment term" in payload["excerpt"]


def test_apply_reranker_blends_scores(monkeypatch):
    document = Document(id="doc-1", filename="contract.pdf", storage_path="/tmp/contract.pdf", uploaded_by="user-1")
    chunks = [
        DocumentChunk(id="a", document_id="doc-1", page_number=1, content="low", content_type="text", token_count=1),
        DocumentChunk(id="b", document_id="doc-1", page_number=1, content="high", content_type="text", token_count=1),
    ]
    results = [
        RetrievedChunk(chunk=chunks[0], document=document, score=0.8),
        RetrievedChunk(chunk=chunks[1], document=document, score=0.7),
    ]
    monkeypatch.setattr(retrieval.settings, "reranker_provider", "local_bge_m3")
    monkeypatch.setattr(retrieval.settings, "reranker_top_k", 30)
    monkeypatch.setattr(retrieval.settings, "reranker_weight", 0.5)
    monkeypatch.setattr(retrieval, "rerank_scores", lambda query, passages: [0.0, 10.0])

    retrieval._apply_reranker("query", results)

    assert results[0].rerank_score == 0.0
    assert results[1].rerank_score == 1.0
    assert results[1].score > results[0].score
