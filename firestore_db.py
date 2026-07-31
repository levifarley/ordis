from datetime import datetime, timezone
from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
import config

_db_client = None

def get_firestore_client():
    """
    Returns a singleton instance of the Firestore client.
    """
    global _db_client
    if _db_client is None:
        _db_client = firestore.Client(
            project=config.PROJECT_ID,
            database=config.FIRESTORE_DATABASE
        )
    return _db_client

def insert_wiki_chunk(doc_id: str, title: str, content: str, embedding: list[float]):
    """
    Inserts a wiki chunk and its embedding vector into the Firestore collection.
    """
    db = get_firestore_client()
    doc_ref = db.collection(config.COLLECTION_NAME).document(doc_id)
    doc_ref.set({
        "title": title,
        "content": content,
        "embedding": Vector(embedding)
    })

def search_vector(query_embedding: list[float], limit: int = 3) -> list[dict]:
    """
    Performs Native Vector Search on Firestore using find_nearest.
    """
    db = get_firestore_client()
    collection_ref = db.collection(config.COLLECTION_NAME)
    
    # Firestore requires the query vector wrapped in Vector
    query_vector = Vector(query_embedding)
    
    # Run the find_nearest query
    results = (
        collection_ref.find_nearest(
            vector_field="embedding",
            query_vector=query_vector,
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
            distance_result_field="vector_distance"
        )
        .get()
    )
    
    docs = []
    for doc in results:
        data = doc.to_dict()
        docs.append({
            "id": doc.id,
            "title": data.get("title", ""),
            "content": data.get("content", ""),
            "market_price": data.get("market_price", ""),
            "distance": data.get("vector_distance")
        })
    return docs

def check_and_increment_usage(limit: int = 300) -> tuple[bool, int]:
    """
    Checks the daily query usage in Firestore telemetry.
    Returns (allowed, current_count). If allowed is False, usage is at/above limit.
    Automatically resets daily based on UTC date.
    """
    db = get_firestore_client()
    doc_ref = db.collection("telemetry").document("usage_stats")
    
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    transaction = db.transaction()
    
    @firestore.transactional
    def update_in_transaction(transaction, doc_ref):
        snapshot = doc_ref.get(transaction=transaction)
        data = snapshot.to_dict() if snapshot.exists else {}
        
        last_reset = data.get("last_reset", "")
        current_count = data.get("query_count", 0)
        
        # Reset if it's a new calendar day
        if last_reset != today_str:
            current_count = 0
            
        if current_count >= limit:
            return False, current_count
            
        new_count = current_count + 1
        transaction.set(doc_ref, {
            "query_count": new_count,
            "last_reset": today_str
        }, merge=True)
        return True, new_count

    return update_in_transaction(transaction, doc_ref)

def get_existing_hashes() -> dict[str, str]:
    """
    Fetches all document IDs and their content_hash fields using projections (.select).
    Returns a dict mapping doc_id -> content_hash.
    """
    db = get_firestore_client()
    docs = db.collection(config.COLLECTION_NAME).select(["content_hash"]).stream()
    hashes = {}
    for doc in docs:
        data = doc.to_dict()
        hashes[doc.id] = data.get("content_hash", "")
    return hashes

def update_market_price(doc_id: str, market_price: str):
    """
    Updates only the market_price of a document in Firestore.
    Does NOT regenerate or alter the vector embedding.
    """
    db = get_firestore_client()
    doc_ref = db.collection(config.COLLECTION_NAME).document(doc_id)
    doc_ref.set({
        "market_price": market_price,
        "last_updated": datetime.now(timezone.utc)
    }, merge=True)


