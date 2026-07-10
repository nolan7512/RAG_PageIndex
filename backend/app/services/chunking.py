from dataclasses import dataclass
from typing import Any, Dict, Iterable, List
import re

from app.services.vietnamese import normalize_vietnamese_text

try:
    import tiktoken
except ImportError:  # pragma: no cover - dependency exists in normal installs
    tiktoken = None


@dataclass
class ContentBlock:
    document_id: str
    page_number: int
    block_type: str
    content: str
    metadata: Dict[str, Any]


@dataclass
class Chunk:
    document_id: str
    page_number: int
    chunk_index: int
    content: str
    content_type: str
    token_count: int
    metadata: Dict[str, Any]


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if tiktoken is None:
        return max(1, len(text.split()))
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def _split_long_text(text: str, max_tokens: int) -> Iterable[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    buffer: List[str] = []
    buffer_tokens = 0
    for paragraph in paragraphs:
        paragraph_tokens = count_tokens(paragraph)
        if paragraph_tokens > max_tokens:
            words = paragraph.split()
            step = max(80, max_tokens)
            for index in range(0, len(words), step):
                yield " ".join(words[index : index + step])
            continue

        if buffer and buffer_tokens + paragraph_tokens > max_tokens:
            yield "\n\n".join(buffer)
            buffer = []
            buffer_tokens = 0

        buffer.append(paragraph)
        buffer_tokens += paragraph_tokens

    if buffer:
        yield "\n\n".join(buffer)


def _split_structural_sections(text: str) -> List[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines()]
    sections: List[tuple[str, List[str]]] = []
    current_title = ""
    current_lines: List[str] = []

    for line in lines:
        if not line:
            if current_lines:
                current_lines.append("")
            continue
        if _looks_like_heading(line):
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = line
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_title, current_lines))

    normalized = [(title, "\n".join(lines).strip()) for title, lines in sections if "\n".join(lines).strip()]
    return normalized or [("", text.strip())]


def _looks_like_heading(line: str) -> bool:
    if len(line) > 140:
        return False
    patterns = [
        r"^[IVXLCDM]{1,6}\.\s+\S+",
        r"^\d+(\.\d+){0,4}\.?\s+\S+",
        r"^[A-ZĐ][A-ZĐ\s]{4,}$",
    ]
    return any(re.match(pattern, line) for pattern in patterns)


def blocks_to_chunks(
    document_id: str,
    blocks: List[ContentBlock],
    max_tokens: int = 900,
    overlap_tokens: int = 120,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    index = 0
    for block in blocks:
        content = normalize_vietnamese_text(block.content)
        if not content:
            continue
        for section_title, section_content in _split_structural_sections(content):
            metadata = dict(block.metadata or {})
            if section_title:
                metadata["section_title"] = section_title
            for piece in _split_long_text(section_content, max_tokens=max_tokens):
                token_count = count_tokens(piece)
                chunks.append(
                    Chunk(
                        document_id=document_id,
                        page_number=max(1, block.page_number),
                        chunk_index=index,
                        content=piece,
                        content_type=block.block_type,
                        token_count=token_count,
                        metadata=metadata,
                    )
                )
                index += 1

                if overlap_tokens and token_count > max_tokens:
                    words = piece.split()
                    overlap = " ".join(words[-overlap_tokens:])
                    if overlap:
                        block = ContentBlock(
                            document_id=document_id,
                            page_number=block.page_number,
                            block_type=block.block_type,
                            content=overlap,
                            metadata=metadata,
                        )
    return chunks


def excerpt(text: str, max_chars: int = 360) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(0, max_chars - 3)].rstrip() + "..."
