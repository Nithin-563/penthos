"""Basic web retrieval layer for Penthos.

Keyless by design: every provider below is a public, API-free endpoint. The
layer tries several free search engines in order (DuckDuckGo lite and html,
Brave, Bing) and falls back to the Wikipedia open API for factual lookups,
so a single blocked provider never silently returns an empty answer.

The provider that produced each result is attached to it so the model can
cite the source honestly. A production deployment can replace these functions
with a paid search/browser provider without touching the agent code.
"""

from urllib.request import Request, urlopen
from urllib.parse import quote, unquote
import html as html_module
import json
import re


USER_AGENT = "Penthos/0.1 (+https://github.com/Nithin-563/penthos)"
MAX_RESULTS = 8


def _http_get(url: str, timeout: int = 20) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        data = response.read(2_000_000)
    return data.decode("utf-8", errors="replace")


def _clean_text(html: str) -> str:
    html = re.sub(r"<(script|style).*?>.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def _decode_href(value: str) -> str:
    if not value:
        return ""
    decoded = html_module.unescape(value)
    if "uddg=" in decoded:
        match = re.search(r"uddg=([^&\"]+)", decoded)
        if match:
            decoded = match.group(1)
    return unquote(decoded)


def _duckduckgo_lite(query: str) -> list[dict]:
    url = "https://lite.duckduckgo.com/lite/?q=" + quote(query)
    html = _http_get(url)
    results = []
    for match in re.finditer(
        r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        title = re.sub(r"<[^>]+>", "", match.group(2))
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue
        results.append({"title": title, "url": _decode_href(match.group(1))})
        if len(results) >= MAX_RESULTS:
            break
    return results


def _duckduckgo_html(query: str) -> list[dict]:
    url = "https://html.duckduckgo.com/html/?q=" + quote(query)
    html = _http_get(url)
    results = []
    for match in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        title = re.sub(r"<[^>]+>", "", match.group(2))
        title = re.sub(r"\s+", " ", title).strip()
        results.append({"title": title, "url": _decode_href(match.group(1))})
        if len(results) >= MAX_RESULTS:
            break
    return results


def _brave(query: str) -> list[dict]:
    url = "https://search.brave.com/search?q=" + quote(query)
    html = _http_get(url)
    results = []
    for match in re.finditer(
        r'<a[^>]+class="[^"]*snippet[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        title = re.sub(r"<[^>]+>", "", match.group(2))
        title = re.sub(r"\s+", " ", title).strip()
        results.append({"title": title, "url": html_module.unescape(match.group(1))})
        if len(results) >= MAX_RESULTS:
            break
    return results


def _bing(query: str) -> list[dict]:
    url = "https://www.bing.com/search?q=" + quote(query) + "&setlang=en"
    html = _http_get(url)
    results = []
    for match in re.finditer(
        r'<li class="b_algo".*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        title = re.sub(r"<[^>]+>", "", match.group(2))
        title = re.sub(r"\s+", " ", title).strip()
        results.append({"title": title, "url": html_module.unescape(match.group(1))})
        if len(results) >= MAX_RESULTS:
            break
    return results


def _wikipedia(query: str) -> list[dict]:
    search_url = (
        "https://en.wikipedia.org/w/api.php?action=opensearch&limit=5&format=json"
        "&search=" + quote(query)
    )
    data = json.loads(_http_get(search_url))
    titles = data[1] or []
    links = data[3] or []
    results = []
    for title, link in zip(titles, links):
        results.append({"title": title, "url": link})
    return results


def search_web(query: str) -> str:
    """Search the public web via free, API-less engines.

    Tries DuckDuckGo (lite then html), then Brave, then Bing, then Wikipedia.
    Each provider result is prefixed with its source; a provider that is
    blocked is skipped. Returns a readable list or an explicit notice.
    """
    attempts: list[tuple[str, list[dict]]] = []
    providers = (
        ("duckduckgo", lambda q: _duckduckgo_lite(q)),
        ("duckduckgo", lambda q: _duckduckgo_html(q)),
        ("brave", lambda q: _brave(q)),
        ("bing", lambda q: _bing(q)),
        ("wikipedia", lambda q: _wikipedia(q)),
    )

    for source, fn in providers:
        try:
            results = fn(query)
        except Exception:
            continue
        if results:
            attempts.append((source, results))
            break

    if not attempts:
        return (
            "WARNING: no free search engine returned results (some providers "
            "rate-limit headless clients). Try rephrasing, use a more specific "
            "query, or fetch a known URL with web_fetch."
        )

    source, results = attempts[0]
    lines = [f"Web search results ({source}):"]
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. {result['title']} — {result['url']}")
    return "\n".join(lines)


def fetch_url(url: str, max_bytes: int = 2_000_000) -> str:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = response.read(max_bytes)
    except Exception as exc:
        return f"WARNING: could not fetch the URL ({exc.__class__.__name__}). Try a different URL."

    raw = data.decode("utf-8", errors="replace")
    return _clean_text(raw)