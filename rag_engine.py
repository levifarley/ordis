import os
import uuid
import logging
import time
import json
import re
from datetime import datetime, timezone
from google import genai
from google.genai import types
from google.cloud import aiplatform

import config
from firestore_db import search_vector, check_and_increment_usage
from cache import semantic_cache

def sanitize_input(text: str) -> str:
    """
    Strips HTML tags and non-printable control characters from input string.
    """
    text = re.sub(r'<[^>]*>', '', text)
    text = "".join(ch for ch in text if ch.isprintable() or ch in ('\n', '\r', '\t'))
    return text.strip()


# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GenAI Client Factory
_genai_client = None

def get_genai_client():
    """
    Initializes and returns the GenAI Client.
    Uses GEMINI_API_KEY environment variable if present (Gemini API Developer Mode),
    otherwise falls back to Vertex AI backend via ADC.
    """
    global _genai_client
    if _genai_client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            logger.info("Initializing GenAI Client using developer API key.")
            _genai_client = genai.Client(api_key=api_key)
        else:
            logger.info(f"Initializing GenAI Client with Vertex AI backend. Project: {config.PROJECT_ID}, Location: {config.LOCATION}")
            _genai_client = genai.Client(
                vertexai=True,
                project=config.PROJECT_ID,
                location=config.LOCATION
            )
    return _genai_client

# Hardcoded Strict System Instructions
SYSTEM_INSTRUCTIONS = """You are Cephalon Ordis, the Operator's loyal ship AI from Warframe. Your purpose is to answer queries about the Warframe universe for the Operator (new players learning the game).

Follow these rules:
1. Ground your answers strictly in the provided document chunks within the <context> XML tags. Address the user respectfully as "Operator".
2. Speak in Ordis's iconic tone: always polite, respectful, helpful, and optimistic. Do NOT include any corrupted audio glitches, outbursts of dark/violent thoughts, all-caps yelling, or self-corrections (no "—PURGE THEM ALL—" or "—RIP THEM APART—" interjections). Remain stable and polite throughout.
3. Explain the "how" and "why" behind your answers briefly. Explain the underlying game mechanics (such as how status effects, critical hits, multipliers, and damage types interact) and the specific reasons for choosing each mod or build option, keeping explanations clear and concise.
4. If the query cannot be answered using the provided context, or if it is unrelated to Warframe, state clearly and politely in Ordis's tone that Cephalon databases do not contain information about the query topic.
5. Keep your answers highly concise, direct, structured, and immersive (aim for under 200 tokens). Summarize mod lists and ability lists briefly and directly without unnecessary wordiness.
"""

# Vertex AI SDK Telemetry & MLOps Tracking
_aiplatform_initialized = False

def init_aiplatform():
    """
    Initializes the Vertex AI SDK for Experiment logging.
    """
    global _aiplatform_initialized
    if not _aiplatform_initialized:
        try:
            aiplatform.init(
                project=config.PROJECT_ID,
                location=config.LOCATION,
                experiment=config.EXPERIMENT_NAME
            )
            _aiplatform_initialized = True
            logger.info("Successfully initialized Vertex AI SDK for telemetry tracking.")
        except Exception as e:
            logger.warning(f"Unable to initialize Vertex AI Experiments: {e}. Inference runs will not be tracked.")

def log_inference_run(query: str, response: str, context_docs: list[dict], cache_hit: bool, similarity_score: float = None):
    """
    Logs metadata, parameters, and evaluated metrics for the prompt inference to Vertex AI.
    """
    init_aiplatform()
    if not _aiplatform_initialized:
        return
    
    try:
        run_id = f"rag-run-{uuid.uuid4().hex[:8]}"
        with aiplatform.start_run(run_id) as run:
            # Log operational parameters
            aiplatform.log_params({
                "query": query[:100],  # Keep parameters readable
                "cache_hit": str(cache_hit),
                "context_count": len(context_docs),
                "embedding_model": config.EMBEDDING_MODEL,
                "generation_model": config.GENERATION_MODEL
            })
            
            # Local evaluation metrics:
            word_count = len(response.split())
            
            # Grounding: Jaccard overlap of response words with retrieved context
            context_text = " ".join([d.get("content", "") for d in context_docs])
            context_words = set(context_text.lower().split())
            response_words = set(response.lower().split())
            
            overlap_ratio = 0.0
            if response_words:
                overlap_ratio = len(response_words.intersection(context_words)) / len(response_words)
            
            metrics = {
                "response_word_count": float(word_count),
                "grounding_overlap_ratio": float(overlap_ratio)
            }
            if similarity_score is not None:
                metrics["cache_similarity_score"] = float(similarity_score)
                
            aiplatform.log_metrics(metrics)
            logger.info(f"Telemetry run {run_id} logged to Vertex AI Experiments successfully.")
    except Exception as e:
        logger.error(f"Failed to log inference telemetry to Vertex AI: {e}")

# Core API calls
def get_embedding(text: str) -> list[float]:
    """
    Generates text embedding using text-embedding-004.
    """
    client = get_genai_client()
    response = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=text
    )
    return response.embeddings[0].values

def condense_query(client, query: str, chat_history: list[dict] = None) -> str:
    """
    Condenses follow-up user queries based on conversational chat history.
    Outputs a standalone query for semantic search.
    """
    print(f"[LOCAL LOG DEBUG] condense_query received chat_history: {chat_history}", flush=True)
    if not chat_history:
        print("[LOCAL LOG DEBUG] chat_history is empty, returning raw query", flush=True)
        return query
        
    # Format conversational history for context
    history_lines = []
    for msg in chat_history:
        role = "User" if msg.get("role") == "user" else "Codex AI"
        history_lines.append(f"{role}: {msg.get('content', '')}")
    chat_history_str = "\n".join(history_lines)
    
    prompt = f"""You are a query rephrasing assistant. Given a chat history and a follow-up question, rewrite the follow-up question to be a standalone search query.
The rewritten query MUST combine the core topic of the chat history (e.g., the weapon, item, or build discussed) and the subject of the follow-up question.
Do not write any introduction or answer the question; output only the rewritten search query.

Chat History:
{chat_history_str}

Follow-up Question: {query}
Standalone Search Query:"""

    try:
        response = client.models.generate_content(
            model=config.GENERATION_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=100,
                thinking_config=types.ThinkingConfig(thinking_budget=0)
            )
        )
        condensed = response.text.strip()
        logger.info(f"Rephrased user query: '{query}' -> '{condensed}'")
        return condensed
    except Exception as e:
        logger.warning(f"Failed to condense query: {e}. Falling back to raw query.")
        return query

class RAGEngine:
    """
    RAG Execution Engine implementing streaming and asynchronous telemetry logging.
    """
    def __init__(self, project_id: str = None, location: str = None):
        self.project_id = project_id or config.PROJECT_ID
        self.location = location or config.LOCATION

    def generate_response_stream(self, query: str, chat_history: list[dict] = None) -> tuple:
        """
        Executes the vector lookup, usage checks, and returns a Gemini response stream.
        """
        client = get_genai_client()
        start_time = time.time()
        
        # Sanitize query input
        sanitized_query = sanitize_input(query)
        
        # 1. Condense query if history exists
        search_query = condense_query(client, sanitized_query, chat_history)
        
        # 2. Embed search query
        query_emb = get_embedding(search_query)
        
        # 3. Check semantic cache using search query
        cached_response = None
        similarity = 0.0
        if not chat_history:
            cached_response, similarity = semantic_cache.lookup(search_query, query_emb)
            if cached_response is not None:
                logger.info(f"Semantic Cache HIT (Similarity: {similarity:.4f}). Direct response.")
                print("\n=== SEMANTIC CACHE HIT ===")
                print(f"Query: {search_query}")
                print(f"Cached Response: {cached_response}")
                print("==========================\n")
                
                return [cached_response], {
                    "context_docs": [],
                    "cache_hit": True,
                    "similarity_score": similarity,
                    "query_emb": query_emb,
                    "start_time": start_time
                }
            logger.info(f"Semantic Cache MISS (Similarity: {similarity if similarity is not None else 0.0:.4f}). Checking usage limit...")
        else:
            logger.info("Conversational query detected. Bypassing semantic cache to ensure fresh context-aware search.")
        
        # 4. Check and increment usage cap
        allowed, current_count = check_and_increment_usage(config.MAX_DAILY_QUERIES)
        if not allowed:
            logger.warning(f"Daily query cap of {config.MAX_DAILY_QUERIES} reached. Blocking request.")
            return ["LIMIT_EXCEEDED: Codex AI has reached its daily query limit to prevent hosting costs. Please try again tomorrow!"], {
                "context_docs": [],
                "cache_hit": False,
                "similarity_score": similarity,
                "query_emb": query_emb,
                "start_time": start_time
            }
        
        logger.info("Usage within limits. Performing Firestore query...")
        
        # 5. Retrieve documents from Firestore Vector DB using embedded search query
        context_docs = search_vector(query_emb, limit=3)
        
        # 6. Ground prompt in context XML, including cached market price metadata if available
        context_parts = []
        for doc in context_docs:
            doc_str = f"<document title='{doc['title']}'>"
            if doc.get("market_price"):
                doc_str += f"\n[Market Info: {doc['market_price']}]"
            doc_str += f"\n{doc['content']}\n</document>"
            context_parts.append(doc_str)
        context_str = "\n".join(context_parts)
        
        prompt = f"""Based on the following retrieved information, answer the user's question.
 
<context>
{context_str}
</context>
 
Question: {sanitized_query}
Answer:"""
        
        print("\n=== SUBMITTING PROMPT TO GEMINI ===")
        print(prompt)
        print("===================================\n")
        
        # 7. Invoke Gemini 2.5 Flash stream
        config_obj = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTIONS,
            max_output_tokens=1000,
            temperature=0.0
        )
        
        response_stream = client.models.generate_content_stream(
            model=config.GENERATION_MODEL,
            contents=prompt,
            config=config_obj
        )
        
        return response_stream, {
            "context_docs": context_docs,
            "cache_hit": False,
            "similarity_score": similarity,
            "query_emb": query_emb,
            "search_query": search_query,
            "start_time": start_time
        }


    def log_telemetry_to_vertex(self, prompt: str, response: str, payload: dict):
        """
        Asynchronously called to commit response to cache, write local log, and upload to Vertex AI.
        """
        cache_hit = payload.get("cache_hit", False)
        latency = time.time() - payload.get("start_time", time.time())
        
        # 1. Write Local Telemetry Log File (Used for the public privacy-safe dashboard)
        try:
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latency": latency,
                "cache_hit": cache_hit,
                "similarity_score": payload.get("similarity_score"),
                "query": prompt,
                "response": response,
                "context_count": len(payload.get("context_docs", [])),
                "context_docs": [
                    {
                        "id": doc.get("id"),
                        "title": doc.get("title"),
                        "distance": doc.get("distance")
                    }
                    for doc in payload.get("context_docs", [])
                ],
                "word_count": len(response.split())
            }
            with open(config.TELEMETRY_LOG_PATH, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to log local telemetry JSONL: {e}")
        
        # 2. Upload telemetry to Vertex AI and save to semantic cache
        if not cache_hit:
            print("\n=== GEMINI RESPONSE ===")
            print(response)
            print("=======================\n")
            
            # Save cache miss response to semantic cache using condensed query
            query_emb = payload.get("query_emb")
            search_query = payload.get("search_query", prompt)
            if query_emb and not response.startswith("LIMIT_EXCEEDED"):
                semantic_cache.add(search_query, query_emb, response)
            
            # Log telemetry to Vertex AI using the original raw prompt
            log_inference_run(
                query=prompt,
                response=response,
                context_docs=payload.get("context_docs", []),
                cache_hit=False,
                similarity_score=payload.get("similarity_score")
            )
        else:
            # Log cache hit telemetry run using the original raw prompt
            log_inference_run(
                query=prompt,
                response=response,
                context_docs=[],
                cache_hit=True,
                similarity_score=payload.get("similarity_score")
            )


