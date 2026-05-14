import logging

from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

import gtt_bot.globals as G
from gtt_bot.config import OLLAMA_HOST, QDRANT_HOST, EMBED_MODEL, COLLECTION, TOP_K

log = logging.getLogger("bot")


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
    seen_files = {}
    for node in nodes:
        fname = node.metadata.get("file_name", node.node_id)
        if fname not in seen_files:
            seen_files[fname] = node
        elif node.score and (seen_files[fname].score or 0) < node.score:
            seen_files[fname] = node
    return list(seen_files.values())
