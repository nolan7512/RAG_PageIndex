from app.models import Document, DocumentChunk
from app.services.retrieval import RetrievedChunk, result_to_dict


def test_result_to_dict_maps_citation_fields():
    document = Document(id="doc-1", filename="contract.pdf", storage_path="/tmp/contract.pdf", uploaded_by="user-1")
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
    assert payload["page_number"] == 7
    assert payload["chunk_id"] == "chunk-1"
    assert payload["score"] == 0.9123
    assert "payment term" in payload["excerpt"]
