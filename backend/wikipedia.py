"""Copy of `wiki_speedrun/wikipedia.py` for the web UI.

The original file is left untouched. Differences from the original:
- relative hrefs ("/wiki/...", "//en.wikipedia.org/...") are resolved against
  the page URL via `urljoin` instead of being dropped;
- only article-body links (#mw-content-text / #bodyContent) are followed so
  nav/footer links don't blow up BFS branching;
- the cache consistently stores sets and returns sorted lists.
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urldefrag, urljoin, urlparse

HEADERS = {
    "User-Agent": "wiki-speedrun/1.0"
}

REJECT_NAMESPACES = [
    "File:",
    "Template:",
    "Category:",
    "Help:",
    "Wikipedia:",
    "Special:",
    "Portal:",
    "(identifier)",
    "(disambiguation)"
]


class WikipediaClient:
    """
    Responsible for communicating with Wikipedia and extracting
    links to other Wikipedia articles.
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        self.cache = dict()

    def get_page(self, base_url: str) -> str:

        try:
            response = self.session.get(
                base_url,
                timeout=self.timeout,  ## Will wait for till specified seconds.
            )

            response.raise_for_status()

            return response.text
        except:
            return False

    def clean_link(self, link):
        for keyword in REJECT_NAMESPACES:
            if keyword in link:
                return False
        return True

    def normalize_url(self, url: str) -> str:
        url, _ = urldefrag(url)
        parsed = urlparse(url)
        # Keep robust for direct calls with relative URLs.
        if not parsed.scheme or not parsed.netloc:
            return url
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def to_absolute(self, base_url: str, href: str) -> str:
        """Resolve a raw anchor href against base_url, strip fragments."""
        joined = urljoin(base_url, href)
        joined, _ = urldefrag(joined)
        parsed = urlparse(joined)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def get_all_valid_links(self, base_url):

        base_url = self.normalize_url(base_url)

        if base_url in self.cache:
            cached = self.cache[base_url]
            return list(cached) if isinstance(cached, set) else cached

        html = self.get_page(base_url=base_url)

        if html == False:
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Only follow article-body links — parsing the full page pulls in
        # nav / footer / sidebar links that blow up BFS branching.
        content = (
            soup.select_one("#mw-content-text")
            or soup.select_one("#bodyContent")
            or soup
        )

        seen_links = set()

        for anchor in content.find_all("a", href=True):
            href = anchor['href']

            if not href:
                continue

            # Resolve relative hrefs ("/wiki/...", "//en.wikipedia.org/...").
            if href.startswith("#"):
                continue
            href = self.to_absolute(base_url, href)

            if not href.startswith("https://en.wikipedia.org/wiki"):
                continue

            if not self.clean_link(link=href):
                continue

            seen_links.add(href)

        self.cache[base_url] = seen_links
        return sorted(list(seen_links))


## Test Purpose
if __name__ == "__main__":
    BASE_URL = "https://en.wikipedia.org/wiki/Potato"

    client = WikipediaClient()
    links = client.get_all_valid_links(BASE_URL)

    print(f"Found {len(links)} valid Links")
