"""Lightweight web search client using DuckDuckGo HTML search.

No API key required. Returns a list of {title, url, snippet} dicts.
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LocalLLMChat/1.0)",
}


def _extract_text(html: str) -> str:
    """Strip HTML tags and decode entities (minimal)."""
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#x27;", "'").replace("&nbsp;", " ")
    return text.strip()


async def search_web(query: str, top_k: int = 5) -> list[dict]:
    """Search the web via DuckDuckGo HTML and return top_k results.

    Returns:
        [{"title": str, "url": str, "snippet": str}, ...]
    """
    url = "https://html.duckduckgo.com/html/"
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.post(url, data={"q": query})
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return []

    html = resp.text
    results: list[dict] = []

    # DuckDuckGo HTML returns results in <a class="result__a"> with
    # snippets in <a class="result__snippet">
    # Parse with regex (no lxml dependency needed)
    blocks = re.findall(
        r'<div class="result results_links results_links_deep[^"]*">(.*?)</div>\s*</div>',
        html,
        re.DOTALL,
    )

    for block in blocks[:top_k]:
        # Title + URL
        title_match = re.search(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            block,
            re.DOTALL,
        )
        if not title_match:
            continue

        raw_url = title_match.group(1)
        title = _extract_text(title_match.group(2))

        # DuckDuckGo wraps URLs through a redirect; extract the real URL
        real_url_match = re.search(r"uddg=([^&]+)", raw_url)
        if real_url_match:
            from urllib.parse import unquote

            final_url = unquote(real_url_match.group(1))
        else:
            final_url = raw_url

        # Snippet
        snippet_match = re.search(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            block,
            re.DOTALL,
        )
        snippet = _extract_text(snippet_match.group(1)) if snippet_match else ""

        if title and final_url:
            results.append({"title": title, "url": final_url, "snippet": snippet})

    return results
