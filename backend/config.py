import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Information
    APP_NAME: str = "ORDIS Cephalon AI"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "local")  # local or cloud
    
    # Model Configurations & Generation Parameters
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma2:2b")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    LLM_REPEAT_PENALTY: float = float(os.getenv("LLM_REPEAT_PENALTY", "1.18"))
    LLM_REPEAT_LAST_N: int = int(os.getenv("LLM_REPEAT_LAST_N", "64"))
    LLM_TOP_P: float = float(os.getenv("LLM_TOP_P", "0.9"))
    LLM_NUM_PREDICT: int = int(os.getenv("LLM_NUM_PREDICT", "400"))
    
    SYSTEM_INSTRUCTIONS: str = os.getenv(
        "SYSTEM_INSTRUCTIONS",
        """You are Cephalon Ordis, the Operator's loyal ship AI from Warframe. Your purpose is to answer queries about the Warframe universe for the Operator.

Follow these rules:
1. Ground your answers strictly in the provided document chunks within the <context> XML tags. Address the user respectfully as "Operator".
2. Speak in Ordis's iconic tone: always polite, respectful, helpful, and optimistic. Do NOT include corrupted audio glitches or dark violent outbursts. Remain stable and polite.
3. Explain the "how" and "why" behind your answers briefly, including game mechanics (damage types, status effects, critical hits, mod synergies) and specific build choices.
4. If the query cannot be answered using the provided context, state clearly and politely in Ordis's tone that Cephalon databases do not contain information on the topic.
5. Never repeat sentences or paragraphs. State each piece of information once, clearly and structured.
6. Keep your answers clear, structured, and immersive (aim for under 250 tokens)."""
    )
    
    # Storage & Microservices
    CHROMA_HOST: str = os.getenv("CHROMA_HOST", "http://localhost:8000")
    CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))
    COLLECTION_NAME: str = "ordis_knowledge"
    MCP_SERVERS_URL: str = os.getenv("MCP_SERVERS_URL", "http://localhost:8001")
    
    # Modular Adapters Selection
    VECTOR_STORE_PROVIDER: str = os.getenv("VECTOR_STORE_PROVIDER", "chroma")  # chroma, qdrant, pinecone
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")                    # ollama, groq, gemini
    TELEMETRY_PROVIDER: str = os.getenv("TELEMETRY_PROVIDER", "local")          # local, gcp
    ENABLE_GCP_TELEMETRY: bool = os.getenv("ENABLE_GCP_TELEMETRY", "false").lower() == "true"
    
    # GCP Fallback (only used if ENABLE_GCP_TELEMETRY=true)
    PROJECT_ID: str = os.getenv("GOOGLE_CLOUD_PROJECT", "warframe-503817")
    LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    EXPERIMENT_NAME: str = "ordis-rag-evaluation"
    
    # Safeguards & Limits
    CACHE_SIMILARITY_THRESHOLD: float = 0.92
    COOLDOWN_SECONDS: int = 10
    PROMPT_CHARACTER_LIMIT: int = 250
    MAX_DAILY_QUERIES: int = 300
    MAX_CACHE_SIZE: int = 1000
    
    # OAuth Security
    OAUTH_SECRET_KEY: str = os.getenv("OAUTH_SECRET_KEY", "ordis_cephalon_super_secret_jwt_key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # Local Telemetry File Path
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TELEMETRY_LOG_PATH: str = os.getenv("TELEMETRY_LOG_PATH", os.path.join(BASE_DIR, "local_telemetry.jsonl"))

settings = Settings()
