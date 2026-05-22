# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**Aya** is a fully local Discord bot that answers questions about an Obsidian vault using RAG. It runs entirely in Docker — no external AI APIs. The vault is mounted read-only; nothing leaves the host except Discord gateway traffic.

## Running the stack

```bash
# Build and start all services (model-init pulls models automatically on first boot)
docker compose up -d --build

# Tail logs per service
docker compose logs -f indexer
docker compose logs -f bot

# Force full reindex
docker compose restart indexer

# Wipe vector store and reindex from scratch
docker compose down && docker volume rm aya_qdrant_data && docker compose up -d

# Rebuild a single service after code changes
docker compose up -d --build bot
docker compose up -d --build indexer
```

## Environment variables (`.env`)

Copy `.env.example` to `.env`. Required:
- `DISCORD_TOKEN` — bot token from Discord Developer Portal (not a webhook URL)
- `ANTHROPIC_API_KEY` - 
- `VAULT_PATH` — absolute host path to the Obsidian vault

Optional overrides with defaults:
- `LLM_MODEL` (default: `qwen2.5:7b-instruct`) — use `qwen2.5:0.5b-instruct` on CPU-only hosts
- `EMBED_MODEL` (default: `nomic-embed-text`)
- `QDRANT_COLLECTION` (default: `vault`)
- `TOP_K` (default: `5`)

## Architecture

Five Docker services share a single internal network:

```
vault (.md files, read-only mount)
       │
  [model-init] ──pull──► [ollama] ◄──generate── [bot] ◄── Discord @mentions
                              ▲                     │
  [indexer] ──embed───────────┘                     │
       │                                            │
       └──────────────► [qdrant] ◄───retrieve───────┘
```

`model-init` is a one-shot service that exits after pulling the configured models. `indexer` and `bot` only start after it completes successfully.

**Indexer** (`services/indexer/main.py`): On startup, loads all `.md` files with LlamaIndex `SimpleDirectoryReader`, chunks via `MarkdownNodeParser`, embeds via Ollama, and upserts into Qdrant. `watchdog` watches the vault for changes and triggers a debounced (3s) full reindex.

**Bot** (`services/bot/main.py`): Connects to Discord gateway via `discord.py`. On any `@mention`, embeds the question, retrieves top-K chunks from Qdrant, passes context+question to the Ollama LLM, and replies. Responses longer than 2000 chars are split across multiple messages.

## Key constraints

- **Reindex is always full** — `build_index()` rebuilds the entire collection on every change. For large vaults this is slow; incremental upsert (per-file) is a known improvement.
- **Bot initializes `query_engine` synchronously** before connecting to Discord. If Qdrant is empty (models not yet pulled), queries return empty results silently — restart the bot after the indexer finishes.
- **Mention parsing** uses raw `message.content` with stable numeric bot ID (`<@BOT_ID>` / `<@!BOT_ID>`), not display name — safe against nickname changes.
- **Pinned to LlamaIndex 0.11.x** — the API changed significantly in 0.12+; do not upgrade without testing.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available gstack skills:
/office-hours, /plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation, /design-shotgun, /design-html, /review, /ship, /land-and-deploy, /canary, /benchmark, /browse, /connect-chrome, /qa, /qa-only, /design-review, /setup-browser-cookies, /setup-deploy, /setup-gbrain, /retro, /investigate, /document-release, /document-generate, /codex, /cso, /autoplan, /plan-devex-review, /devex-review, /careful, /freeze, /guard, /unfreeze, /gstack-upgrade, /learn
