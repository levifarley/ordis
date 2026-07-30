import threading
import numpy as np
from typing import Optional, Tuple
import config

class SemanticCache:
    def __init__(self, threshold: float = 0.92):
        self.lock = threading.Lock()
        self.queries = []       # List[str]
        self.embeddings = []    # List[np.ndarray] (each is 1D array of floats)
        self.responses = []     # List[str]
        self.threshold = threshold

    def lookup(self, query: str, query_embedding: list[float]) -> Tuple[Optional[str], Optional[float]]:
        """
        Looks up a query embedding in the semantic cache.
        Returns (cached_response, similarity_score) if a match is found with similarity >= threshold.
        Otherwise returns (None, max_similarity_score).
        """
        with self.lock:
            if not self.embeddings:
                return None, None
            
            # Convert query embedding to numpy array
            q_emb = np.array(query_embedding, dtype=np.float32)
            q_norm = np.linalg.norm(q_emb)
            if q_norm == 0:
                return None, 0.0
            
            # Stack all cached embeddings into a 2D array of shape (N, D)
            cache_embs = np.vstack(self.embeddings)
            cache_norms = np.linalg.norm(cache_embs, axis=1)
            
            # Avoid division by zero for cached embeddings
            cache_norms = np.where(cache_norms == 0, 1.0, cache_norms)
            
            # Compute cosine similarity for all cached embeddings: (A . B) / (||A|| * ||B||)
            dot_products = np.dot(cache_embs, q_emb)
            similarities = dot_products / (cache_norms * q_norm)
            
            # Find the best match
            max_idx = np.argmax(similarities)
            max_similarity = float(similarities[max_idx])
            
            if max_similarity >= self.threshold:
                return self.responses[max_idx], max_similarity
            
            return None, max_similarity

    def add(self, query: str, query_embedding: list[float], response: str):
        """
        Adds a new query, its embedding, and response to the in-memory cache.
        """
        with self.lock:
            q_emb = np.array(query_embedding, dtype=np.float32)
            self.queries.append(query)
            self.embeddings.append(q_emb)
            self.responses.append(response)

# Thread-safe global instance of semantic cache
semantic_cache = SemanticCache(threshold=config.CACHE_SIMILARITY_THRESHOLD)
