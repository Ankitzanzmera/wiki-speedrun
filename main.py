import time
from wiki_speedrun.bfs import BFS
from wiki_speedrun.wikipedia import WikipediaClient


START_URL = "https://en.wikipedia.org/wiki/Potato"
TARGET_URL = "https://en.wikipedia.org/wiki/Sweet_potato"


if __name__ == "__main__":
    
    bfs = BFS(wiki_client=WikipediaClient())
    
    start = time.time()
    path = bfs.search(start_url=START_URL, target_url=TARGET_URL)
    end = time.time()
    
    print(f"Time Taken to reach Target URL is {end-start} secs.")
    
    print(path)