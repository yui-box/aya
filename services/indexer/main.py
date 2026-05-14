import os
import re
import time
import logging
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("indexer")

VAULT_DIR = os.environ.get("VAULT_DIR", "/vault")
OLLAMA_HOST = os.environ["OLLAMA_HOST"]
QDRANT_HOST = os.environ["QDRANT_HOST"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
COLLECTION = os.environ["QDRANT_COLLECTION"]

DEBOUNCE_SECONDS = 3.0

FRONTMATTER_RE = re.compile(r"^\s*---[\s\S]*?---\s*$")


def is_noise_chunk(text: str) -> bool:
    """Return True for chunks that are pure YAML frontmatter or near-empty."""
    stripped = text.strip()
    if not stripped:
        return True
    if FRONTMATTER_RE.match(stripped):
        return True
    without_fm = re.sub(r"---[\s\S]*?---", "", stripped).strip()
    if len(without_fm) < 30:
        return True
    return False


def build_index():
    log.info("Building index from %s", VAULT_DIR)

    embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_HOST)
    Settings.embed_model = embed_model
    Settings.llm = None

    client = QdrantClient(url=QDRANT_HOST)

    # Wipe the collection so no stale embeddings from previous runs persist
    try:
        client.delete_collection(COLLECTION)
        log.info("Cleared existing collection %s", COLLECTION)
    except Exception:
        pass

    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    docs = SimpleDirectoryReader(
        VAULT_DIR, recursive=True, required_exts=[".md"]
    ).load_data()

    unique_files = len(set(d.metadata.get("file_path") for d in docs))
    log.info("Loaded %d markdown documents from %d files", len(docs), unique_files)

    parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    nodes = parser.get_nodes_from_documents(docs)
    clean_nodes = [n for n in nodes if not is_noise_chunk(n.get_content())]

    log.info(
        "Indexing %d/%d chunks (filtered %d noise chunks)",
        len(clean_nodes), len(nodes), len(nodes) - len(clean_nodes),
    )

    # Embed each chunk individually — pre-computing and setting node.embedding
    # ensures VectorStoreIndex uses per-chunk content, not document-level embeddings.
    texts = [n.get_content() for n in clean_nodes]
    log.info("Embedding %d chunks via %s...", len(texts), EMBED_MODEL)
    embeddings = embed_model.get_text_embedding_batch(texts, show_progress=False)
    for node, emb in zip(clean_nodes, embeddings):
        node.embedding = emb

    VectorStoreIndex(clean_nodes, storage_context=storage_context)
    log.info("Index build complete (collection=%s, chunks=%d)", COLLECTION, len(clean_nodes))


class DebouncedReindex(FileSystemEventHandler):
    def __init__(self):
        self._last_event = 0.0
        self._pending = False

    def on_any_event(self, event):
        if event.is_directory:
            return
        if not event.src_path.endswith(".md"):
            return
        self._last_event = time.time()
        self._pending = True

    def tick(self):
        if self._pending and (time.time() - self._last_event) >= DEBOUNCE_SECONDS:
            self._pending = False
            try:
                build_index()
            except Exception:
                log.exception("Reindex failed")


def main():
    Path(VAULT_DIR).mkdir(parents=True, exist_ok=True)

    while True:
        try:
            build_index()
            break
        except Exception:
            log.exception("Initial index failed; retrying in 10s")
            time.sleep(10)

    handler = DebouncedReindex()
    observer = Observer()
    observer.schedule(handler, VAULT_DIR, recursive=True)
    observer.start()
    log.info("Watching %s for changes", VAULT_DIR)

    try:
        while True:
            time.sleep(1)
            handler.tick()
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
