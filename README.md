# RAG PageIndex MVP

Internal MVP for a small CPU-only RAG file manager. It provides upload, document processing, semantic search, chat answers with citations, and a worker pipeline that can use RAG-Anything and PageIndex when available.

## Stack

- Frontend: Next.js App Router
- API: FastAPI
- Worker: RQ + Redis
- Database: Postgres + pgvector
- Storage: local Docker volume
- LLM/Embedding: OpenAI API
- Parser: RAG-Anything adapter with lightweight fallback parsers
- Long-document structure: PageIndex adapter with heuristic fallback tree

## Quick Start

### Ubuntu one-shot server setup

On the Ubuntu server, copy this project folder to the server, then run:

```bash
chmod +x scripts/setup-ubuntu.sh
PUBLIC_HOST="your-server-ip-or-domain" ./scripts/setup-ubuntu.sh
```

For a dry internal demo without an OpenAI key:

```bash
USE_FAKE_OPENAI=true PUBLIC_HOST="your-server-ip-or-domain" ./scripts/setup-ubuntu.sh
```

The script installs Docker Engine and the Compose plugin, creates `/opt/rag-pageindex`, generates `.env` secrets if needed, opens UFW ports `3111` and `8111` when UFW is active, then runs `docker compose up --build -d`.

During setup, the installer asks which API provider to use, lets you paste the API key, checks the `/models` endpoint when available, and lets you choose chat/embedding models. Supported quick choices are OpenAI, Gemini OpenAI-compatible, OpenRouter, Together AI, custom OpenAI-compatible endpoint, or fake demo mode.

1. Copy environment settings:

```powershell
Copy-Item .env.example .env
```

2. Set `OPENAI_API_KEY` in `.env`.

3. Start the stack:

```powershell
docker compose up --build
```

4. Open:

```text
Frontend: http://localhost:3111
API docs:  http://localhost:8111/docs
```

Default admin credentials come from `.env`:

```text
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me-now
```

## Development

Backend tests:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Frontend:

```powershell
cd frontend
npm install
npm run lint
npm run build
```

## Notes

- RAG-Anything is attempted first when installed and enabled. If it is unavailable or fails for a file, the worker falls back to local parsers for PDF, DOCX, PPTX, XLSX, TXT, and images.
- Scanned PDFs are OCRed in the fallback parser by rendering pages with pypdfium2. `PDF_OCR_ENGINE=auto` prefers PaddleOCR when available, stores line confidence/bounding boxes, and falls back to Tesseract Vietnamese/English OCR. Tune with `PDF_OCR_LANG`, `PADDLE_OCR_LANG`, `PDF_OCR_SCALE`, and `PDF_OCR_MAX_PAGES`.
- PageIndex is attempted for long documents when `PAGEINDEX_COMMAND` is configured. Otherwise the worker creates a lightweight page tree from parsed chunks so the API contract still works.
- Vietnamese retrieval now includes Unicode normalization and diacritic-insensitive lexical fallback. See `docs/VIETNAMESE_RAG_PLAN.md`.
- Use the eye icon beside each uploaded document to review the source PDF beside parsed blocks and indexed chunks.
- API keys, uploaded files, and generated artifacts are intentionally excluded from git.

## Clear and Reinstall on Ubuntu

Use this when changing embedding dimensions, switching embedding providers, or reinstalling from a clean state.

```bash
cd /opt/rag-pageindex
sudo docker compose down -v
cd ..
sudo rm -rf /opt/rag-pageindex
git clone https://github.com/nolan7512/RAG_PageIndex.git /opt/rag-pageindex
cd /opt/rag-pageindex
chmod +x scripts/setup-ubuntu.sh
PUBLIC_HOST="your-server-ip-or-domain" ./scripts/setup-ubuntu.sh
```

The `down -v` command deletes Postgres and uploaded file Docker volumes. Back up files first if needed.
