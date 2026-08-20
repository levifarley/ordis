import pytest
import json
import os
from unittest.mock import patch, MagicMock
from backend.telemetry import (
    LocalJsonlTelemetry,
    GCPVertexTelemetry,
    get_telemetry_provider
)
from backend.config import settings

def test_local_jsonl_telemetry_logging(tmp_path):
    """Verify LocalJsonlTelemetry writes formatted JSON records to log file."""
    log_file = tmp_path / "test_telemetry.jsonl"
    
    with patch.object(settings, "TELEMETRY_LOG_PATH", str(log_file)):
        provider = LocalJsonlTelemetry()
        payload = {
            "latency": 0.42,
            "cache_hit": False,
            "similarity_score": 0.88,
            "context_docs": [{"title": "Doc 1"}, {"title": "Doc 2"}]
        }
        provider.log_inference(
            prompt="What is Excalibur Prime?",
            response="Excalibur Prime is a founder exclusive warframe.",
            payload=payload
        )
        
        assert os.path.exists(log_file)
        with open(log_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            record = json.loads(lines[0])
            assert record["query"] == "What is Excalibur Prime?"
            assert record["latency"] == 0.42
            assert record["cache_hit"] is False
            assert record["similarity_score"] == 0.88
            assert record["context_count"] == 2
            assert record["word_count"] == 7
            assert "timestamp" in record

def test_gcp_telemetry_disabled_by_default():
    """Verify GCPVertexTelemetry initializes without error when disabled."""
    with patch.object(settings, "ENABLE_GCP_TELEMETRY", False):
        provider = GCPVertexTelemetry()
        assert provider._initialized is False
        
        # Calling log_inference should fall back to local logging without crashing
        with patch.object(LocalJsonlTelemetry, "log_inference") as mock_local:
            provider.log_inference("query", "response", {})
            mock_local.assert_called_once()

def test_get_telemetry_provider_factory():
    """Verify telemetry factory returns appropriate provider based on settings."""
    with patch.object(settings, "ENABLE_GCP_TELEMETRY", False):
        provider = get_telemetry_provider()
        assert isinstance(provider, LocalJsonlTelemetry)
