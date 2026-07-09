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


def test_extract_paddle_lines_from_dict_includes_confidence_and_bbox():
    result = {
        "rec_texts": ["Xin chào", "Tai nạn lao động"],
        "rec_scores": [0.91, 0.82],
        "dt_polys": [
            [[0, 0], [100, 0], [100, 20], [0, 20]],
            [[0, 30], [180, 30], [180, 50], [0, 50]],
        ],
    }

    lines = parsing._extract_paddle_lines_from_dict(result)

    assert lines == [
        {"text": "Xin chào", "confidence": 0.91, "bbox": [[0, 0], [100, 0], [100, 20], [0, 20]]},
        {"text": "Tai nạn lao động", "confidence": 0.82, "bbox": [[0, 30], [180, 30], [180, 50], [0, 50]]},
    ]


def test_extract_tesseract_lines_groups_words_and_confidence():
    data = {
        "text": ["Tai", "nạn", ""],
        "conf": ["90", "80", "-1"],
        "block_num": [1, 1, 1],
        "par_num": [1, 1, 1],
        "line_num": [1, 1, 2],
        "left": [10, 42, 0],
        "top": [20, 20, 0],
        "width": [28, 34, 0],
        "height": [12, 12, 0],
    }

    lines, confidence_avg, confidence_min = parsing._extract_tesseract_lines(data)

    assert lines == [{"text": "Tai nạn", "confidence": 0.85, "bbox": [10, 20, 76, 32]}]
    assert confidence_avg == 0.85
    assert confidence_min == 0.85


def test_filter_ocr_lines_drops_low_confidence(monkeypatch):
    monkeypatch.setattr(parsing.settings, "ocr_min_line_confidence", 0.35)

    lines = parsing._filter_ocr_lines(
        [
            {"text": "nhiễu", "confidence": 0.2, "bbox": [0, 0, 10, 10]},
            {"text": "tai nạn lao động", "confidence": 0.9, "bbox": [0, 20, 100, 40]},
        ]
    )

    assert lines == [{"text": "tai nạn lao động", "confidence": 0.9, "bbox": [0, 20, 100, 40]}]
