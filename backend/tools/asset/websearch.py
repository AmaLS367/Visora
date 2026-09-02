"""Web search fallback for finding real Sketchfab asset pages.

Sketchfab's own public search API (`SketchfabProvider.search` in providers.py) ignores its `q`
parameter - verified live with a real SKETCHFAB_API_TOKEN: a nonsense query string and a real
search term return the identical result set, both with and without the Authorization header. This
is a platform-level limitation of the public /v3/models endpoint, not something a different
request shape can fix. For a specific/niche model (e.g. a particular game character), the search
tool is therefore useless, but resolving a model directly by its UID
(`download_and_import_asset(asset_id="sketchfab:<uid>")`) works fine.

This module closes that gap with a real, general-purpose web search: SearXNG (a keyless, public
metasearch aggregator - no API key, no rate-limited account) queries real engines for
"site:sketchfab.com/3d-models <query>", and we pull the model UID straight out of the matching
result URLs. If every configured SearXNG instance fails, we fall back to scraping DuckDuckGo's
HTML-only search page, which needs no key either.

Verified live (2026-09-02, real network calls, real query): every default public SearXNG instance
failed - one served an HTML bot-check page instead of JSON, one rate-limited with 429, one had a
broken TLS certificate - which matches SearXNG's own documented default posture (operators are
encouraged to disable/throttle the JSON API for anonymous callers to stop exactly this kind of
scraping). The DuckDuckGo HTML fallback carried the entire result and correctly found the real
model. So in practice, with the public instance list, DuckDuckGo is the backbone and SearXNG is a
bonus that activates for instances that happen to allow it (most reliably a self-hosted one - see
SEARXNG_INSTANCE_URLS in .env.example). This isn't a bug to fix here: both paths are already tried
and failures are reported as non-fatal warnings, not errors.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

import httpx

from backend.config import get_settings
from backend.schemas.asset import AssetSearchResultItem

logger = logging.getLogger("backend.tools.asset.websearch")

# Sketchfab model page URLs look like:
#   https://sketchfab.com/3d-models/<url-slug>-<32-hex-char-uid>
# The uid is exactly what SketchfabProvider.resolve_download_url() and
# download_and_import_asset(asset_id=...) need.
_SKETCHFAB_UID_RE = re.compile(r"sketchfab\.com/3d-models/[a-z0-9-]*-([0-9a-f]{32})\b", re.IGNORECASE)
_DDG_RESULT_HREF_RE = re.compile(r'class="result__a"[^>]*href="([^"]+)"')

_USER_AGENT = "Mozilla/5.0 (Visora-MCP asset web-search fallback)"


async def _searxng_search(query: str, instance_url: str, timeout: float) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.get(
            f"{instance_url.rstrip('/')}/search",
            params={"q": query, "format": "json"},
            headers={"User-Agent": _USER_AGENT},
        )
        res.raise_for_status()
        data: dict[str, Any] = res.json()
    results = data.get("results", [])
    return results if isinstance(results, list) else []


async def _duckduckgo_search(query: str, timeout: float) -> list[dict[str, Any]]:
    # DuckDuckGo has no free JSON search API; html.duckduckgo.com is its keyless HTML-only search
    # page (built for JS-disabled browsers), so result links can be pulled out with a regex. This
    # is best-effort scraping - DDG can change its markup without notice - used only after every
    # SearXNG instance above has already failed.
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        res = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": _USER_AGENT},
        )
        res.raise_for_status()
        html = res.text

    results: list[dict[str, Any]] = []
    for match in _DDG_RESULT_HREF_RE.finditer(html):
        href = match.group(1)
        # DDG wraps outbound result links through its own redirector: /l/?uddg=<url-encoded-target>
        parsed = urllib.parse.urlparse(href)
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [href])[0]
        results.append({"url": urllib.parse.unquote(target)})
    return results


async def find_sketchfab_models_via_web_search(
    query: str, limit: int = 5
) -> tuple[list[AssetSearchResultItem], list[str]]:
    """Find real Sketchfab model page URLs for `query` and turn them into resolvable asset IDs."""
    settings = get_settings()
    warnings: list[str] = []
    full_query = f"site:sketchfab.com/3d-models {query}"

    raw_results: list[dict[str, Any]] = []
    for instance in settings.searxng_instance_urls:
        try:
            raw_results = await _searxng_search(full_query, instance, settings.web_search_timeout_seconds)
            if raw_results:
                break
        except Exception as exc:
            logger.warning(f"SearXNG instance {instance} failed: {exc}")
            warnings.append(f"SearXNG instance {instance} failed: {exc}")

    if not raw_results:
        try:
            raw_results = await _duckduckgo_search(full_query, settings.web_search_timeout_seconds)
        except Exception as exc:
            logger.warning(f"DuckDuckGo fallback search failed: {exc}")
            warnings.append(f"DuckDuckGo fallback search failed: {exc}")

    items: list[AssetSearchResultItem] = []
    seen_uids: set[str] = set()
    for result in raw_results:
        url = result.get("url") or ""
        match = _SKETCHFAB_UID_RE.search(url)
        if not match:
            continue
        uid = match.group(1).lower()
        if uid in seen_uids:
            continue
        seen_uids.add(uid)
        title = result.get("title") or url
        items.append(
            AssetSearchResultItem(
                id=f"sketchfab:{uid}",
                name=title,
                source="sketchfab",
                category="model",
                description=f"Found via web search, not Sketchfab's own (unreliable) search API: {url}",
                download_url=None,
                details={"uid": uid, "page_url": url, "found_via": "web_search"},
            )
        )
        if len(items) >= limit:
            break

    if not items:
        warnings.append(
            f"Web search found no Sketchfab model pages for query: {query!r}. Try different "
            "keywords, or find the model on sketchfab.com yourself and pass its UID as asset_id."
        )
    return items, warnings
