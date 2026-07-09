"""
exa_client.py — Exa neural search integration.

Provides search() and fetch_content() used by the ReAct agent as live
web-research tools when the local knowledge base is insufficient.
"""
from __future__ import annotations

from typing import Any, Optional

from config import EXA_API_KEY

try:
    from exa_py import Exa
    EXA_AVAILABLE = True
except ImportError:
    EXA_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
#  Client singleton
# ─────────────────────────────────────────────────────────────────────────────

_exa_client: Optional[Any] = None


def _get_client():
    global _exa_client
    if _exa_client is None and EXA_AVAILABLE and EXA_API_KEY:
        _exa_client = Exa(api_key=EXA_API_KEY)
    return _exa_client


# ─────────────────────────────────────────────────────────────────────────────
#  Public helpers
# ─────────────────────────────────────────────────────────────────────────────

def search(
    query: str,
    num_results: int = 5,
    include_domains: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """
    Neural search via Exa.  Returns a list of result dicts:
      { title, url, published_date, text_snippet }
    Falls back to mock results when not configured.
    """
    client = _get_client()
    if client is None:
        return _mock_search(query, num_results)

    kwargs: dict[str, Any] = {
        "num_results": num_results,
        "text": True,
    }
    if include_domains:
        kwargs["include_domains"] = include_domains

    try:
        response = client.search_and_contents(query, **kwargs)
        results = []
        for r in response.results:
            results.append({
                "title": getattr(r, "title", "Untitled"),
                "url": getattr(r, "url", ""),
                "published_date": getattr(r, "published_date", ""),
                "text_snippet": (getattr(r, "text", "") or "")[:800],
                "source": "WEB",
            })
        return results
    except Exception as exc:
        err_str = str(exc)
        # 401 = invalid key, silently return empty so it doesn't pollute citations
        if "401" in err_str or "403" in err_str or "Unauthorized" in err_str:
            return []
        return [{"title": f"Exa search unavailable", "url": "", "published_date": "",
                 "text_snippet": f"Web search error: {err_str[:120]}", "source": "WEB_ERROR"}]


def fetch_content(url: str, max_chars: int = 2000) -> str:
    """Fetch and return text content of a URL via Exa."""
    client = _get_client()
    if client is None:
        return f"[MOCK] Content of {url} (Exa not configured)"

    try:
        result = client.get_contents([url], text=True)
        if result.results:
            text = getattr(result.results[0], "text", "") or ""
            return text[:max_chars]
        return ""
    except Exception as exc:
        return f"[Exa fetch error] {exc}"


def is_configured() -> bool:
    return bool(EXA_API_KEY) and EXA_AVAILABLE


# ─────────────────────────────────────────────────────────────────────────────
#  Mock fallback
# ─────────────────────────────────────────────────────────────────────────────

def _mock_search(query: str, num_results: int) -> list[dict[str, Any]]:
    return [
        {
            "title": f"[MOCK] Exa result {i+1} for: {query}",
            "url": f"https://example.com/paper{i+1}",
            "published_date": "2024-01-01",
            "text_snippet": (
                f"This mock result discusses aspects of '{query}' relevant to "
                "autonomous rover navigation and SLAM algorithms. "
                "Configure EXA_API_KEY in .env for live results."
            ),
            "source": "WEB_MOCK",
        }
        for i in range(min(num_results, 3))
    ]
