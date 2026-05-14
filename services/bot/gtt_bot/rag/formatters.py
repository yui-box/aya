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
