import urllib.request
import json
import re
import logging
import os
import time
from google.genai import types
from google.cloud.firestore_v1.vector import Vector

import config
from firestore_db import get_firestore_client
from rag_engine import get_genai_client

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of API data feeds (WFCD/warframe-items CDN)
DATA_FEEDS = {
    "Warframes": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Warframes.json",
    "Primary": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Primary.json",
    "Secondary": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Secondary.json",
    "Melee": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Melee.json"
}

def make_warframe_text(item: dict) -> str:
    name = item.get("name", "Unknown Warframe")
    desc = item.get("description", "")
    health = item.get("health", 100)
    shield = item.get("shield", 100)
    armor = item.get("armor", 100)
    power = item.get("power", 100)
    passive = item.get("passiveDescription", "None")
    
    abilities_text = []
    for a in item.get("abilities", []):
        abilities_text.append(f"- {a.get('name')}: {a.get('description', '')}")
    abilities_str = "\n".join(abilities_text)
    
    text = f"""Warframe Name: {name}
Description: {desc}
Base Stats: Health {health}, Shield {shield}, Armor {armor}, Energy/Power {power}
Passive Ability: {passive}
Abilities:
{abilities_str}
"""
    return text

def make_weapon_text(item: dict) -> str:
    name = item.get("name", "Unknown Weapon")
    desc = item.get("description", "")
    category = item.get("category", "")
    w_type = item.get("type", "")
    crit_chance = item.get("criticalChance", 0)
    crit_mult = item.get("criticalMultiplier", 1.0)
    status_chance = item.get("procChance", 0) or item.get("statusChance", 0)
    fire_rate = item.get("fireRate", 0)
    multishot = item.get("multishot", 1.0)
    mag_size = item.get("magazineSize", 0)
    reload_time = item.get("reloadTime", 0)
    
    damage = item.get("damage", {})
    if isinstance(damage, dict):
        damage_details = ", ".join([f"{k}: {v}" for k, v in damage.items() if k != "total"])
    else:
        damage_details = str(damage)
        
    text = f"""Weapon Name: {name}
Category: {category} ({w_type})
Description: {desc}
Base Stats:
- Critical Chance: {crit_chance * 100:.1f}%
- Critical Multiplier: {crit_mult:.1f}x
- Status Chance: {status_chance * 100:.1f}%
- Fire Rate: {fire_rate:.1f}
- Multishot: {multishot:.1f}
- Magazine Size: {mag_size}
- Reload Time: {reload_time:.2f}s
- Damage Types: {damage_details}
"""
    return text

def fetch_feed_data(url: str) -> list[dict]:
    """
    Downloads items JSON file from the CDN.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityWarframeBot/1.0"
    })
    try:
        logger.info(f"Fetching JSON data from: {url}...")
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"Error fetching feed: {e}")
        return []

def get_batch_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Requests embeddings in a single batch call from Vertex AI.
    """
    client = get_genai_client()
    contents = [types.Content(parts=[types.Part(text=t)]) for t in texts]
    response = client.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=contents
    )
    return [e.values for e in response.embeddings]

def ingest_data():
    """
    Pulls structured JSON data, reformats items, generates batch embeddings,
    and commits documents to Firestore in batches.
    """
    # Use environment variable if already set; otherwise fallback to local gcloud ADC path if it exists
    if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
        local_adc = "/root/.config/gcloud/application_default_credentials.json"
        if os.path.exists(local_adc):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_adc

    db = get_firestore_client()
    
    all_chunks = []
    
    # 1. Fetch and Parse Feeds
    for category, url in DATA_FEEDS.items():
        items = fetch_feed_data(url)
        logger.info(f"Loaded {len(items)} items for category '{category}'")
        
        for item in items:
            name = item.get("name")
            if not name:
                continue
                
            # Exclude internal components or items without description
            desc = item.get("description", "")
            if not desc or "skin" in name.lower() or "blueprint" in name.lower() or "relic" in name.lower():
                continue
                
            # Format text
            if category == "Warframes":
                content_text = make_warframe_text(item)
                title_str = f"Warframe - {name}"
            else:
                content_text = make_weapon_text(item)
                title_str = f"Weapon - {name}"
                
            # Clean safe doc ID
            doc_id = f"item-{category.lower()}-{re.sub(r'[^a-z0-9_-]', '', name.lower())}"[:100]
            
            all_chunks.append({
                "id": doc_id,
                "title": title_str,
                "content": content_text
            })
            
    logger.info(f"Total structured items selected for ingestion: {len(all_chunks)}")
    
    # 2. Batch Embedding Generation and Upload
    batch_size = 100
    total_uploaded = 0
    
    for i in range(0, len(all_chunks), batch_size):
        batch_chunks = all_chunks[i : i + batch_size]
        batch_texts = [c["content"] for c in batch_chunks]
        
        try:
            logger.info(f"Generating embeddings for batch {i//batch_size + 1} (size {len(batch_chunks)})...")
            embeddings = get_batch_embeddings(batch_texts)
            
            logger.info(f"Uploading batch {i//batch_size + 1} to Firestore...")
            db_batch = db.batch()
            
            for idx, chunk in enumerate(batch_chunks):
                doc_ref = db.collection(config.COLLECTION_NAME).document(chunk["id"])
                db_batch.set(doc_ref, {
                    "title": chunk["title"],
                    "content": chunk["content"],
                    "embedding": Vector(embeddings[idx])
                })
                
            db_batch.commit()
            total_uploaded += len(batch_chunks)
            logger.info(f"Successfully uploaded batch {i//batch_size + 1} ({total_uploaded}/{len(all_chunks)} total).")
            
            # Rate limiting safety delay
            time.sleep(1.0)
            
        except Exception as e:
            logger.error(f"Failed to process batch {i//batch_size + 1}: {e}")
            
    logger.info(f"Ingestion complete. Successfully uploaded {total_uploaded} items to Firestore.")

if __name__ == "__main__":
    ingest_data()

