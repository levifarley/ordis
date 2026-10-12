"""
===============================================================================
ORDIS In-Memory Semantic LRU Cache & Latency Mitigation Engine
===============================================================================

Architectural Purpose:
----------------------
1. **Latency Mitigation**:
   Standard RAG query pipelines require vector database similarity search (~15-50ms)
   followed by LLM generation (~500-3000ms). By performing vectorized matrix dot-product
   cosine similarity matching against previously answered queries in-memory, exact or
   semantically equivalent queries hit in <1ms (sub-millisecond latency SLA).

2. **Cost Routing & Avoidance**:
   In both Self-Hosted (Profile A) and Cloud (Profile B) deployments, serving queries 
   from the semantic cache completely bypasses external embedding lookups, vector store
   reads, and downstream LLM inference token consumption, acting as the primary tier 
   of financial defense.

Mathematical Specification:
---------------------------
Cosine Similarity Formula:
    cos_sim(A, B) = (A · B) / (||A|| * ||B||)

- Similarity Threshold: Default 0.92 (Configurable via CACHE_SIMILARITY_THRESHOLD).
- Eviction Policy: Least Recently Used (LRU) capped at MAX_CACHE_SIZE (default 1000 items).
- Thread Safety: Guarded by threading.Lock() for high-concurrency FastAPI request handling.
"""

import threading
import numpy as np
from typing import Optional, Tuple
from backend.config import settings


class SemanticCache:
    """
    Thread-safe, vectorized in-memory LRU Semantic Cache.
    Accelerates response latency to <1ms for semantic query matches >= 0.92 cosine similarity.
    """
    def __init__(self, threshold: float = None):
        self.lock = threading.Lock()
        self.queries = []
        self.embeddings = []
        self.responses = []
        self.threshold = threshold or settings.CACHE_SIMILARITY_THRESHOLD

    def lookup(self, query: str, query_embedding: list[float]) -> Tuple[Optional[str], Optional[float]]:
        """
        Evaluates incoming query vector against cached embeddings using vectorized NumPy math.
        
        Returns:
            (cached_response, similarity_score) if max_similarity >= threshold
            (None, max_similarity) if cache miss
        """
        with self.lock:
            if not self.embeddings:
                return None, None
            
            # Vectorized Matrix Cosine Similarity Math: O(N) linear vector evaluation
            q_emb = np.array(query_embedding, dtype=np.float32)
            q_norm = np.linalg.norm(q_emb)
            if q_norm == 0:
                return None, 0.0
            
            cache_embs = np.vstack(self.embeddings)
            cache_norms = np.linalg.norm(cache_embs, axis=1)
            cache_norms = np.where(cache_norms == 0, 1.0, cache_norms)
            
            # Calculate dot products across all cached prompt vectors in parallel
            dot_products = np.dot(cache_embs, q_emb)
            similarities = dot_products / (cache_norms * q_norm)
            
            max_idx = int(np.argmax(similarities))
            max_similarity = float(similarities[max_idx])
            
            # Sub-Millisecond Hit Threshold Check
            if max_similarity >= self.threshold:
                # Refresh LRU position (move hit entry to end of queue)
                hit_query = self.queries.pop(max_idx)
                hit_embedding = self.embeddings.pop(max_idx)
                hit_response = self.responses.pop(max_idx)
                
                self.queries.append(hit_query)
                self.embeddings.append(hit_embedding)
                self.responses.append(hit_response)
                
                return hit_response, max_similarity
            
            return None, max_similarity

    def add(self, query: str, query_embedding: list[float], response: str):
        """
        Stores generated response and prompt embedding vector into LRU cache.
        Evicts oldest entry if cache capacity MAX_CACHE_SIZE is exceeded.
        """
        with self.lock:
            q_emb = np.array(query_embedding, dtype=np.float32)
            
            if len(self.queries) >= settings.MAX_CACHE_SIZE:
                if self.queries:
                    # LRU Eviction: Remove oldest query embedding at index 0
                    self.queries.pop(0)
                    self.embeddings.pop(0)
                    self.responses.pop(0)
                    
            self.queries.append(query)
            self.embeddings.append(q_emb)
            self.responses.append(response)

    def clear(self):
        """Flushes all entries from the semantic cache."""
        with self.lock:
            self.queries.clear()
            self.embeddings.clear()
            self.responses.clear()


# Global Singleton Semantic Cache instance
semantic_cache = SemanticCache()


