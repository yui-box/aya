# GTT Bot

A local, containerized Discord bot for the [Goju Tech Talk (GTT)](https://youtube.com/@gojutechtalk) community — a space for software engineers, scientists, technology enthusiasts, and curious minds built around honest tech analysis and deep critical thinking. Answers questions grounded in an Obsidian knowledge base using RAG — local vector search for retrieval, Claude (Anthropic API) for opinionated, GTT-voiced responses.

---

## Architecture

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
║   │  Indexer service │      │  Discord bot     │      │  Ollama          │       ║
║   │  - Watches vault │◄────►│  - discord.py    │◄────►│  - nomic-embed   │       ║
║   │  - Chunks + embeds      │  - LlamaIndex    │      └──────────────────┘       ║
║   └────────┬─────────┘      └────────┬─────────┘                                ║
║            │                         │ Anthropic API (answer generation)         ║
║            ▼                         ▼                                           ║
║         ┌──────────────────────────────┐                                         ║
║         │  Qdrant (vector DB)          │                                         ║
║         │  - Persistent volume         │                                         ║
║         └──────────────────────────────┘                                         ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

### Data flow

**Indexing** (on startup + on vault file changes)
1. Indexer watches the `/vault` mount
2. Chunks markdown files respecting headers and wikilinks
3. Calls Ollama → `nomic-embed-text` embeddings
4. Stores vectors + metadata in Qdrant

**Query** (per Discord mention)
1. User mentions `@GTT Bot` in Discord
2. Bot embeds the question (Ollama, local)
3. Bot retrieves top-k chunks (Qdrant, local)
4. Bot sends context + question to Claude via Anthropic API
5. Bot posts answer back to Discord with source citations

**`/knowledge-base` query** (fully local, no API cost)
1. User runs `/knowledge-base <query>`
2. Bot embeds query and retrieves matching chunks (Ollama + Qdrant)
3. Returns summary and raw chunks directly — no LLM involved

---

## Bot commands

| Command | Description | Cost |
|---|---|---|
| `@GTT Bot <question>` | Ask a question, get a GTT-voiced answer in a thread | Anthropic API |
| `/knowledge-search <query>` | Search vault in a private thread (visible to mods) | Free (local) |
| `/knowledge-base <query>` | Search vault, results sent to your DMs only | Free (local) |
| `/thread-mode on/off` | Toggle thread replies on or off | Free (local) |
| `/status` | Show knowledge base size, uptime, config (private) | Free (local) |
| `/export` | Export a single channel to text/JSON/HTML (GTT Team only) | Free (local) |
| `/export-all` | Export all channels to disk (GTT Team only) | Free (local) |
| `/export-state` | Incremental export — only new messages since last run (GTT Team only) | Free (local) |

### Thread memory

When you `@GTT Bot` inside an existing thread, the bot reads the last 30 messages and builds conversation history. Follow-up questions are answered in context — no need to repeat yourself. This applies to both `@GTT Bot` threads and `/knowledge-search` threads.

The 30-message cap keeps token costs controlled. Long threads are still readable but only the most recent 30 messages are passed to Claude.

---

## Tech stack

| Layer | Tech | Purpose |
|---|---|---|
| **Answer generation** | Claude (Anthropic API) | GTT-voiced responses |
| **Embedding model** | nomic-embed-text (Ollama) | Vault chunk embeddings |
| **Vector DB** | Qdrant | Persistent vector store |
| **RAG pipeline** | LlamaIndex | Chunking, retrieval |
| **Discord client** | discord.py | Bot integration |
| **File watcher** | watchdog | Auto-reindex on vault change |
| **Containerization** | Docker Compose | Multi-service orchestration |

---

## Project structure

```
services/bot/
├── main.py                      # Entry point (shim — calls gtt_bot.main)
├── gtt_bot/
│   ├── main.py                  # Client setup, on_ready, on_message, bot.run()
│   ├── config.py                # All env vars, constants, SYSTEM_PROMPT
│   ├── globals.py               # Mutable runtime state (cooldowns, thread mode, retriever)
│   ├── rag/
│   │   ├── retriever.py         # build_retriever(), retrieve_context()
│   │   ├── anthropic.py         # query_anthropic()
│   │   └── formatters.py        # Chunk formatting and text splitting helpers
│   ├── discord_utils/
│   │   ├── permissions.py       # Role, channel, and guild access checks
│   │   ├── cooldown.py          # Per-user rate limiting
│   │   ├── thread_mode.py       # get/set thread mode per guild
│   │   └── thread_history.py    # Conversation history from threads
│   ├── automod/
│   │   ├── rules.py             # check_automod() — rule evaluation and timeouts
│   │   └── alerts.py            # send_mod_alert()
│   ├── export/
│   │   ├── core.py              # Channel export, attachment download, URL extraction
│   │   ├── formatters.py        # Message serialization and HTML rendering
│   │   └── state.py             # Incremental export state (load/save)
│   └── commands/
│       ├── knowledge.py         # /knowledge-base, /knowledge-search
│       ├── status.py            # /status
│       ├── thread_mode_cmd.py   # /thread-mode
│       ├── export_single.py     # /export
│       ├── export_all.py        # /export-all
│       └── export_state.py      # /export-state
services/indexer/
└── main.py                      # Vault watcher and Qdrant indexer
```

---

## Hardware requirements

- **RAM:** 16 GB minimum (32 GB recommended)
- **Disk:** ~5 GB for embedding model + vault index
- **GPU:** Optional — only used for Ollama embeddings

---

## Setup

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- A Discord bot token — [Developer Portal](https://discord.com/developers/applications) → New Application → Bot → Reset Token
  - Enable **Privileged Gateway Intents**: `MESSAGE CONTENT INTENT`
  - Invite to your server via OAuth2 URL Generator with scopes `bot` and `applications.commands`, permissions `Send Messages` + `Read Message History` + `Create Public Threads`
- An Anthropic API key — [console.anthropic.com](https://console.anthropic.com) → API Keys
- An Obsidian vault (or any folder of markdown files)

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```
DISCORD_TOKEN=your_bot_token_here
ANTHROPIC_API_KEY=your_anthropic_key_here
VAULT_PATH=/absolute/path/to/your/vault

# Lock the bot to specific servers (recommended)
ALLOWED_GUILDS=your_guild_id_here
```

To get your guild ID: enable Developer Mode in Discord (Settings → Advanced), then right-click your server name → Copy Server ID.

### 2. Start the stack

```bash
docker compose up -d --build
```

First run downloads images and builds containers. Takes a few minutes.

### 3. Pull the embedding model (one-time)

```bash
docker compose exec ollama ollama pull nomic-embed-text
```

Then restart the indexer so it can build the vault index:

```bash
docker compose restart indexer
```

### 4. Verify

```bash
# Bot connected
docker compose logs bot --tail=20
# expect: "Slash commands synced" and "Logged in as <bot-name>"

# Indexer built the vault
docker compose logs indexer --tail=20
# expect: "Index build complete"
```

### 5. Test from Discord

```
@GTT Bot what is DIF?
```

```
/knowledge-base repository lifetime reasoning
```

```
/status
```

---

## Configuration reference

All settings go in `.env`. See `.env.example` for the full list with descriptions.

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | required | Bot token from Discord Developer Portal |
| `ANTHROPIC_API_KEY` | required | API key from console.anthropic.com |
| `VAULT_PATH` | required | Absolute path to your Obsidian vault |
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model |
| `QDRANT_COLLECTION` | `vault` | Qdrant collection name |
| `TOP_K` | `5` | Number of vault chunks retrieved per query |
| `MIN_SCORE` | `0.45` | Hybrid score threshold below which the bot answers from reasoning rather than the vault |
| `KEYWORD_WEIGHT` | `0.3` | Weight of keyword matching vs vector similarity — higher boosts exact terms like DIF, RLR |
| `ALLOWED_GUILDS` | *(all)* | Comma-separated guild IDs. Empty = allow all |
| `ALLOWED_CHANNELS` | *(all)* | Comma-separated channel IDs. Empty = allow all |
| `COOLDOWN_SECONDS` | `120` | Per-user cooldown for `@mention` (Anthropic API) |
| `COOLDOWN_LOCAL_SECONDS` | `30` | Per-user cooldown for `/knowledge-base` and `/knowledge-search` |
| `MAX_QUESTION_LENGTH` | `300` | Max characters per question |
| `USE_THREADS` | `false` | Reply in threads instead of inline |
| `REQUIRED_ROLE` | *(none)* | Role name required to use `@GTT Bot`. Empty = allow all |
| `MOD_CHANNEL_ID` | *(none)* | Channel ID for automod alerts |
| `GENERAL_CHANNEL_ID` | *(none)* | Channel ID for self-promo detection |
| `SELF_PROMO_PATTERNS` | *(none)* | Comma-separated self-promo keywords (kept private in `.env`) |
| `NEW_ACCOUNT_DAYS` | `7` | Flag new accounts younger than this with no role |
| `SUSPICIOUS_MSG_LENGTH` | `200` | Message length threshold for new account flag |

### Thread mode

Set `USE_THREADS=true` in `.env` to default thread mode on for all guilds. Any member in an allowed server can also toggle it at runtime with `/thread-mode on` or `/thread-mode off` — this overrides the `.env` default for that server until the bot restarts.

---

## Knowledge base

The bot's knowledge base is an Obsidian vault of atomic notes. The indexer watches the vault folder and automatically reindexes when files change.

Notes follow a Zettelkasten structure with wikilinks (`[[note-title]]`) for connections. The bot retrieves the most relevant chunks for each question and uses them as context for the answer.

To update the knowledge base: add or edit markdown files in your vault folder. The indexer picks up changes within a few seconds. To force a full reindex:

```bash
docker compose restart indexer
```

---

## Security

- **`ALLOWED_GUILDS`** — strongly recommended. Without it, anyone who discovers your bot's Client ID can invite it to their server and use your Anthropic API key.
- **`.env`** — never commit this file. It's in `.gitignore` by default.
- **Ports** — Qdrant (6333) and Ollama (11434) are bound to `127.0.0.1` and not accessible from outside the host.
- **Rate limiting** — per-user cooldowns on both paths. Adjust `COOLDOWN_SECONDS` and `MAX_QUESTION_LENGTH` to control API cost exposure.

---

## Troubleshooting

```bash
# Check bot logs
docker compose logs bot --tail=30

# Check indexer logs
docker compose logs indexer --tail=30

# Force reindex
docker compose restart indexer

# Rebuild after editing bot code
docker compose up --build bot -d

# Wipe vector store and reindex from scratch
docker compose down
docker volume rm gtt-bot_qdrant_data
docker compose up -d --build

# Pull a different embedding model
docker compose exec ollama ollama pull <model-name>
```

If the bot doesn't respond to mentions, confirm **MESSAGE CONTENT INTENT** is enabled in the Developer Portal — without it, discord.py receives empty message content.

If `/knowledge-base` returns nothing, the indexer may not have run yet. Check its logs and restart if needed.

---

## Contributing

This is a proof-of-concept built for the GTT community. The knowledge base (vault) is separate from the bot code by design — the code is public, the knowledge base is yours to keep private or share as you choose.

To adapt this for your own community: replace the `SYSTEM_PROMPT` in `services/bot/gtt_bot/config.py` with your own worldview, drop your markdown notes into the vault, and you have a bot that reflects your community's actual knowledge and voice.
