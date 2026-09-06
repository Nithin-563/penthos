"""Basic web retrieval layer.

This is intentionally isolated from the model.
A production Penthos deployment can replace these functions
with a proper search/browser provider.
"""

from urllib.request import Request, urlopen
from urllib.parse import quote
import re


USER_AGENT = "Penthos/0.1 (+https://github.com/Nithin-563/penthos)"


def fetch_url(url: str, max_bytes: int = 2_000_000) -> str:
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )

    with urlopen(request, timeout=15) as response:
        data = response.read(max_bytes)

    text = data.decode("utf-8", errors="replace")

    # Remove scripts/styles for cleaner model context.
    text = re.sub(
        r"<(script|style).*?>.*?</\1>",
        " ",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def search_web(query: str) -> str:
    """Simple DuckDuckGo HTML search adapter.

    This is a replaceable development adapter.
    """
    url = "https://html.duckduckgo.com/html/?q=" + quote(query)

    request = Request(
        url,
        headers={"User-Agent": USER_AGENT},
    )

    with urlopen(request, timeout=15) as response:
        html = response.read(2_000_000).decode(
            "utf-8",
            errors="replace",
        )

    results = []

    for match in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        link = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2))
        title = re.sub(r"\s+", " ", title).strip()

        results.append({
            "title": title,
            "url": link,
        })

        if len(results) >= 8:
            break

    return "\n".join(
        f"{i + 1}. {r['title']} — {r['url']}"
        for i, r in enumerate(results)
    )
