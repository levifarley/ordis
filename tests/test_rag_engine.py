import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from backend.rag_engine import OllamaProvider, RAGEngine, get_llm_provider
from backend.cache import SemanticCache, semantic_cache


class DummyResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def test_ollama_provider_get_embedding_success():
    provider = OllamaProvider()
    dummy_emb = [0.1] * 768
    mock_resp = DummyResponse(200, {"embedding": dummy_emb})

    with patch("httpx.Client.post", return_value=mock_resp):
        emb = provider.get_embedding("test query")
        assert len(emb) == 768
        assert emb[0] == 0.1


def test_ollama_provider_get_embedding_fallback():
    provider = OllamaProvider()
    with patch("httpx.Client.post", side_effect=Exception("Connection failed")):
        emb = provider.get_embedding("test query")
        assert len(emb) == 768
        assert emb == [0.0] * 768


def test_ollama_provider_generate_stream():
    provider = OllamaProvider()

    class MockStreamResponse:
        status_code = 200
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def iter_lines(self):
            return [
                '{"response": "Greetings, "}',
                '{"response": "Operator!"}',
                ''
            ]

    class MockClient:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def stream(self, method, url, json):
            return MockStreamResponse()

    with patch("httpx.Client", return_value=MockClient()):
        tokens = list(provider.generate_stream("Hello"))
        assert "".join(tokens) == "Greetings, Operator!"


def test_ollama_provider_host_fallback():
    provider = OllamaProvider()

    class MockStreamResponse:
        status_code = 200
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def iter_lines(self):
            return ['{"response": "Fallback success!"}', '']

    class MockClientWithFallback:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def stream(self, method, url, json):
            if "ollama:11434" in url:
                raise Exception("[Errno -2] Name or service not known")
            return MockStreamResponse()

    with patch("httpx.Client", return_value=MockClientWithFallback()):
        tokens = list(provider.generate_stream("Hello"))
        assert "".join(tokens) == "Fallback success!"


def test_semantic_cache_operations():
    cache = SemanticCache(threshold=0.9)
    cache.clear()

    v1 = [1.0, 0.0, 0.0]
    v2 = [0.99, 0.01, 0.0]  # Very high cosine similarity to v1
    v3 = [0.0, 1.0, 0.0]   # Orthogonal (dissimilar)

    # 1. Empty cache lookup
    resp, score = cache.lookup("query 1", v1)
    assert resp is None

    # 2. Add item
    cache.add("query 1", v1, "Response 1")

    # 3. Lookup high similarity query
    resp, score = cache.lookup("query 1 variant", v2)
    assert resp == "Response 1"
    assert score >= 0.9

    # 4. Lookup dissimilar query
    resp, score = cache.lookup("different query", v3)
    assert resp is None

    # 5. Clear
    cache.clear()
    resp, score = cache.lookup("query 1 variant", v2)
    assert resp is None


def test_rag_engine_cache_hit():
    semantic_cache.clear()
    engine = RAGEngine()

    query = "What is Saryn Prime?"
    dummy_emb = [0.5] * 768
    
    # Mock LLM embedding calculation
    with patch.object(engine.llm, "get_embedding", return_value=dummy_emb):
        semantic_cache.add(query, dummy_emb, "Saryn Prime is a toxic warframe, Operator.")

        stream_gen, payload = engine.generate_response_stream(query)
        assert payload["cache_hit"] is True
        assert list(stream_gen) == ["Saryn Prime is a toxic warframe, Operator."]

    semantic_cache.clear()


def test_rag_engine_cache_miss_and_stream():
    semantic_cache.clear()
    engine = RAGEngine()

    query = "How to build Ignis Wraith?"
    dummy_emb = [0.2] * 768
    mock_docs = [
        {"title": "Ignis Wraith Build", "content": "Use Multishot and Heat damage.", "market_price": "5 platinum"}
    ]

    with patch.object(engine.llm, "get_embedding", return_value=dummy_emb), \
         patch.object(engine.vector_store, "search_similar", return_value=mock_docs), \
         patch.object(engine.llm, "generate_stream", return_value=iter(["Ignis ", "Wraith ", "Build"])):

        stream_gen, payload = engine.generate_response_stream(query)
        assert payload["cache_hit"] is False
        assert len(payload["context_docs"]) == 1

        tokens = list(stream_gen)
        full_response = "".join(tokens)
        assert full_response == "Ignis Wraith Build"

        # Finalize telemetry and verify cached
        engine.finalize_telemetry(query, full_response, payload)
        
        cached_resp, sim = semantic_cache.lookup(query, dummy_emb)
        assert cached_resp == "Ignis Wraith Build"

    semantic_cache.clear()


def test_rag_engine_with_chat_history():
    semantic_cache.clear()
    engine = RAGEngine()

    query = "Where do I farm it?"
    dummy_emb = [0.1] * 768
    chat_history = [
        {"role": "user", "content": "What is Saryn Prime?"},
        {"role": "assistant", "content": "Saryn Prime is a Warframe."}
    ]

    captured_prompt = []

    def mock_generate_stream(prompt):
        captured_prompt.append(prompt)
        yield "You can farm relics."

    with patch.object(engine.llm, "get_embedding", return_value=dummy_emb), \
         patch.object(engine.vector_store, "search_similar", return_value=[]), \
         patch.object(engine.llm, "generate_stream", side_effect=mock_generate_stream):

        stream_gen, payload = engine.generate_response_stream(query, chat_history=chat_history)
        tokens = list(stream_gen)
        assert tokens == ["You can farm relics."]

        assert len(captured_prompt) == 1
        assert "<conversation_history>" in captured_prompt[0]
        assert "Operator: What is Saryn Prime?" in captured_prompt[0]

    semantic_cache.clear()


def test_hooks_execution():
    from backend.hooks import (
        register_pre_prompt_hook,
        register_post_response_hook,
        execute_pre_prompt_hooks,
        execute_post_response_hooks
    )

    # 1. Test HTML sanitization default hook
    clean_query, _ = execute_pre_prompt_hooks("<b>Hello</b> <script>alert(1)</script> Ordis", {})
    assert clean_query == "Hello alert(1) Ordis"

    # 2. Register custom pre-prompt hook
    def custom_pre_hook(query, ctx):
        return query + " [hook_modified]", ctx

    register_pre_prompt_hook(custom_pre_hook)
    mod_query, _ = execute_pre_prompt_hooks("Test query", {})
    assert "Test query [hook_modified]" in mod_query

    # 3. Register custom post-response hook
    def custom_post_hook(query, response, payload):
        return response + " [verified]", payload

    register_post_response_hook(custom_post_hook)
    mod_resp, _ = execute_post_response_hooks("Test query", "Original response", {})
    assert mod_resp == "Original response [verified]"

