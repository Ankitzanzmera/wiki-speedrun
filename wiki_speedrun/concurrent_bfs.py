import os
from collections import deque ## Using Double Endedn Queue, which use doubly linked structure
from concurrent.futures import ThreadPoolExecutor, as_completed

from .wikipedia import WikipediaClient

class ConcurentBFS:
    def __init__(self, wiki_client:WikipediaClient):
        self.wiki_client = wiki_client
        self.max_workers = 4 

    def get_links_concurrently(self, urls):

        results = {}
        with ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:

            futures = {
                executor.submit(
                    self.wiki_client.get_all_valid_links,
                    url
                ): url
                for url in urls
            }

            for future in as_completed(futures):

                url = futures[future]
                try:
                    results[url] = future.result()

                except Exception as e:
                    print(f"Failed to Fetch {url}: {e}")
                    results[url] = []

        return results

    def search(self, start_url, target_url):
        
        queue = deque([start_url])
        visited = {start_url}
        
        parent = {
            start_url:None
        }
        
        while queue:
            # current_url = queue.popleft()
            urls = list(queue)
            queue.clear()
            
            results = self.get_links_concurrently(urls=urls)
            
            for current_url in urls:
            
                print(f"Visiting: {current_url}")
            
                if current_url == target_url:
                    return self.reconstruct_path(parent=parent, target_url=target_url)
                
                links = results.get(current_url, [])
            
                if links == []:
                    continue
                
                for link in links:
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