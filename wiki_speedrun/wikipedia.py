
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
        response = self.session.get(
            base_url,
            timeout=self.timeout, ## Will wait for till specified seconds.
        )

        response.raise_for_status()

        return response.text

    def clean_link(self, link):
        for keyword in REJECT_NAMESPACES:
            if keyword in link:
                return False
        return True

    def normalize_url(self, url: str) -> str:
        url, _ = urldefrag(url)
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def get_all_valid_links(self, base_url):
        
        base_url = self.normalize_url(base_url)

        if base_url in self.cache:
            return self.cache[base_url]

        html = self.get_page(base_url=base_url)
        
        soup = BeautifulSoup(html, "html.parser")
        
        seen_links = set()
        
        for anchor in soup.find_all("a", href=True):
            href = anchor['href']
            
            if not href:
                continue
            
            href = self.normalize_url(href)
            
            if not href.startswith("https://en.wikipedia.org/wiki"):
                continue
        
            if not self.clean_link(link=href):
                continue
            
            seen_links.add(href)

        self.cache[base_url] = seen_links
        return list(seen_links)

## Test Purpose
if __name__ == "__main__":
    BASE_URL = "https://en.wikipedia.org/wiki/Potato"
    
    client = WikipediaClient()
    links = client.get_all_valid_links(BASE_URL)
    
    print(f"Found {len(links)} valid Links")