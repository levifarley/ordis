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


_ollama_last_failure_time = 0.0

class OllamaProvider(BaseLLMProvider):
    """Local Ollama implementation for Gemma generation & local embeddings."""
    def __init__(self):
        self.host = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_MODEL
        self.embedding_model = settings.EMBEDDING_MODEL

    @staticmethod
    def reset_failure_cache():
        global _ollama_last_failure_time
        _ollama_last_failure_time = 0.0

    def _get_host_candidates(self) -> List[str]:
        candidates = [self.host]
        for fallback in ["http://localhost:11434", "http://127.0.0.1:11434"]:
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def is_available(self) -> bool:
        global _ollama_last_failure_time
        if time.time() - _ollama_last_failure_time < 15.0:
            return False

        timeout = httpx.Timeout(2.0, connect=1.0)
        for host in self._get_host_candidates():
            try:
                with httpx.Client(timeout=timeout) as client:
                    res = client.get(f"{host}/api/tags")
                    if res.status_code == 200:
                        return True
            except Exception:
                continue
        _ollama_last_failure_time = time.time()
        return False

    def get_embedding(self, text: str) -> List[float]:
        global _ollama_last_failure_time
        if time.time() - _ollama_last_failure_time < 15.0:
            return [0.0] * 768

        payload = {"model": self.embedding_model, "prompt": text}
        timeout = httpx.Timeout(5.0, connect=1.0)
        for host in self._get_host_candidates():
            url = f"{host}/api/embeddings"
            try:
                with httpx.Client(timeout=timeout) as client:
                    res = client.post(url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        if "embedding" in data and data["embedding"]:
                            return data["embedding"]
                        elif "embeddings" in data and data["embeddings"]:
                            return data["embeddings"][0]
            except Exception as e:
                logger.warning(f"Ollama embedding error at {host}: {e}")

        _ollama_last_failure_time = time.time()
        return [0.0] * 768

    def generate_stream(self, prompt: str) -> Generator[str, None, None]:
        global _ollama_last_failure_time
        if time.time() - _ollama_last_failure_time < 15.0:
            yield "Cephalon Ordis sub-system offline: Ollama host unreachable. Please verify Ollama or GEMINI_API_KEY configuration."
            return

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
        last_exception = None
        timeout = httpx.Timeout(30.0, connect=2.0)
        for host in self._get_host_candidates():
            url = f"{host}/api/generate"
            try:
                with httpx.Client(timeout=timeout) as client:
                    with client.stream("POST", url, json=payload) as response:
                        status_code = getattr(response, "status_code", 200)
                        if status_code == 200:
                            has_tokens = False
                            for line in response.iter_lines():
                                if line:
                                    data = json.loads(line)
                                    token = data.get("response", "")
                                    if token:
                                        has_tokens = True
                                        yield token
                            if has_tokens:
                                return
            except Exception as e:
                logger.warning(f"Ollama generation stream error at {host}: {e}")
                last_exception = e

        _ollama_last_failure_time = time.time()
        logger.error(f"All Ollama host candidates failed. Last error: {last_exception}")
        yield f"Cephalon Ordis is experiencing sub-system reconnection: {last_exception}"


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API implementation for cloud generation & embeddings via REST."""
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.embedding_model = settings.GEMINI_EMBEDDING_MODEL

    def get_embedding(self, text: str) -> List[float]:
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is missing for Gemini embedding call.")
            return [0.0] * 768

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.embedding_model}:embedContent?key={self.api_key}"
        payload = {
            "model": f"models/{self.embedding_model}",
            "content": {"parts": [{"text": text}]}
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    values = data.get("embedding", {}).get("values", [])
                    if values:
                        return values
                else:
                    logger.error(f"Gemini embedding failed ({res.status_code}): {res.text}")
        except Exception as e:
            logger.error(f"Gemini embedding exception: {e}")
        return [0.0] * 768

    def generate_stream(self, prompt: str) -> Generator[str, None, None]:
        if not self.api_key:
            yield "Cephalon Ordis sub-system offline: GEMINI_API_KEY is not configured on server."
            return

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}&alt=sse"
        payload = {
            "system_instruction": {
                "parts": [{"text": settings.SYSTEM_INSTRUCTIONS}]
            },
            "contents": [
                {"parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "temperature": settings.LLM_TEMPERATURE
            }
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        yield f"Gemini API error ({response.status_code})"
                        return
                    for line in response.iter_lines():
                        if line and line.startswith("data: "):
                            json_str = line[6:].strip()
                            if json_str == "[DONE]":
                                break
                            try:
                                data = json.loads(json_str)
                                candidates = data.get("candidates", [])
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts", [])
                                    for p in parts:
                                        text_chunk = p.get("text", "")
                                        if text_chunk:
                                            yield text_chunk
                            except Exception:
                                continue
        except Exception as e:
            logger.error(f"Gemini streaming exception: {e}")
            yield f"Cephalon Ordis neural connection failed: {e}"


def get_llm_provider() -> BaseLLMProvider:
    from backend.billing_killswitch import billing_killswitch
    
    # Circuit breaker check: Force local Gemma if cloud circuit breaker is tripped
    if billing_killswitch.is_circuit_open():
        logger.warning("Cost circuit breaker ACTIVE: Routing request to zero-cost local OllamaProvider.")
        return OllamaProvider()

    provider = settings.LLM_PROVIDER.lower()
    if provider == "gemini":
        return GeminiProvider()
    elif provider == "ollama":
        ollama = OllamaProvider()
        if ollama.is_available():
            return ollama
        elif settings.GEMINI_API_KEY:
            logger.info("Ollama unreachable. Auto-failing over to GeminiProvider.")
            return GeminiProvider()
        return ollama
    elif settings.GEMINI_API_KEY:
        return GeminiProvider()
    else:
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
