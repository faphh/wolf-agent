"""Web tools — search and fetch web content."""

import subprocess
import logging
from typing import Any, Dict
from wolf.tools.registry import registry

logger = logging.getLogger(__name__)


def web_search_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Search the web using curl + search API."""
    query = args.get("query", "")
    num_results = args.get("num_results", 5)

    if not query:
        return {"error": "No query provided"}

    try:
        # Use DuckDuckGo HTML search as a simple fallback
        import urllib.parse
        import urllib.request
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Simple extraction of result snippets
        import re
        results = []
        snippets = re.findall(r'class="result__snippet">([^<]+)', html)
        titles = re.findall(r'class="result__a"[^>]*>([^<]+)', html)
        links = re.findall(r'class="result__url"[^>]*>([^<]+)', html)

        for i in range(min(num_results, len(snippets))):
            results.append({
                "title": titles[i].strip() if i < len(titles) else "",
                "snippet": snippets[i].strip(),
                "url": links[i].strip() if i < len(links) else "",
            })
        return {"results": results, "query": query}
    except Exception as e:
        return {"error": f"Web search failed: {str(e)}"}


def web_fetch_handler(args: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Fetch content from a URL."""
    url = args.get("url", "")
    max_length = args.get("max_length", 10000)

    if not url:
        return {"error": "No URL provided"}

    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        # Strip HTML tags for readability
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) > max_length:
            text = text[:max_length] + "\n... [truncated]"

        return {"content": text, "url": url, "truncated": len(text) > max_length}
    except Exception as e:
        return {"error": f"Fetch failed: {str(e)}"}


registry.register(
    name="web_search", toolset="web",
    schema={
        "description": "Search the web for information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results (default 5)"},
            },
            "required": ["query"],
        },
    },
    handler=web_search_handler, emoji="🔎",
)

registry.register(
    name="web_fetch", toolset="web",
    schema={
        "description": "Fetch and read content from a URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_length": {"type": "integer", "description": "Max content length (default 10000)"},
            },
            "required": ["url"],
        },
    },
    handler=web_fetch_handler, emoji="🌐",
)
