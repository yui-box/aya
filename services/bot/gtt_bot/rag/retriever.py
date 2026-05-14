import logging
import re

from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

import gtt_bot.globals as G
from gtt_bot.config import OLLAMA_HOST, QDRANT_HOST, EMBED_MODEL, COLLECTION, TOP_K, MIN_SCORE, KEYWORD_WEIGHT

log = logging.getLogger("bot")

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall", "should",
    "may", "might", "must", "can", "could", "to", "of", "in", "on", "at", "by",
    "for", "with", "about", "as", "into", "through", "during", "before", "after",
    "and", "or", "but", "if", "then", "than", "so", "yet",
    "not", "no", "nor", "how", "what", "when", "where", "who", "which", "why",
    "this", "that", "these", "those", "it", "its", "me", "my", "you", "your",
    "he", "she", "we", "they", "them", "their", "our", "us",
    "tell", "explain", "give", "get", "go", "know", "think", "use", "make", "need",
})


def _significant_terms(query: str) -> list[str]:
    """Extract meaningful search terms: preserve acronyms (DIF, RLR), filter noise words."""
    terms = []
    for w in re.findall(r'\b\w+\b', query):
        if w.isupper() and len(w) >= 2:        # acronyms: DIF, RLR, LLM, AI
            terms.append(w.lower())
        elif len(w) >= 4 and w.lower() not in _STOP_WORDS:
            terms.append(w.lower())
    return list(dict.fromkeys(terms))           # deduplicate, preserve order


def _keyword_score(terms: list[str], text: str) -> float:
    if not terms:
        return 0.0
    text_lower = text.lower()
    matches = sum(1 for t in terms if re.search(r'\b' + re.escape(t) + r'\b', text_lower))
    return matches / len(terms)


def build_retriever():
    Settings.llm = None  # Prevent accidental OpenAI calls
    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_HOST)
    client = QdrantClient(url=QDRANT_HOST)
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION)
    index = VectorStoreIndex.from_vector_store(vector_store)
    # Fetch more than TOP_K so deduplication still yields TOP_K unique files
    retriever = index.as_retriever(similarity_top_k=TOP_K * 4)
    log.info("Vector retriever ready (k=%d, dedup to %d unique files)", TOP_K * 4, TOP_K)
    return retriever


def retrieve_context(question: str) -> list:
    nodes = G.retriever.retrieve(question)

    # Hybrid scoring: blend vector similarity with keyword match for exact terms
    terms = _significant_terms(question)
    vector_weight = 1.0 - KEYWORD_WEIGHT
    if terms:
        for node in nodes:
            v = node.score or 0.0
            k = _keyword_score(terms, node.get_content())
            node.score = vector_weight * v + KEYWORD_WEIGHT * k
        nodes.sort(key=lambda n: n.score or 0, reverse=True)

    # Deduplicate by source file — keep highest scoring chunk per file
    seen_files: dict = {}
    for node in nodes:
        fname = node.metadata.get("file_name", node.node_id)
        if fname not in seen_files or (node.score or 0) > (seen_files[fname].score or 0):
            seen_files[fname] = node

    results = list(seen_files.values())[:TOP_K]

    # Confidence gate — return empty if best result is below threshold
    if not results or (results[0].score or 0) < MIN_SCORE:
        log.info(
            "retrieve_context: low confidence (best=%.3f, threshold=%.3f) for %r",
            results[0].score if results else 0.0,
            MIN_SCORE,
            question[:80],
        )
        return []

    return results
