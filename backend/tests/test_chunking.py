from app.services.chunking import ContentBlock, blocks_to_chunks, count_tokens, excerpt


def test_blocks_to_chunks_preserves_page_and_content_type():
    blocks = [
        ContentBlock(
            document_id="doc-1",
            page_number=3,
            block_type="table",
            content="Revenue | 100\nCost | 80",
            metadata={"sheet": "Summary"},
        )
    ]

    chunks = blocks_to_chunks("doc-1", blocks, max_tokens=20)

    assert len(chunks) == 1
    assert chunks[0].document_id == "doc-1"
    assert chunks[0].page_number == 3
    assert chunks[0].content_type == "table"
    assert chunks[0].metadata["sheet"] == "Summary"
    assert chunks[0].token_count == count_tokens(chunks[0].content)


def test_excerpt_trims_long_text():
    text = " ".join(["word"] * 200)
    value = excerpt(text, max_chars=80)

    assert len(value) <= 80
    assert value.endswith("...")


def test_blocks_to_chunks_adds_section_title_metadata():
    blocks = [
        ContentBlock(
            document_id="doc-1",
            page_number=2,
            block_type="text",
            content="I. MỤC ĐÍCH\nHướng dẫn tai nạn lao động.\n\nII. PHẠM VI\nToàn thể nhân viên.",
            metadata={"parser": "tesseract-pdf-ocr"},
        )
    ]

    chunks = blocks_to_chunks("doc-1", blocks, max_tokens=40)

    assert len(chunks) == 2
    assert chunks[0].metadata["section_title"] == "I. MỤC ĐÍCH"
    assert chunks[1].metadata["section_title"] == "II. PHẠM VI"
