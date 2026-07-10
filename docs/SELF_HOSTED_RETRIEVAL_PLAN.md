# Self-Hosted Retrieval Upgrade Plan

## Goal

Move document understanding and retrieval toward a private setup where document text and embeddings stay on the server.

## Target Retrieval Stack

- Embedding: `BAAI/bge-m3`, self-hosted with sentence-transformers or a dedicated embedding service.
- Vector DB: keep Postgres + pgvector for the next internal milestone; switch to Qdrant/Milvus later if document volume grows.
- Hybrid search:
  - Short term: pgvector semantic search + local Vietnamese lexical scoring with tokenizer support.
  - Mid term: OpenSearch/Elasticsearch with Vietnamese analyzer, or BM25 over underthesea/pyvi tokens.
- Reranker: `BAAI/bge-reranker-v2-m3`, self-hosted, applied to top 30 candidates before selecting chat context.
- Chunking: structure-aware chunks with `section_title`, page number, OCR confidence, and parser metadata.

## Deployment Notes

BGE-M3 uses 1024-dimensional embeddings. Switching from OpenAI `text-embedding-3-small` 1536 dimensions requires:

1. Set embedding provider to local BGE-M3.
2. Set embedding dimensions to 1024.
3. Recreate pgvector storage or run a migration that rebuilds `document_chunks.embedding`.
4. Re-ingest all documents.

For the current 1-2 user internal server, start with CPU inference only if latency is acceptable. If ingestion becomes slow, move embedding/reranker into a separate service and batch requests.

## Current Implementation

The app now includes the local adapters, but they are opt-in:

```env
EMBEDDING_PROVIDER=local_bge_m3
LOCAL_EMBEDDING_MODEL=BAAI/bge-m3
LOCAL_EMBEDDING_DIMENSIONS=1024
LOCAL_EMBEDDING_DEVICE=cpu
LOCAL_EMBEDDING_BATCH_SIZE=8

RERANKER_PROVIDER=local_bge_m3
LOCAL_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
LOCAL_RERANKER_DEVICE=cpu
RERANKER_TOP_K=30
RERANKER_WEIGHT=0.35
```

Docker installs `sentence-transformers` best-effort. If the optional install fails, the app still runs with OpenAI-compatible embeddings.

To switch an existing server to BGE-M3, use a clean data reset because pgvector dimensions change:

```bash
cd ~/RAG_PageIndex
git pull
EMBEDDING_PROVIDER=local_bge_m3 \
OPENAI_EMBEDDING_DIMENSIONS=1024 \
RERANKER_PROVIDER=local_bge_m3 \
PUBLIC_HOST="10.30.0.15" \
./scripts/setup-ubuntu.sh

cd /opt/rag-pageindex
sudo docker compose down -v
sudo docker compose up --build -d
```

Then upload documents again so chunks are embedded with BGE-M3.

## Suggested Phases

### Phase 1: Local Embedding Adapter

- Done: add `EMBEDDING_PROVIDER=openai|local_bge_m3`.
- Done: add `LOCAL_EMBEDDING_MODEL=BAAI/bge-m3`.
- Todo: add `/admin/reindex` or a CLI re-index command.
- Required during switch: rebuild DB with 1024-dim pgvector.

### Phase 2: Reranker

- Done: retrieve top 30 by semantic + lexical.
- Done: rerank with `BAAI/bge-reranker-v2-m3` when `RERANKER_PROVIDER=local_bge_m3`.
- Done: chat context is already capped by `CHAT_CONTEXT_LIMIT`.
- Done: store `rerank_score` in search response for debugging.

### Phase 3: OpenSearch/BM25

- Add OpenSearch service only when document volume justifies it.
- Index fields: filename, page number, section title, normalized content, OCR confidence.
- Use Vietnamese analyzer/tokenizer or pre-tokenized underthesea/pyvi field.

### Phase 4: Citation Precision

- Use OCR line bounding boxes to highlight lines in the PDF preview.
- Map citation chunks to page + bbox list.
- Click citation → open PDF page → scroll/highlight relevant text box.
