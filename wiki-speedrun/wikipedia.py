
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://en.wikipedia.org/wiki/Potato"

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
    
    def get_page(self, base_url: str) -> str:
        """
        Download the HTML of a Wikipedia article.

        Example:
            "Python (programming language)"
        """

        response = requests.get(
            base_url,
            headers=HEADERS,
            timeout=self.timeout, ## Will wait for till specified second.
        )

        response.raise_for_status()

        return response.text

    def clean_link(self, link):
        for keyword in REJECT_NAMESPACES:
            if keyword in link:
                return False
        return True

    def get_all_valid_links(self, base_url):
        
        html = self.get_page(base_url=base_url)
        
        soup = BeautifulSoup(html, "html.parser")
        
        seen_links = set()
        
        for anchor in soup.find_all("a", href=True):
            href = anchor['href']
            
            if not href:
                continue
            
            if not href.startswith("https://en.wikipedia.org/wiki"):
                continue
        
            if not self.clean_link(link=href):
                continue
            
            if "#" in href:
                href = href.split("#")[0]
            
            seen_links.add(href)

        return list(seen_links)
        
        

if __name__ == "__main__":
    client = WikipediaClient()
    
    links = client.get_all_valid_links(BASE_URL)

    print(f"Found {len(links)} valid Links")