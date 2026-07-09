from app.services import parsing


def test_pdf_ocr_disabled_returns_clear_block(monkeypatch, tmp_path):
    monkeypatch.setattr(parsing.settings, "pdf_ocr_enabled", False)
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    blocks = parsing._ocr_pdf("doc-1", pdf_path, "scan.pdf", page_count=1)

    assert len(blocks) == 1
    assert blocks[0].page_number == 1
    assert "OCR parser is disabled" in blocks[0].content
    assert blocks[0].metadata["parser"] == "fallback"
