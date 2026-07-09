import asyncio
import json
from pathlib import Path
from typing import List, Tuple

from app.config import get_settings
from app.services.chunking import ContentBlock
from app.services.storage import document_artifact_dir


settings = get_settings()


async def parse_document(document_id: str, path: Path, filename: str, mime_type: str = "") -> Tuple[List[ContentBlock], int]:
    blocks = await _try_rag_anything(document_id, path, filename)
    if not blocks:
        blocks = _parse_with_lightweight_parsers(document_id, path, filename, mime_type)
    page_count = max([block.page_number for block in blocks], default=0)
    artifact_path = document_artifact_dir(document_id) / "parsed.json"
    artifact_path.write_text(
        json.dumps([_block_to_dict(block) for block in blocks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return blocks, page_count


async def _try_rag_anything(document_id: str, path: Path, filename: str) -> List[ContentBlock]:
    if not settings.enable_rag_anything:
        return []
    try:
        from raganything import RAGAnything, RAGAnythingConfig  # type: ignore
    except Exception:
        return []

    try:
        working_dir = document_artifact_dir(document_id) / "raganything"
        output_dir = document_artifact_dir(document_id) / "raganything-output"
        config = RAGAnythingConfig(
            working_dir=str(working_dir),
            parser=settings.rag_anything_parser,
            parse_method="auto",
            enable_image_processing=True,
            enable_table_processing=True,
            enable_equation_processing=True,
        )
        rag = RAGAnything(config=config)

        process = getattr(rag, "process_document_complete", None)
        if process is None:
            return []
        result = process(file_path=str(path), output_dir=str(output_dir))
        if asyncio.iscoroutine(result):
            await result

        blocks = _load_rag_anything_outputs(document_id, output_dir, filename)
        return blocks
    except Exception:
        return []


def _load_rag_anything_outputs(document_id: str, output_dir: Path, filename: str) -> List[ContentBlock]:
    blocks: List[ContentBlock] = []
    if not output_dir.exists():
        return blocks

    for candidate in output_dir.rglob("*.json"):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data if isinstance(data, list) else data.get("chunks") or data.get("content") or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("text") or "").strip()
            if not content:
                continue
            blocks.append(
                ContentBlock(
                    document_id=document_id,
                    page_number=int(item.get("page_number") or item.get("page") or 1),
                    block_type=str(item.get("type") or item.get("content_type") or "text"),
                    content=content,
                    metadata={"parser": "rag-anything", "source_file": filename},
                )
            )
    return blocks


def _parse_with_lightweight_parsers(
    document_id: str, path: Path, filename: str, mime_type: str = ""
) -> List[ContentBlock]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(document_id, path, filename)
    if suffix in {".txt", ".md", ".csv"}:
        return [_text_block(document_id, 1, path.read_text(encoding="utf-8", errors="ignore"), filename)]
    if suffix == ".docx":
        return _parse_docx(document_id, path, filename)
    if suffix == ".pptx":
        return _parse_pptx(document_id, path, filename)
    if suffix == ".xlsx":
        return _parse_xlsx(document_id, path, filename)
    if suffix in {".png", ".jpg", ".jpeg"} or mime_type.startswith("image/"):
        return _parse_image(document_id, path, filename)
    return [_text_block(document_id, 1, f"Unsupported file type for fallback parser: {filename}", filename)]


def _parse_pdf(document_id: str, path: Path, filename: str) -> List[ContentBlock]:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        return [_text_block(document_id, 1, f"PDF parser unavailable: {exc}", filename)]

    blocks: List[ContentBlock] = []
    reader = PdfReader(str(path))
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            blocks.append(_text_block(document_id, page_index, text, filename, parser="pypdf"))
    if not blocks:
        blocks = _ocr_pdf(document_id, path, filename, len(reader.pages))
    return blocks


def _ocr_pdf(document_id: str, path: Path, filename: str, page_count: int) -> List[ContentBlock]:
    if not settings.pdf_ocr_enabled:
        return [_text_block(document_id, 1, "No extractable PDF text found. OCR parser is disabled.", filename)]

    try:
        import pypdfium2 as pdfium
        import pytesseract
    except Exception as exc:
        return [_text_block(document_id, 1, f"No extractable PDF text found. OCR parser unavailable: {exc}", filename)]

    blocks: List[ContentBlock] = []
    try:
        pdf = pdfium.PdfDocument(str(path))
        max_pages = min(len(pdf), max(1, settings.pdf_ocr_max_pages))
        for page_index in range(max_pages):
            page = pdf[page_index]
            bitmap = page.render(scale=settings.pdf_ocr_scale)
            image = bitmap.to_pil()
            text = pytesseract.image_to_string(image, lang=settings.pdf_ocr_lang).strip()
            blocks.append(
                ContentBlock(
                    document_id=document_id,
                    page_number=page_index + 1,
                    block_type="text",
                    content=text or "OCR produced no text for this page.",
                    metadata={
                        "parser": "tesseract-pdf-ocr",
                        "source_file": filename,
                        "ocr_lang": settings.pdf_ocr_lang,
                        "ocr_scale": settings.pdf_ocr_scale,
                    },
                )
            )
    except Exception as exc:
        return [_text_block(document_id, 1, f"No extractable PDF text found. OCR failed: {exc}", filename)]

    if page_count > len(blocks):
        blocks.append(
            _text_block(
                document_id,
                len(blocks) + 1,
                f"OCR stopped after {len(blocks)} of {page_count} pages due to PDF_OCR_MAX_PAGES.",
                filename,
                parser="tesseract-pdf-ocr",
            )
        )
    return blocks or [_text_block(document_id, 1, "No extractable PDF text found. OCR produced no pages.", filename)]


def _parse_docx(document_id: str, path: Path, filename: str) -> List[ContentBlock]:
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))
    paragraphs = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
    table_text = []
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                table_text.append(" | ".join(cells))
    content = "\n\n".join(paragraphs + table_text)
    return [_text_block(document_id, 1, content or "Empty DOCX document.", filename, parser="python-docx")]


def _parse_pptx(document_id: str, path: Path, filename: str) -> List[ContentBlock]:
    from pptx import Presentation

    presentation = Presentation(str(path))
    blocks: List[ContentBlock] = []
    for index, slide in enumerate(presentation.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                texts.append(shape.text.strip())
        blocks.append(_text_block(document_id, index, "\n".join(texts), filename, parser="python-pptx"))
    return blocks


def _parse_xlsx(document_id: str, path: Path, filename: str) -> List[ContentBlock]:
    from openpyxl import load_workbook

    workbook = load_workbook(str(path), read_only=True, data_only=True)
    blocks: List[ContentBlock] = []
    for sheet_index, sheet in enumerate(workbook.worksheets, start=1):
        rows = []
        for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            if row_index > 200:
                rows.append("...")
                break
            values = [str(value) for value in row if value is not None and str(value).strip()]
            if values:
                rows.append(" | ".join(values))
        blocks.append(
            ContentBlock(
                document_id=document_id,
                page_number=sheet_index,
                block_type="table",
                content=f"Sheet: {sheet.title}\n" + "\n".join(rows),
                metadata={"parser": "openpyxl", "source_file": filename, "sheet": sheet.title},
            )
        )
    return blocks


def _parse_image(document_id: str, path: Path, filename: str) -> List[ContentBlock]:
    try:
        from PIL import Image
        import pytesseract

        image = Image.open(str(path))
        text = pytesseract.image_to_string(image, lang="vie+eng")
        content = text.strip() or f"Image file {filename} produced no OCR text."
    except Exception as exc:
        content = f"Image OCR unavailable for {filename}: {exc}"
    return [
        ContentBlock(
            document_id=document_id,
            page_number=1,
            block_type="image_caption",
            content=content,
            metadata={"parser": "pytesseract", "source_file": filename},
        )
    ]


def _text_block(
    document_id: str,
    page_number: int,
    content: str,
    filename: str,
    parser: str = "fallback",
) -> ContentBlock:
    return ContentBlock(
        document_id=document_id,
        page_number=page_number,
        block_type="text",
        content=content,
        metadata={"parser": parser, "source_file": filename},
    )


def _block_to_dict(block: ContentBlock):
    return {
        "document_id": block.document_id,
        "page_number": block.page_number,
        "block_type": block.block_type,
        "content": block.content,
        "metadata": block.metadata,
    }
