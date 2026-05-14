"""
Interactive retrieval rank tester.
Run inside the bot container:

    docker compose exec -it bot python rank_test.py

Type any query and see hybrid scores sorted. Ctrl+C or 'q' to quit.
"""
import os, sys
sys.path.insert(0, "/app")
os.environ.setdefault("DISCORD_TOKEN", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")

from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from gtt_bot.config import OLLAMA_HOST, QDRANT_HOST, EMBED_MODEL, COLLECTION, TOP_K, KEYWORD_WEIGHT, MIN_SCORE
from gtt_bot.rag.retriever import _significant_terms, _keyword_score

import logging
logging.disable(logging.CRITICAL)

print("Initialising retriever...", end=" ", flush=True)
Settings.llm = None
Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_HOST)
client = QdrantClient(url=QDRANT_HOST)
total = client.get_collection(COLLECTION).points_count or TOP_K * 4
retriever = VectorStoreIndex.from_vector_store(
    QdrantVectorStore(client=client, collection_name=COLLECTION)
).as_retriever(similarity_top_k=min(int(total), 500))
print(f"ready ({total} chunks)\n")

VW = 1.0 - KEYWORD_WEIGHT

while True:
    try:
        query = input("query> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        break
    if not query or query.lower() == "q":
        break

    nodes = retriever.retrieve(query)
    terms = _significant_terms(query)

    rows = sorted([
        (
            VW * (n.score or 0) + KEYWORD_WEIGHT * _keyword_score(terms, n.get_content(), n.metadata.get("file_name", "")),
            n.score or 0,
            _keyword_score(terms, n.get_content(), n.metadata.get("file_name", "")),
            n.metadata.get("file_name", "?"),
        )
        for n in nodes
    ], reverse=True)

    print(f"\n  terms   : {terms or '(none)'}")
    print(f"  nodes   : {len(nodes)}   threshold : {MIN_SCORE}   top_k : {TOP_K}")
    print()
    print(f"  {'hybrid':>7}  {'vector':>7}  {'kw':>7}  file")
    print("  " + "-" * 52)
    for i, (h, v, k, f) in enumerate(rows):
        tag = " <-- returned" if i < TOP_K and h >= MIN_SCORE else ""
        print(f"  {h:>7.3f}  {v:>7.3f}  {k:>7.3f}  {f}{tag}")
    print()
