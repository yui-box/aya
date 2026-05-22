import os

_CLOUD_KEYWORDS = frozenset({"analyze", "draft", "pros and cons"})


def route_query(question: str) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "local"
    q = question.lower()
    if any(kw in q for kw in _CLOUD_KEYWORDS) or len(question) > 200:
        return "cloud"
    return "local"
