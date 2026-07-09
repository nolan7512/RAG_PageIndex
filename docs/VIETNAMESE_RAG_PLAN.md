# Vietnamese RAG Optimization Plan

## Current Implementation

This MVP now includes a lightweight Vietnamese-aware retrieval layer:

- Unicode NFC normalization for parsed chunks.
- Whitespace and broken-newline cleanup before chunking.
- Diacritic-insensitive lexical scoring, so queries such as `thoi han thanh toan` can match `thời hạn thanh toán`.
- Vietnamese stopword filtering for keyword fallback.
- Hybrid retrieval remains vector-first, then merges Vietnamese lexical matches and PageIndex page boosts.

This is designed for the current scope: 1-2 internal users, small document volume, CPU-only server, and external API models.

## Recommended Test Configuration

For OpenAI:

```env
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

For stronger retrieval quality:

```env
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_DIMENSIONS=3072
```

For Gemini OpenAI-compatible mode:

```env
API_PROVIDER=gemini
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
OPENAI_CHAT_MODEL=gemini-2.5-flash
OPENAI_EMBEDDING_MODEL=text-embedding-004
OPENAI_EMBEDDING_DIMENSIONS=768
```

If embedding dimensions change after data has been indexed, clear the database volume and re-ingest documents.

## Next Production Upgrades

- Replace lightweight lexical scan with OpenSearch/Elasticsearch BM25 plus a Vietnamese analyzer.
- Add a multilingual reranker such as `bge-reranker-v2-m3`.
- Use PaddleOCR/VietOCR or MinerU through RAG-Anything for Vietnamese scanned PDFs.
- Add document-structure chunking by heading, table, page, and slide.
- Add an evaluation set for Vietnamese Q&A, citation accuracy, OCR quality, and no-answer behavior.
