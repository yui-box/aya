---
name: run-aya
description: Run, start, test, verify, smoke-test, or interact with the Aya Discord bot RAG stack. Use when asked to run the app, check if the stack is working, test a RAG query, verify indexing, or debug service health.
---

Aya runs entirely in Docker (4 services: ollama, qdrant, indexer, bot). There is no local Python environment — everything runs in containers. The smoke driver sends real embed+search+generate requests to the running services over `localhost` ports — no Discord token needed.

## Prerequisites

- Docker Desktop running
- `.env` file with `DISCORD_TOKEN` and `VAULT_PATH` set (copy from `.env.example`)
- Models pulled into Ollama (first-time only — ~670 MB total)

## Build

```bash
docker compose up -d --build
```

## First-time model pull (once per fresh Ollama volume)

```bash
docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull qwen2.5:0.5b-instruct
docker compose restart indexer  # re-run after models are available
```

## Run (agent path) — smoke test without Discord

The driver is `.claude/skills/run-aya/smoke.sh`. It embeds a question, queries Qdrant, and generates an answer using Ollama — the full RAG path, no Discord token required.

```bash
bash .claude/skills/run-aya/smoke.sh "Your question here"
```

Environment overrides (all optional — defaults match `.env.example`):

```bash
QDRANT_COLLECTION=vault EMBED_MODEL=nomic-embed-text LLM_MODEL=qwen2.5:0.5b-instruct TOP_K=5 \
  bash .claude/skills/run-aya/smoke.sh "Who is on-call this week?"
```

Expected output on a healthy stack:
```
[1/3] Checking service health...
  ✓ Qdrant healthy
  ✓ Ollama healthy
  ✓ Collection 'awesome': 9 points indexed
[2/3] Running RAG query: '...'
  Embedded question (768-dim vector)
  Retrieved 3 chunks from Qdrant

=== Answer ===
<generated answer>

[3/3] ✓ Smoke test passed
```

## Run (human path) — full stack with Discord

```bash
docker compose up -d
docker compose logs -f bot    # watch for "Logged in as ..."
```

Mention the bot in any Discord channel to query it. Not automatable headless.

## Service health

```bash
docker compose ps
curl -s http://localhost:6333/healthz        # Qdrant
curl -s http://localhost:11434/api/tags      # Ollama (lists pulled models)
curl -s http://localhost:6333/collections/test-vault  # collection stats
```

## Reindex / reset

```bash
docker compose restart indexer              # force reindex from vault
docker compose down && docker volume rm aya_qdrant_data && docker compose up -d  # wipe + reindex
```

## Gotchas

- **Healthchecks failed on fresh install** — the stock Qdrant and Ollama images lack `curl`/`wget`. Fixed in `docker-compose.yml` to use `bash -c 'echo > /dev/tcp/localhost/<port>'`. If you see "container is unhealthy" on first `docker compose up`, this is the cause.
- **Ollama must have models before indexer runs** — if models aren't pulled, indexer logs `ResponseError: model "nomic-embed-text" not found`. Pull models first, then `docker compose restart indexer`.
- **Empty vault fails indexer with `ValueError: No files found`** — the indexer retries every 10 s, but if `VAULT_PATH` is wrong or the directory has no `.md` files, it loops forever. Check `docker compose logs indexer`.
- **Bot crashes silently if Qdrant is empty** — `build_query_engine()` completes without error even if the collection is empty. Queries return empty results. Always verify `points_count > 0` via the Qdrant API before testing the bot.
- **Collection name** — the default in `.env.example` is `vault`, but this install uses `awesome`. Always check `QDRANT_COLLECTION` in `.env`.
- **LlamaIndex payload format** — Qdrant payloads store text inside a JSON-encoded `_node_content` field. Direct `curl` queries need to parse this layer; the smoke script handles it.
- **Pinned to LlamaIndex 0.11.x** — do not upgrade without testing; the API changed in 0.12+.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `container is unhealthy` on startup | `docker compose logs aya-qdrant` / `aya-ollama` — likely healthcheck failure; fixed in `docker-compose.yml` |
| `model "nomic-embed-text" not found` in indexer logs | `docker compose exec ollama ollama pull nomic-embed-text && docker compose restart indexer` |
| `ValueError: No files found in /vault` in indexer logs | Check `VAULT_PATH` in `.env` points to a directory with `.md` files |
| Smoke test returns `0 points indexed` | Indexer hasn't finished or failed; `docker compose logs indexer` |
| Bot responds `(no answer)` | Either collection empty or Qdrant/Ollama slow; check logs |
