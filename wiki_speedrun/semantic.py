from sentence_transformers import SentenceTransformer

class SemanticRanker:
    def __init__(self):
        self.model_name = "sentence-transformers/bert-base-nli-mean-tokens"
        self.batch_size = 16
        
        self.model = SentenceTransformer(self.model_name)
        self.embedding_cache = {}
    
    def _get_title(self, url):
        title = url.split("/wiki/", 1)[-1]
        return title.replace("-", " ")
    
    def _get_embeddings(self, title):
        
        if title not in self.embedding_cache:
            embedding = self.model.encode(title, convert_to_numpy=True, normalize_embeddings=True)
            self.embedding_cache[title] = embedding
            
        return self.embedding_cache[title]
    
    def _get_similarity_score(self, candidate, target):
        candidate_emb = self._get_embeddings(candidate)
        target_emb = self._get_embeddings(target)
        return float(candidate_emb @ target_emb)
    
    def rank(self, candidates_list, target_url):
        target_title = self._get_title(target_url)
        
        ranked_candidates = []
        
        for candidate_url in candidates_list:
            candidate_title = self._get_title(candidate_url)
            
            score = self._get_similarity_score(candidate=candidate_title, target=target_title)
            
            ranked_candidates.append((candidate_url, score))
            
        ranked_candidates.sort(key=lambda item:item[1], reverse=True)
        return ranked_candidates
