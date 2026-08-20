from abc import ABC, abstractmethod
from typing import List, Dict, Any, Generator, Tuple
import logging
import time
import httpx
import json

from backend.config import settings
from backend.vector_store import get_vector_store
from backend.cache import semantic_cache
from backend.telemetry import get_telemetry_provider
from backend.hooks import execute_pre_prompt_hooks, execute_post_response_hooks

logger = logging.getLogger("ordis.rag_engine")

class BaseLLMProvider(ABC):
    @abstractmethod
    def get_embedding(self, text: str) -> List[float]:
        pass

    @abstractmethod
    def generate_stream(self, prompt: str) -> Generator[str, None, None]:
        pass


class OllamaProvider(BaseLLMProvider):
    """Local Ollama implementation for Gemma generation & local embeddings."""
    def __init__(self):
        self.host = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_MODEL
        self.embedding_model = settings.EMBEDDING_MODEL

    def get_embedding(self, text: str) -> List[float]:
        url = f"{self.host}/api/embeddings"
        payload = {"model": self.embedding_model, "prompt": text}
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    if "embedding" in data and data["embedding"]:
                        return data["embedding"]
                    elif "embeddings" in data and data["embeddings"]:
                        return data["embeddings"][0]
        except Exception as e:
            logger.error(f"Ollama embedding error: {e}")
        # Return fallback zeros if Ollama model is initializing
        return [0.0] * 768

    def generate_stream(self, prompt: str) -> Generator[str, None, None]:
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "system": settings.SYSTEM_INSTRUCTIONS,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": settings.LLM_TEMPERATURE,
                "repeat_penalty": settings.LLM_REPEAT_PENALTY,
                "repeat_last_n": settings.LLM_REPEAT_LAST_N,
                "top_p": settings.LLM_TOP_P,
                "num_predict": settings.LLM_NUM_PREDICT,
            }
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                with client.stream("POST", url, json=payload) as response:
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                yield token
        except Exception as e:
            logger.error(f"Ollama generation stream error: {e}")
            yield f"Cephalon Ordis is experiencing sub-system reconnection: {e}"


def get_llm_provider() -> BaseLLMProvider:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "ollama":
        return OllamaProvider()
    else:
        logger.warning(f"Unsupported LLM_PROVIDER '{provider}'. Defaulting to OllamaProvider.")
        return OllamaProvider()


class RAGEngine:
    """Core RAG execution engine with modular storage, hooks, and streaming."""
    def __init__(self):
        self.vector_store = get_vector_store()
        self.llm = get_llm_provider()
        self.telemetry = get_telemetry_provider()

    def generate_response_stream(self, raw_query: str, chat_history: List[Dict[str, Any]] = None) -> Tuple[Any, Dict[str, Any]]:
        start_time = time.time()
        
        # 1. Execute Pre-Prompt Hooks
        query, context_meta = execute_pre_prompt_hooks(raw_query, {"chat_history": chat_history or []})
        
        # 2. Embedding Calculation
        query_emb = self.llm.get_embedding(query)
        
        # 3. Check Semantic Cache (for non-conversational single queries)
        if not chat_history:
            cached_response, similarity = semantic_cache.lookup(query, query_emb)
            if cached_response is not None:
                logger.info(f"Semantic Cache HIT (Similarity: {similarity:.4f})")
                payload = {
                    "context_docs": [],
                    "cache_hit": True,
                    "similarity_score": similarity,
                    "latency": time.time() - start_time
                }
                return [cached_response], payload
        
        # 4. Search Vector Database (ChromaDB)
        context_docs = self.vector_store.search_similar(query_emb, limit=3)
        
        # 5. Build Grounded Context XML & Chat History
        context_parts = []
        for doc in context_docs:
            doc_str = f"<document title='{doc.get('title', 'Unknown')}'>"
            if doc.get("market_price"):
                doc_str += f"\n[Market Price Info: {doc['market_price']}]"
            doc_str += f"\n{doc['content']}\n</document>"
            context_parts.append(doc_str)
        context_str = "\n".join(context_parts) if context_parts else "No specific documents retrieved."
        
        history_str = ""
        if chat_history:
            turns = []
            for msg in chat_history[-4:]:
                role = "Operator" if msg.get("role") == "user" else "Cephalon Ordis"
                turns.append(f"{role}: {msg.get('content', '')}")
            history_str = "\n\n<conversation_history>\n" + "\n".join(turns) + "\n</conversation_history>"

        prompt = f"""Based on the following retrieved information, answer the user's question.

<context>
{context_str}
</context>{history_str}

Question: {query}
Answer:"""

        
        # 6. Stream Response Generation
        stream_gen = self.llm.generate_stream(prompt)
        
        payload = {
            "query": query,
            "context_docs": context_docs,
            "cache_hit": False,
            "similarity_score": 0.0,
            "query_emb": query_emb,
            "start_time": start_time
        }
        
        return stream_gen, payload

    def finalize_telemetry(self, query: str, response: str, payload: Dict[str, Any]):
        """Non-blocking execution of post-response hooks and telemetry dispatch."""
        latency = time.time() - payload.get("start_time", time.time())
        payload["latency"] = latency
        
        # Run Post-Response Hooks
        final_response, final_payload = execute_post_response_hooks(query, response, payload)
        
        # Save to Semantic Cache if not a cache hit
        if not final_payload.get("cache_hit", False) and final_payload.get("query_emb"):
            semantic_cache.add(query, final_payload["query_emb"], final_response)
            
        # Dispatch Telemetry
        self.telemetry.log_inference(query, final_response, final_payload)

rag_engine = RAGEngine()
