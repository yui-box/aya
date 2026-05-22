# LLMs — Quick Reference

#knowledge #ai #llms

## Models I use / know

### Local (Ollama)
| Model | Size | Use case |
|---|---|---|
| qwen2.5:0.5b-instruct | ~400 MB | CPU-only, fast and simple responses |
| qwen2.5:7b-instruct | ~4.5 GB | Better quality, requires GPU or patience |
| nomic-embed-text | ~270 MB | Embeddings only, does not generate text |
| llama3.2:3b | ~2 GB | Balanced alternative |

### API (cloud)
| Model | Use case |
|---|---|
| claude-sonnet-4-6 | Complex analysis, long-form writing, reasoning |
| claude-haiku-4-5 | Fast API tasks, low cost |
| gpt-4o | Fallback if Anthropic is unavailable |

## When to use local vs cloud

**Local whenever:**
- Content is private (emails, client data, family)
- Task is simple (vault Q&A, short summaries)
- Low latency is needed

**Cloud when:**
- Task requires deep reasoning (architecture review, multi-perspective analysis)
- Context is long (large documents)
- Best possible quality is needed and privacy is not a blocker

## Parameters that matter

- **Temperature**: 0.0–0.3 for factual tasks; 0.7–1.0 for brainstorming
- **request_timeout**: on local Ollama, increase to 120s+ for larger models
- **Top-K (RAG)**: how many chunks to retrieve. 5 is a good default.

## Personal observations

- Qwen 2.5 0.5B is surprisingly capable for its size when the context is clear
- Claude is the best option for drafting things that sound like me — it "gets the tone" better
- Local models hallucinate more when the vault context does not cover the question
