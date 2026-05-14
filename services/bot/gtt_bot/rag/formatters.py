def extractive_summary(nodes: list) -> str:
    lines = []
    for i, node in enumerate(nodes, 1):
        chunk_content = node.get_content().strip()
        source = node.metadata.get("file_name", f"chunk {i}")
        stem = source.replace(".md", "")
        content_lines = chunk_content.splitlines()
        if content_lines and content_lines[0].strip() == stem:
            content_lines = content_lines[1:]
        chunk_content = "\n".join(content_lines).strip()
        first_sentence = chunk_content.split(".")[0].strip() + "."
        lines.append(f"**[{i}] {source}**\n{first_sentence}")
    return "\n\n".join(lines)


def format_raw_chunks(nodes: list) -> str:
    parts = []
    for i, node in enumerate(nodes, 1):
        source = node.metadata.get("file_name", f"chunk {i}")
        content = node.get_content().strip()
        parts.append(f"**[{i}] {source}**\n```\n{content}\n```")
    return "\n\n".join(parts)


def format_raw_chunks_plain(nodes: list) -> str:
    """Plain text version for DMs — blockquotes and inline code, renders cleanly."""
    parts = []
    for i, node in enumerate(nodes, 1):
        source = node.metadata.get("file_name", f"chunk {i}")
        chunk_content = node.get_content().strip()
        stem = source.replace(".md", "")
        lines = chunk_content.splitlines()
        if lines and lines[0].strip() == stem:
            lines = lines[1:]
        chunk_content = "\n".join(lines).strip()
        quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in chunk_content.splitlines())
        parts.append(f"**[{i}]** `{source}`\n{quoted}")
    return "\n\n---\n\n".join(parts)


def split_at_sentence(text: str, limit: int = 1950) -> list[str]:
    """Split text at sentence boundaries instead of hard cutting at limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while len(text) > limit:
        cut = text.rfind(". ", 0, limit)
        if cut == -1:
            cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        else:
            cut += 1  # include the period
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def format_sources(nodes: list) -> str:
    seen = []
    for node in nodes:
        source = node.metadata.get("file_name", "unknown")
        if source not in seen:
            seen.append(source)
    return "*Sources — " + ", ".join(seen) + "*"


def format_bootstrap_html(query: str, nodes: list) -> str:
    """Render knowledge base results as a self-contained Bootstrap 5 HTML file."""
    import html as _html

    def _card(index: int, node) -> str:
        source = node.metadata.get("file_name", f"chunk {index}")
        stem = source.replace(".md", "")
        content = node.get_content().strip()
        lines = content.splitlines()
        if lines and lines[0].strip() == stem:
            lines = lines[1:]
        content = "\n".join(lines).strip()
        score = node.score or 0.0
        escaped = _html.escape(content)
        return f"""
        <div class="card mb-4 border-0 shadow-sm chunk-card">
          <div class="card-header d-flex justify-content-between align-items-center py-2">
            <span class="badge bg-primary font-monospace fs-6">[{index}] {_html.escape(source)}</span>
            <span class="badge bg-secondary">score {score:.3f}</span>
          </div>
          <div class="card-body">
            <pre class="chunk-pre mb-0"><code>{escaped}</code></pre>
          </div>
        </div>"""

    def _summary_item(index: int, node) -> str:
        source = node.metadata.get("file_name", f"chunk {index}")
        stem = source.replace(".md", "")
        content = node.get_content().strip()
        lines = content.splitlines()
        if lines and lines[0].strip() == stem:
            lines = lines[1:]
        content = "\n".join(lines).strip()
        first = (content.split(".")[0].strip() + ".") if content else ""
        return f"""
        <div class="d-flex gap-3 mb-3 summary-item">
          <span class="badge bg-primary font-monospace align-self-start mt-1">{index}</span>
          <div>
            <div class="fw-semibold text-info mb-1">{_html.escape(source)}</div>
            <p class="mb-0 text-body-secondary">{_html.escape(first)}</p>
          </div>
        </div>"""

    summary_html = "".join(_summary_item(i, n) for i, n in enumerate(nodes, 1))
    chunks_html = "".join(_card(i, n) for i, n in enumerate(nodes, 1))
    source_list = ", ".join(n.metadata.get("file_name", "?") for n in nodes)

    return f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GTT Knowledge Base — {_html.escape(query)}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {{ background:#0d1117; }}
    .chunk-card {{ background:#161b22; border-left:3px solid #1f6feb !important; }}
    .chunk-card .card-header {{ background:#1c2128; }}
    .chunk-pre {{ background:#0d1117; border-radius:6px; padding:1rem; font-size:.85rem;
                  white-space:pre-wrap; word-break:break-word; color:#e6edf3; max-height:500px; overflow-y:auto; }}
    .summary-item {{ border-bottom:1px solid #21262d; padding-bottom:.75rem; }}
    .query-box {{ background:#161b22; border:1px solid #30363d; border-radius:8px; }}
    .section-label {{ color:#8b949e; font-size:.75rem; text-transform:uppercase; letter-spacing:.08em; }}
  </style>
</head>
<body>
<div class="container py-5" style="max-width:900px">

  <div class="d-flex align-items-center gap-3 mb-4">
    <h1 class="h4 mb-0 text-white">GTT Knowledge Base</h1>
    <span class="badge bg-secondary">{len(nodes)} sources</span>
  </div>

  <div class="query-box p-3 mb-5">
    <div class="section-label mb-1">Query</div>
    <p class="mb-1 fw-semibold text-white fs-5">{_html.escape(query)}</p>
    <small class="text-secondary font-monospace">{_html.escape(source_list)}</small>
  </div>

  <div class="mb-5">
    <div class="section-label mb-3">Summary</div>
    {summary_html}
  </div>

  <div>
    <div class="section-label mb-3">Raw Chunks</div>
    {chunks_html}
  </div>

</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""
