# RAG + SLM Discord Bot — Architecture Plan

**Goal:** Local, containerized Discord bot that answers questions based on an Obsidian vault using RAG + a small language model.

---

## High-Level Architecture

```
┌─────────────────────┐                          ┌─────────────────────┐
│  Obsidian vault     │                          │  Discord            │
│  (markdown files)   │                          │  (bot account)      │
└──────────┬──────────┘                          └──────────┬──────────┘
           │ mounted (ro)                                   │ gateway
           ▼                                                ▼
╔══════════════════════════ Docker host (docker-compose) ══════════════════════════╗
║                                                                                  ║
║   ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐       ║
║   │  Indexer service │      │  Discord bot app │      │  Ollama          │       ║
║   │  - Watches vault │◄────►│  - discord.py    │◄────►│  - Qwen 2.5 7B   │       ║
║   │  - Chunks + embeds      │  - LlamaIndex    │      │  - nomic-embed   │       ║
║   └────────┬─────────┘      └────────┬─────────┘      └──────────────────┘       ║
║            │                         │                                           ║
║            ▼                         ▼                                           ║
║         ┌──────────────────────────────┐    ┌──────────────────────────────┐     ║
║         │  Qdrant (vector DB)          │    │  Shared volumes              │     ║
║         │  - Persistent volume         │    │  - vault mount (ro)          │     ║
║         └──────────────────────────────┘    │  - model cache, qdrant data  │     ║
║                                             └──────────────────────────────┘     ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

---

## Data Flow

### Indexing (one-time + on file changes)
1. Indexer watches `/vault` mount
2. Chunks markdown (respecting headers, wikilinks)
3. Calls Ollama → embeddings
4. Stores vectors + metadata in Qdrant

### Query (per Discord message)
1. User mentions bot in Discord
2. Bot receives event via Discord gateway
3. Bot embeds question (Ollama)
4. Bot retrieves top-k chunks (Qdrant)
5. Bot builds prompt + context, calls Ollama SLM
6. Bot posts answer back to Discord

---

## Tech Stack

| Layer | Tech | Purpose |
|---|---|---|
| **SLM runtime** | Ollama | Serves Qwen 2.5 7B + nomic-embed-text |
| **LLM model** | Qwen 2.5 7B Instruct | Answer generation |
| **Embedding model** | nomic-embed-text | Markdown-friendly vectors |
| **Vector DB** | Qdrant | Persistent vector store |
| **Orchestration** | LlamaIndex | RAG pipeline, chunking, retrieval |
| **Discord client** | discord.py | Official bot integration |
| **File watcher** | watchdog (Python) | Auto-reindex on vault change |
| **Language** | Python 3.11+ | Indexer + bot |
| **Containerization** | Docker Compose | Multi-service orchestration |
| **GPU passthrough** | NVIDIA Container Toolkit | If GPU available |

---

## Container Layout

### 4 services in `docker-compose.yml`

1. **`ollama`** — official `ollama/ollama` image, GPU-enabled, exposes port 11434
2. **`qdrant`** — official `qdrant/qdrant` image, exposes port 6333, persistent volume
3. **`indexer`** — custom Python image, mounts vault read-only, runs file watcher
4. **`bot`** — custom Python image, holds Discord token via env var

### Volumes
- `./vault` → `/vault` (read-only, both indexer and bot)
- `ollama_data` → model cache
- `qdrant_data` → vector store persistence

### Network
- Single internal Docker network
- Only `bot` needs outbound to Discord
- Nothing inbound from outside

---

## Hardware Requirements

- **GPU:** 8–12 GB VRAM (NVIDIA recommended for Ollama GPU support)
- **RAM:** 16 GB minimum
- **Disk:** ~10 GB for models + vault size

---

## Discord Setup Notes

- Use **official Discord Bot account** (not self-bot with username/password)
- Self-bots violate Discord ToS and risk account ban
- Bot uses a token from the Discord Developer Portal
- Invite bot to your server with `MESSAGE_CONTENT` and `GUILD_MESSAGES` intents

---

## Next Steps

1. Confirm hardware specs (GPU/RAM)
2. Create Discord bot account, obtain token
3. Scaffold `docker-compose.yml` and service Dockerfiles
4. Implement indexer (file watcher + chunking + embedding)
5. Implement bot (Discord event handler + RAG query pipeline)
6. Test with sample vault before pointing at real Obsidian data
