#!/usr/bin/env bash
# Smoke test the Aya RAG stack without Discord.
# Requires: docker compose up -d with all models pulled.
# Usage: bash .claude/skills/run-aya/smoke.sh [question]
set -euo pipefail

OLLAMA="${OLLAMA:-http://localhost:11434}"
QDRANT="${QDRANT:-http://localhost:6333}"
COLLECTION="${QDRANT_COLLECTION:-awesome}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
LLM_MODEL="${LLM_MODEL:-qwen2.5:0.5b-instruct}"
QUESTION="${1:-What is in this vault?}"
TOP_K="${TOP_K:-3}"

# ── 1. Service health ─────────────────────────────────────────────────────────
echo "[1/3] Checking service health..."
docker compose ps 2>/dev/null | grep -E 'NAME|aya-'
curl -sf "$QDRANT/healthz" > /dev/null && echo "  ✓ Qdrant healthy" || { echo "  ✗ Qdrant not reachable at $QDRANT"; exit 1; }
curl -sf "$OLLAMA/api/tags" > /dev/null && echo "  ✓ Ollama healthy" || { echo "  ✗ Ollama not reachable at $OLLAMA"; exit 1; }

POINTS=$(curl -sf "$QDRANT/collections/$COLLECTION" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('points_count','?'))")
echo "  ✓ Collection '$COLLECTION': $POINTS points indexed"
[ "$POINTS" = "0" ] || [ "$POINTS" = "?" ] && { echo "  ✗ No points — run indexer first"; exit 1; } || true

# ── 2. RAG query via Python (avoids bash quoting hell with JSON) ──────────────
echo "[2/3] Running RAG query: '$QUESTION'"

python3 - "$OLLAMA" "$COLLECTION" "$EMBED_MODEL" "$LLM_MODEL" "$QUESTION" "$TOP_K" "$QDRANT" << 'PYEOF'
import sys, json, re
import urllib.request, urllib.parse

ollama, collection, embed_model, llm_model, question, top_k, qdrant = sys.argv[1:]
top_k = int(top_k)

def post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

# Embed the question
emb_resp = post(f"{ollama}/api/embeddings", {"model": embed_model, "prompt": question})
embedding = emb_resp["embedding"]
print(f"  Embedded question ({len(embedding)}-dim vector)")

# Search Qdrant
search_resp = post(f"{qdrant}/collections/{collection}/points/search",
    {"vector": embedding, "limit": top_k, "with_payload": True})

texts = []
for r in search_resp.get("result", []):
    nc = r["payload"].get("_node_content", "{}")
    m = re.search(r'"text":\s*"((?:[^"\\]|\\.)*)"', nc)
    if m:
        texts.append(m.group(1).replace("\\n", "\n").replace('\\"', '"')[:400])
    score = r["score"]

print(f"  Retrieved {len(texts)} chunks from Qdrant")
context = "\n---\n".join(texts)

# Generate answer
gen_resp = post(f"{ollama}/api/generate",
    {"model": llm_model, "prompt": f"Context:\n{context}\n\nQuestion: {question}\nAnswer:", "stream": False})
answer = gen_resp["response"].strip()

print()
print("=== Answer ===")
print(answer)
PYEOF

echo ""
echo "[3/3] ✓ Smoke test passed"
