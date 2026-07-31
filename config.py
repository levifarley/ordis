import os

# Google Cloud Project & Location
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "warframe-503817")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE", "(default)")
COLLECTION_NAME = "ordis_knowledge"
EXPERIMENT_NAME = "ordis-rag-evaluation"

# Models Config
EMBEDDING_MODEL = "text-embedding-004"
GENERATION_MODEL = "gemini-2.5-flash"

# Cost & Safeguard Config
CACHE_SIMILARITY_THRESHOLD = 0.92
COOLDOWN_SECONDS = 10
PROMPT_CHARACTER_LIMIT = 250
MAX_DAILY_QUERIES = 300

# Quota & Budget Safeguards (Ingestion)
MAX_EMBEDDING_TOKENS_PER_CYCLE = 300000
MAX_MARKET_API_CALLS_PER_CYCLE = 200
MAX_WIKI_API_CALLS_PER_CYCLE = 50

# Cache Bounds
MAX_CACHE_SIZE = 1000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TELEMETRY_LOG_PATH = os.getenv("TELEMETRY_LOG_PATH", os.path.join(BASE_DIR, "local_telemetry.jsonl"))


