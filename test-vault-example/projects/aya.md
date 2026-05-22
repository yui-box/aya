# Project Aya

#project #ai #aya

## What it is

Aya is my personal AI assistant — a digital twin that centralizes emails, meetings, Obsidian notes, and family reminders. It runs 100% locally in Docker for privacy.

## Stack

- **Local LLM**: Ollama + Qwen 2.5 (CPU-friendly: 0.5B instruct)
- **Embeddings**: nomic-embed-text
- **Vector DB**: Qdrant
- **RAG orchestration**: LlamaIndex 0.11.x
- **Interface**: Discord bot (discord.py)
- **Cloud LLM** (complex tasks): Claude API (claude-sonnet-4-6)
- **Containers**: Docker Compose (4 services)

## Current status

- [x] Full Docker stack running
- [x] Indexer with watchdog and debounce
- [x] Bot responds to @mentions with RAG
- [ ] Auto-pull models on startup (AYA-1)
- [ ] Graceful reply when Qdrant is empty (AYA-2)
- [ ] Show source notes in responses (AYA-3)
- [ ] Fix mention parsing (AYA-4)
- [ ] Aya persona layer (AYA-7)
- [ ] Morning briefing (AYA-12)
- [ ] Email integration (AYA-10)

## Design decisions

- **Full reindex**: for now, every vault change triggers a full reindex. Slow on large vaults but simple.
- **Privacy first**: the local SLM handles all personal data. Claude API only receives sanitized context for complex analysis.
- **Obsidian as the brain**: the `_aya/` folder holds high-priority context that is always injected into the prompt.

## Repo

GitHub: aya (private)
Collaborators: Andrea + "Vibe & Wine" co-builder

## Next session

Implement AYA-7 (persona layer) and test the full vault with the bot.
