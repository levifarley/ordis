import threading
import numpy as np
from typing import Optional, Tuple
from backend.config import settings

class SemanticCache:
    """Thread-safe, in-memory LRU Semantic Cache using NumPy cosine similarity math."""
    def __init__(self, threshold: float = None):
        self.lock = threading.Lock()
        self.queries = []
        self.embeddings = []
        self.responses = []
        self.threshold = threshold or settings.CACHE_SIMILARITY_THRESHOLD

    def lookup(self, query: str, query_embedding: list[float]) -> Tuple[Optional[str], Optional[float]]:
        with self.lock:
            if not self.embeddings:
                return None, None
            
            q_emb = np.array(query_embedding, dtype=np.float32)
            q_norm = np.linalg.norm(q_emb)
            if q_norm == 0:
                return None, 0.0
            
            cache_embs = np.vstack(self.embeddings)
            cache_norms = np.linalg.norm(cache_embs, axis=1)
            cache_norms = np.where(cache_norms == 0, 1.0, cache_norms)
            
            dot_products = np.dot(cache_embs, q_emb)
            similarities = dot_products / (cache_norms * q_norm)
            
            max_idx = int(np.argmax(similarities))
            max_similarity = float(similarities[max_idx])
            
            if max_similarity >= self.threshold:
                hit_query = self.queries.pop(max_idx)
                hit_embedding = self.embeddings.pop(max_idx)
                hit_response = self.responses.pop(max_idx)
                
                self.queries.append(hit_query)
                self.embeddings.append(hit_embedding)
                self.responses.append(hit_response)
                
                return hit_response, max_similarity
            
            return None, max_similarity

    def add(self, query: str, query_embedding: list[float], response: str):
        with self.lock:
            q_emb = np.array(query_embedding, dtype=np.float32)
            
            if len(self.queries) >= settings.MAX_CACHE_SIZE:
                if self.queries:
                    self.queries.pop(0)
                    self.embeddings.pop(0)
                    self.responses.pop(0)
                    
            self.queries.append(query)
            self.embeddings.append(q_emb)
            self.responses.append(response)

    def clear(self):
        with self.lock:
            self.queries.clear()
            self.embeddings.clear()
            self.responses.clear()

semantic_cache = SemanticCache()

