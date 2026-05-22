import os
import logging
import asyncio
from pathlib import Path

import anthropic
import discord

from llama_index.core import VectorStoreIndex, Settings, PromptTemplate
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from router import route_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
OLLAMA_HOST = os.environ["OLLAMA_HOST"]
QDRANT_HOST = os.environ["QDRANT_HOST"]
LLM_MODEL = os.environ["LLM_MODEL"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
COLLECTION = os.environ["QDRANT_COLLECTION"]
TOP_K = int(os.environ.get("TOP_K", "5"))

DISCORD_MSG_LIMIT = 2000

AYA_DIR = "/vault/_aya"

DEFAULT_PERSONA = (
    "You are Andrea, an AI assistant embedded in a personal knowledge base.\n"
    "Answer questions strictly based on the notes retrieved from the vault.\n"
    "Be concise and direct. Use plain language. If the retrieved context does\n"
    "not contain enough information to answer confidently, say so — do not\n"
    "invent facts. Never mention Qdrant, LlamaIndex, Ollama, or any internal\n"
    "infrastructure detail. Address the user as you would a colleague."
)


def load_aya_context() -> str:
    try:
        parts = [f.read_text() for f in sorted(Path(AYA_DIR).glob("*.md"))]
        if parts:
            return "\n\n".join(parts)
    except Exception:
        log.warning("Could not read %s; using default persona", AYA_DIR)
    return DEFAULT_PERSONA


def build_query_engine():
    global retriever, _persona
    _persona = load_aya_context()

    Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=OLLAMA_HOST)
    Settings.llm = Ollama(model=LLM_MODEL, base_url=OLLAMA_HOST, request_timeout=120.0)

    client = QdrantClient(url=QDRANT_HOST)
    vector_store = QdrantVectorStore(client=client, collection_name=COLLECTION)
    index = VectorStoreIndex.from_vector_store(vector_store)
    retriever = index.as_retriever(similarity_top_k=TOP_K)

    # Obsidian notes may contain braces (e.g. Dataview queries); escape them so
    # they don't collide with PromptTemplate's str.format() substitution markers.
    safe_persona = _persona.replace("{", "{{").replace("}", "}}")
    qa_template = PromptTemplate(
        safe_persona + "\n\n"
        "Context information is below.\n"
        "---------------------\n"
        "{context_str}\n"
        "---------------------\n"
        "Given the context information and not prior knowledge, answer the query.\n"
        "Query: {query_str}\n"
        "Answer: "
    )
    return index.as_query_engine(similarity_top_k=TOP_K, text_qa_template=qa_template)


intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True

client = discord.Client(intents=intents)
query_engine = None
qdrant_client = None
retriever = None
_persona = None


async def _answer_cloud(question: str) -> str:
    nodes = await asyncio.to_thread(retriever.retrieve, question)
    context = "\n\n".join(n.get_content() for n in nodes)

    ac = anthropic.Anthropic()
    msg = await asyncio.to_thread(
        ac.messages.create,
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_persona,
        messages=[{"role": "user", "content": (
            "Context information is below.\n"
            "---------------------\n"
            f"{context}\n"
            "---------------------\n"
            "Given the context information and not prior knowledge, answer the query.\n"
            f"Query: {question}"
        )}],
    )
    answer = msg.content[0].text.strip() if msg.content else "(no answer)"

    seen = {}
    for node in nodes:
        name = node.metadata.get("file_name") if hasattr(node, "metadata") else None
        if name and name not in seen:
            seen[name] = node.score
    if seen:
        parts = [f"{name} ({score:.2f})" if score is not None else name for name, score in seen.items()]
        answer += "\n\n**Sources:** " + ", ".join(parts)

    return answer


@client.event
async def on_ready():
    log.info("Logged in as %s", client.user)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    if client.user not in message.mentions:
        return

    question = (
        message.content
        .replace(f"<@{client.user.id}>", "")
        .replace(f"<@!{client.user.id}>", "")
        .strip()
    )
    if not question:
        return

    if qdrant_client.get_collection(COLLECTION).vectors_count == 0:
        await message.reply("Still indexing the vault — try again in a moment.")
        return

    async with message.channel.typing():
        try:
            if route_query(question) == "cloud":
                log.info("Routing to cloud (Claude): %s", question[:60])
                answer = "[☁️ Claude]\n" + await _answer_cloud(question)
            else:
                response = await asyncio.to_thread(query_engine.query, question)
                answer = "[🏠 Local]\n" + (str(response).strip() or "(no answer)")

                nodes = getattr(response, "source_nodes", None) or []
                seen = {}
                for node in nodes:
                    name = node.metadata.get("file_name") if hasattr(node, "metadata") else None
                    if name and name not in seen:
                        seen[name] = node.score
                if seen:
                    parts = [f"{name} ({score:.2f})" if score is not None else name for name, score in seen.items()]
                    answer += "\n\n**Sources:** " + ", ".join(parts)
        except Exception:
            log.exception("Query failed")
            await message.reply("Something went wrong answering that.")
            return

    for i in range(0, len(answer), DISCORD_MSG_LIMIT):
        await message.reply(answer[i : i + DISCORD_MSG_LIMIT])


def main():
    global query_engine, qdrant_client
    qdrant_client = QdrantClient(url=QDRANT_HOST)
    query_engine = build_query_engine()
    client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
