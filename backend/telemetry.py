from abc import ABC, abstractmethod
from typing import Dict, Any
import json
import logging
from datetime import datetime, timezone
from backend.config import settings

logger = logging.getLogger("ordis.telemetry")

class BaseTelemetryProvider(ABC):
    @abstractmethod
    def log_inference(self, prompt: str, response: str, payload: Dict[str, Any]):
        pass


class LocalJsonlTelemetry(BaseTelemetryProvider):
    """Local JSONL file logger requiring zero remote cloud configuration."""
    def log_inference(self, prompt: str, response: str, payload: Dict[str, Any]):
        try:
            latency = payload.get("latency", 0.0)
            cache_hit = payload.get("cache_hit", False)
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "query": prompt,
                "response": response,
                "latency": latency,
                "cache_hit": cache_hit,
                "similarity_score": payload.get("similarity_score"),
                "context_count": len(payload.get("context_docs", [])),
                "word_count": len(response.split())
            }
            with open(settings.TELEMETRY_LOG_PATH, "a") as f:
                f.write(json.dumps(record) + "\n")
            logger.info(f"Logged local telemetry record to {settings.TELEMETRY_LOG_PATH}")
        except Exception as e:
            logger.error(f"Local telemetry log error: {e}")


class GCPVertexTelemetry(BaseTelemetryProvider):
    """Optional Vertex AI Experiments telemetry logger."""
    def __init__(self):
        self._initialized = False
        if settings.ENABLE_GCP_TELEMETRY:
            try:
                from google.cloud import aiplatform
                aiplatform.init(
                    project=settings.PROJECT_ID,
                    location=settings.LOCATION,
                    experiment=settings.EXPERIMENT_NAME
                )
                self._initialized = True
                logger.info("Vertex AI Experiments telemetry initialized.")
            except Exception as e:
                logger.warning(f"Could not initialize Vertex AI Experiments: {e}")

    def log_inference(self, prompt: str, response: str, payload: Dict[str, Any]):
        # Always log to local JSONL first
        LocalJsonlTelemetry().log_inference(prompt, response, payload)
        
        if not self._initialized:
            return
            
        try:
            import uuid
            from google.cloud import aiplatform
            run_id = f"rag-run-{uuid.uuid4().hex[:8]}"
            with aiplatform.start_run(run_id):
                aiplatform.log_params({
                    "query": prompt[:100],
                    "cache_hit": str(payload.get("cache_hit", False)),
                    "llm_provider": settings.LLM_PROVIDER,
                    "model": settings.OLLAMA_MODEL
                })
                aiplatform.log_metrics({
                    "word_count": float(len(response.split())),
                    "latency": float(payload.get("latency", 0.0))
                })
        except Exception as e:
            logger.error(f"GCP Vertex AI telemetry dispatch error: {e}")


def get_telemetry_provider() -> BaseTelemetryProvider:
    if settings.ENABLE_GCP_TELEMETRY and settings.TELEMETRY_PROVIDER == "gcp":
        return GCPVertexTelemetry()
    return LocalJsonlTelemetry()
