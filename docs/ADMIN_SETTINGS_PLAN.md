# Admin Settings Plan

## Goal

Add a safe admin-only settings screen for operational RAG configuration without exposing the entire `.env` file or giving the web app Docker control.

## Phase 1 Implemented Scope

- Add admin-only backend APIs:
  - `GET /admin/settings`
  - `PUT /admin/settings`
- Use an allowlist of editable settings for LLM, embedding, reranker, OCR, PageIndex, chat/RAG, and upload limits.
- Mask secret values such as `OPENAI_API_KEY`; submitting `********` keeps the existing secret.
- Validate values by type and option list before writing.
- Write updates to `.env` via `ADMIN_SETTINGS_ENV_PATH`.
- Mount host `.env` into the API container as `/app/.env`.
- Return a restart command instead of restarting Docker from the app.
- Add an admin frontend settings screen with grouped fields and a visible restart command.

## Explicit Non-Goals

- Do not expose raw `.env` editing in the browser.
- Do not expose unsafe values such as `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ADMIN_PASSWORD`, host ports, or Docker profiles.
- Do not mount `/var/run/docker.sock` or allow the API container to restart Docker services.

## Restart Model

After saving settings, the admin runs:

```bash
sudo docker compose up -d --force-recreate api worker frontend
```

This is intentionally manual for Phase 1. A future phase may add a separate host-side restart agent with a narrow command allowlist.
