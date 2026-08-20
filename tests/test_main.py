import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.main import app
from backend.auth import create_access_token

client = TestClient(app)

def test_login_success():
    response = client.post(
        "/api/auth/token",
        data={"username": "operator", "password": "cephalon"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_failure():
    response = client.post(
        "/api/auth/token",
        data={"username": "operator", "password": "wrong_password"}
    )
    assert response.status_code == 401

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ORDIS Cephalon AI"
    assert "ollama_available" in data
    assert "chroma_available" in data
    assert "background_worker" in data

def test_chat_stream_unauthorized():
    response = client.post(
        "/api/chat/stream",
        json={"prompt": "Hello Ordis"}
    )
    assert response.status_code == 401

def test_chat_stream_authorized():
    token = create_access_token(data={"sub": "operator"})
    headers = {"Authorization": f"Bearer {token}"}
    
    with patch("backend.main.rag_engine") as mock_rag_engine:
        # Mock generate_response_stream to return list of tokens and dummy payload
        mock_rag_engine.generate_response_stream.return_value = (
            ["Operator, ", "how may ", "I assist?"],
            {"context_docs": [], "cache_hit": True, "similarity_score": 0.95, "start_time": 100.0}
        )
        
        response = client.post(
            "/api/chat/stream",
            headers=headers,
            json={"prompt": "Hello Ordis"}
        )
        assert response.status_code == 200
        assert "Operator, how may I assist?" in response.text
        mock_rag_engine.finalize_telemetry.assert_called_once()

def test_ingest_trigger():
    token = create_access_token(data={"sub": "operator"})
    headers = {"Authorization": f"Bearer {token}"}
    
    with patch("backend.main.background_worker") as mock_worker:
        mock_worker.is_ingesting = False
        response = client.post(
            "/api/ingest/trigger",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "triggered"
