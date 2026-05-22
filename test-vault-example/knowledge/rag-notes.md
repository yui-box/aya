# RAG — Technical Notes

#knowledge #ai #rag

## What RAG is

Retrieval-Augmented Generation: instead of asking the LLM to remember everything, you give it the relevant context in the prompt at inference time. This reduces hallucinations and allows using private documents without fine-tuning.

## Key components

1. **Chunking**: splitting documents into manageable pieces. Size matters:
   - Chunks too small → lose context
   - Chunks too large → dilute the embedding signal
   - For markdown: use headers as natural chunk boundaries

2. **Embeddings**: converting text to vectors. The model matters:
   - `nomic-embed-text`: good for general text, runs locally with Ollama
   - `text-embedding-3-small` (OpenAI): more accurate but requires API
   - Typical dimension: 768 or 1536

3. **Vector store**: database that indexes vectors and enables cosine similarity search
   - Qdrant: open source, persistent, good REST API
   - Pinecone: managed, easier but has cost and privacy trade-offs
   - ChromaDB: lightweight, good for local development

4. **Retrieval**: given a query, find the K most similar chunks
   - `similarity_top_k=5` is a good starting point
   - Metadata filters can be added (date, tag, file type)

5. **Generation**: inject chunks into the LLM prompt as context

## Known limitations

- **Context window**: if chunks are too many or too long, they may not fit in the prompt
- **Semantic mismatch**: the user's query and the relevant chunk may not share vocabulary → the embedding fails to find it
- **Full vs incremental reindex**: Aya currently does a full reindex (slow on large vaults)

## LlamaIndex vs LangChain

| | LlamaIndex | LangChain |
|---|---|---|
| Specialization | RAG and document Q&A | Agents and chained workflows |
| API | Cleaner for pure RAG | More flexible but verbose |
| Docs | Good but change frequently | Many Stack Overflow examples |

Aya uses LlamaIndex. Do not upgrade to 0.12+ without reviewing breaking changes.

## Resources

- Original RAG paper (Lewis et al. 2020): search on arXiv
- LlamaIndex docs: llama-index.readthedocs.io (use version 0.11)
