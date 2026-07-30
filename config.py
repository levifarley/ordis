import os

# Google Cloud Project & Location
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "warframe-503817")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE", "(default)")
COLLECTION_NAME = "warframe_knowledge"
EXPERIMENT_NAME = "warframe-rag-evaluation"

# Models Config
EMBEDDING_MODEL = "text-embedding-004"
GENERATION_MODEL = "gemini-2.5-flash"

# Cost & Safeguard Config
CACHE_SIMILARITY_THRESHOLD = 0.92
COOLDOWN_SECONDS = 10
PROMPT_CHARACTER_LIMIT = 250
MAX_DAILY_QUERIES = 300

