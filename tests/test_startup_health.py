import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import httpx

from backend.main import app
from backend.config import settings

client = TestClient(app)

def test_health_check_all_systems_healthy():
    """Verify health endpoint when Ollama and ChromaDB are both operational."""
    mock_ollama_resp = MagicMock()
    mock_ollama_resp.status_code = 200

    async def mock_async_get(*args, **kwargs):
        return mock_ollama_resp

    mock_vs = MagicMock()
    mock_vs.get_existing_hashes.return_value = {"doc1": "hash1"}

    with patch("httpx.AsyncClient.get", side_effect=mock_async_get), \
         patch("backend.main.get_vector_store", return_value=mock_vs):

        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == settings.APP_NAME
        assert data["llm_provider"] == settings.LLM_PROVIDER
        assert data["vector_store"] == settings.VECTOR_STORE_PROVIDER
        assert data["ollama_available"] is True
        assert data["chroma_available"] is True
        assert "background_worker" in data
        assert data["background_worker"]["is_ingesting"] is False


def test_health_check_ollama_unavailable():
    """Verify health endpoint handles Ollama connection failure gracefully."""
    async def mock_async_get_fail(*args, **kwargs):
        raise httpx.ConnectError("Ollama instance unreachable")

    mock_vs = MagicMock()
    mock_vs.get_existing_hashes.return_value = {}

    with patch("httpx.AsyncClient.get", side_effect=mock_async_get_fail), \
         patch("backend.main.get_vector_store", return_value=mock_vs):

        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ollama_available"] is False
        assert data["chroma_available"] is True


def test_health_check_chroma_unavailable():
    """Verify health endpoint handles ChromaDB store failure gracefully."""
    mock_ollama_resp = MagicMock()
    mock_ollama_resp.status_code = 200

    async def mock_async_get(*args, **kwargs):
        return mock_ollama_resp

    mock_vs = MagicMock()
    mock_vs.get_existing_hashes.side_effect = Exception("Chroma connection error")

    with patch("httpx.AsyncClient.get", side_effect=mock_async_get), \
         patch("backend.main.get_vector_store", return_value=mock_vs):

        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ollama_available"] is True
        assert data["chroma_available"] is False
