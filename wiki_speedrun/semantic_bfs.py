from collections import deque ## Using Double Endedn Queue, which use doubly linked structure
from .wikipedia import WikipediaClient
from .semantic import SemanticRanker

class SemanticBFS:
    def __init__(self, wiki_client:WikipediaClient, ranker:SemanticRanker):
        self.wiki_client = wiki_client
        self.ranker = ranker

    def search(self, start_url, target_url):
        queue = deque([start_url])
        visited = {start_url}
        
        parent = {
            start_url:None
        }
        
        while queue:
            current_url = queue.popleft()
            print(f"Visiting: {current_url}")

            if current_url == target_url:
                return self.reconstruct_path(parent=parent, target_url=target_url)
            
            links = self.wiki_client.get_all_valid_links(base_url=current_url)
            
            if links == []:
                continue
            
            candidates = [link for link in links if link not in visited]
            
            ranked_candidates = self.ranker.rank(candidates_list=candidates, target_url=target_url)
            
            for link, _ in ranked_candidates:
                
                if link in visited:
                    continue
                
                visited.add(link)
                parent[link] = current_url
                
                if link == target_url:
                    return self.reconstruct_path(parent=parent, target_url=target_url)
                
                queue.append(link)
            
        return None

    @staticmethod
    def reconstruct_path(parent, target_url):
        path = []
        current = target_url

        while current is not None:

            path.append(current)

            current = parent[current]

        # We constructed target -> start, so reverse it.
        path.reverse()

        return path