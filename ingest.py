import urllib.request
import urllib.parse
import json
import re
import logging
import os
import time
import hashlib
from datetime import datetime, timezone
from google.genai import types
from google.cloud.firestore_v1.vector import Vector

import config
import firestore_db
from firestore_db import get_firestore_client, get_existing_hashes, update_market_price
from rag_engine import get_genai_client

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of API data feeds (WFCD/warframe-items CDN)
DATA_FEEDS = {
    "Warframes": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Warframes.json",
    "Primary": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Primary.json",
    "Secondary": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Secondary.json",
    "Melee": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Melee.json",
    "Mods": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Mods.json",
    "Arcanes": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Arcanes.json"
}

WIKI_PAGES = ["Damage", "Status_Effect", "Affinity", "Mastery_Rank"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CRAWLER_CACHE_FILE = os.path.join(BASE_DIR, "crawler_cache.json")

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

def make_mod_text(item: dict) -> str:
    name = item.get("name", "Unknown Mod")
    desc = item.get("description", "")
    compat = item.get("compatName", "") or item.get("type", "Mod")
    polarity = item.get("polarity", "")
    rarity = item.get("rarity", "")
    base_drain = item.get("baseDrain", 0)
    
    desc_clean = re.sub(r'<[^>]*>', '', desc)
    
    text = f"""Mod Name: {name}
Compatibility/Type: {compat}
Polarity: {polarity}
Rarity: {rarity}
Base Drain: {base_drain}
Description / Effects: {desc_clean}
"""
    return text

def make_arcane_text(item: dict) -> str:
    name = item.get("name", "Unknown Upgrade/Arcane")
    desc = item.get("description", "")
    type_str = item.get("type", "Upgrade")
    
    desc_clean = re.sub(r'<[^>]*>', '', desc)
    
    text = f"""Upgrade Name: {name}
Type: {type_str}
Description / Effects: {desc_clean}
"""
    return text

def load_crawler_cache() -> dict:
    if os.path.exists(CRAWLER_CACHE_FILE):
        try:
            with open(CRAWLER_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_crawler_cache(cache: dict):
    try:
        with open(CRAWLER_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save crawler cache file: {e}")

def fetch_feed_data_cached(url: str, cache_store: dict) -> tuple[list[dict], bool]:
    """
    Downloads items JSON from CDN. Employs conditional GET using ETag/Last-Modified.
    Returns (parsed_data, was_modified).
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityWarframeBot/1.0"
    })
    
    cached_info = cache_store.get(url, {})
    etag = cached_info.get("etag")
    last_modified = cached_info.get("last_modified")
    
    if etag:
        req.add_header("If-None-Match", etag)
    if last_modified:
        req.add_header("If-Modified-Since", last_modified)
        
    try:
        logger.info(f"Fetching JSON data from: {url}...")
        with urllib.request.urlopen(req, timeout=30) as response:
            info = response.info()
            new_etag = info.get("ETag")
            new_last_modified = info.get("Last-Modified")
            
            cache_store[url] = {
                "etag": new_etag,
                "last_modified": new_last_modified
            }
            
            data = json.loads(response.read().decode("utf-8"))
            return data, True
    except urllib.error.HTTPError as e:
        if e.code == 304:
            logger.info(f"Feed {url} has not changed (304 Not Modified). Skipping feed download.")
            return [], False
        logger.error(f"HTTP error fetching feed {url}: {e}")
        return [], False
    except Exception as e:
        logger.error(f"Error fetching feed {url}: {e}")
        return [], False

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

# -------------------------------------------------------------------
# MediaWiki Scraper for high-value guide pages
# -------------------------------------------------------------------
def clean_wikitext(text: str) -> str:
    text = re.sub(r'<[^>]*>', '', text)
    for _ in range(5):
        text = re.sub(r'\{\{[^{}]*\}\}', '', text)
    text = re.sub(r'\[\[[^|\]]*\|([^\]]*)\]\]', r'\1', text)
    text = re.sub(r'\[\[([^\]]*)\]\]', r'\1', text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def chunk_wikitext(page_title: str, text: str) -> list[dict]:
    sections = []
    current_title = "Overview"
    current_content = []
    
    lines = text.split('\n')
    for line in lines:
        match = re.match(r'^==+\s*(.*?)\s*==+$', line)
        if match:
            if current_content:
                sections.append({
                    "title": f"Wiki: {page_title} - {current_title}",
                    "content": "\n".join(current_content).strip()
                })
            current_title = match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)
            
    if current_content:
        sections.append({
            "title": f"Wiki: {page_title} - {current_title}",
            "content": "\n".join(current_content).strip()
        })
        
    cleaned_sections = []
    for s in sections:
        clean_body = clean_wikitext(s["content"])
        if len(clean_body) > 100:
            cleaned_sections.append({
                "title": s["title"],
                "content": f"{s['title']}\n\n{clean_body}"
            })
    return cleaned_sections

def fetch_wiki_page(page_name: str) -> list[dict]:
    url = f"https://warframe.fandom.com/api.php?action=parse&page={urllib.parse.quote(page_name)}&prop=wikitext&format=json"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityWarframeBot/1.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            res = json.loads(response.read().decode("utf-8"))
            wikitext = res.get("parse", {}).get("wikitext", {}).get("*", "")
            if wikitext:
                return chunk_wikitext(page_name, wikitext)
    except Exception as e:
        logger.error(f"Error fetching wiki page {page_name}: {e}")
    return []

# -------------------------------------------------------------------
# warframe.market Pricing Stats crawler
# -------------------------------------------------------------------
def get_market_slug(item_name: str) -> str:
    s = item_name.lower()
    s = s.replace(" - ", "_").replace(" -", "_").replace("- ", "_").replace("-", "_")
    s = re.sub(r'[^a-z0-9_\s]', '', s)
    s = re.sub(r'\s+', '_', s.strip())
    if s.endswith("_prime"):
        return f"{s}_set"
    return s

def fetch_market_price_stats(slug: str) -> str:
    url = f"https://api.warframe.market/v1/items/{slug}/statistics"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntigravityWarframeBot/1.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res = json.loads(response.read().decode("utf-8"))
            stats = res.get("payload", {}).get("statistics_closed", {}).get("48hours", [])
            if stats:
                latest = stats[-1]
                median = latest.get("median", 0)
                avg = latest.get("avg", 0.0)
                volume = latest.get("volume", 0)
                min_p = latest.get("min_price", 0)
                max_p = latest.get("max_price", 0)
                return f"Median Price: {median} platinum (Avg: {avg:.1f}p, Min: {min_p}p, Max: {max_p}p, Volume: {volume} traded in last 48 hours)"
    except Exception as e:
        logger.debug(f"Failed to crawl market details for slug '{slug}': {e}")
    return ""

# -------------------------------------------------------------------
# Primary Ingestion Routine
# -------------------------------------------------------------------
def ingest_data() -> dict:
    """
    Core data synchronizer. Feeds Firestore vector index from all three APIs
    under strict token limits, HTTP cache policies, and idempotent hash checks.
    """
    if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
        local_adc = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
        if os.path.exists(local_adc):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = local_adc

    logger.info("Initializing ingestion crawler...")
    db = get_firestore_client()
    
    crawler_cache = load_crawler_cache()
    
    logger.info("Retrieving existing document hashes from Firestore...")
    existing_hashes = get_existing_hashes()
    logger.info(f"Loaded {len(existing_hashes)} current document hashes.")
    
    all_chunks = []
    
    # 1. Fetch & Parse static CDN feeds
    for category, url in DATA_FEEDS.items():
        items, was_modified = fetch_feed_data_cached(url, crawler_cache)
        if not was_modified:
            continue
            
        logger.info(f"Parsing {len(items)} items from feed: {category}")
        for item in items:
            name = item.get("name")
            if not name:
                continue
                
            desc = item.get("description", "")
            if not desc or "skin" in name.lower() or "blueprint" in name.lower() or "relic" in name.lower():
                continue
                
            if category == "Warframes":
                content_text = make_warframe_text(item)
                title_str = f"Warframe - {name}"
            elif category in ("Primary", "Secondary", "Melee"):
                content_text = make_weapon_text(item)
                title_str = f"Weapon - {name}"
            elif category == "Mods":
                content_text = make_mod_text(item)
                title_str = f"Mod - {name}"
            elif category == "Arcanes":
                content_text = make_arcane_text(item)
                title_str = f"Arcane - {name}"
            else:
                continue
                
            doc_id = f"item-{category.lower()}-{re.sub(r'[^a-z0-9_-]', '', name.lower())}"[:100]
            content_hash = hashlib.md5(content_text.encode('utf-8')).hexdigest()
            
            if existing_hashes.get(doc_id) == content_hash:
                continue
                
            all_chunks.append({
                "id": doc_id,
                "title": title_str,
                "content": content_text,
                "content_hash": content_hash,
                "is_wiki": False
            })
            
    # 2. Fetch & Parse Wiki pages
    wiki_request_count = 0
    for page in WIKI_PAGES:
        if wiki_request_count >= config.MAX_WIKI_API_CALLS_PER_CYCLE:
            logger.warning("MediaWiki API request limit reached. Skipping remaining wiki crawls.")
            break
            
        logger.info(f"Crawling Fandom Wiki guide page: {page}...")
        wiki_request_count += 1
        time.sleep(1.0)
        
        wiki_sections = fetch_wiki_page(page)
        for idx, sec in enumerate(wiki_sections):
            doc_id = f"wiki-{page.lower()}-section{idx}"
            content_hash = hashlib.md5(sec["content"].encode('utf-8')).hexdigest()
            
            if existing_hashes.get(doc_id) == content_hash:
                continue
                
            all_chunks.append({
                "id": doc_id,
                "title": sec["title"],
                "content": sec["content"],
                "content_hash": content_hash,
                "is_wiki": True
            })

    save_crawler_cache(crawler_cache)
    
    # 3. Quota Limits and Embedding Generation
    logger.info(f"Total new/changed items to embed: {len(all_chunks)}")
    
    total_tokens_estimated = sum(len(c["content"]) // 4 for c in all_chunks)
    logger.info(f"Estimated embedding token requirements: {total_tokens_estimated} tokens.")
    
    if total_tokens_estimated > config.MAX_EMBEDDING_TOKENS_PER_CYCLE:
        logger.warning(f"Ingestion halted: token requirements ({total_tokens_estimated}) exceed the safeguard limit of {config.MAX_EMBEDDING_TOKENS_PER_CYCLE}!")
        return {"status": "halted_token_limit", "new_embeddings": 0, "prices_updated": 0}
        
    batch_size = 15
    total_embedded = 0
    
    for i in range(0, len(all_chunks), batch_size):
        batch_chunks = all_chunks[i : i + batch_size]
        batch_texts = [c["content"] for c in batch_chunks]
        
        try:
            logger.info(f"Generating embeddings for batch {i//batch_size + 1} (size {len(batch_chunks)})...")
            embeddings = get_batch_embeddings(batch_texts)
            
            db_batch = db.batch()
            for idx, chunk in enumerate(batch_chunks):
                doc_ref = db.collection(config.COLLECTION_NAME).document(chunk["id"])
                db_batch.set(doc_ref, {
                    "title": chunk["title"],
                    "content": chunk["content"],
                    "content_hash": chunk["content_hash"],
                    "embedding": Vector(embeddings[idx]),
                    "last_updated": datetime.now(timezone.utc)
                }, merge=True)
                
            db_batch.commit()
            total_embedded += len(batch_chunks)
            time.sleep(1.0)
        except Exception as e:
            logger.error(f"Failed embedding batch {i//batch_size + 1}: {e}")
            
    # 4. Sync market prices (Updates metadata fields only - preserves embeddings)
    logger.info("Executing live market price updates...")
    market_request_count = 0
    updated_prices_count = 0
    
    active_tradeables = {}
    try:
        active_docs = db.collection(config.COLLECTION_NAME).select(["title"]).stream()
        for doc in active_docs:
            doc_id = doc.id
            title = doc.to_dict().get("title", "")
            if "Prime" in title or "Mod - " in title or "Arcane - " in title:
                name_clean = title.split(" - ")[-1]
                active_tradeables[doc_id] = get_market_slug(name_clean)
    except Exception as e:
        logger.error(f"Error querying list of tradeable items: {e}")
        
    for doc_id, slug in active_tradeables.items():
        if market_request_count >= config.MAX_MARKET_API_CALLS_PER_CYCLE:
            logger.warning("Market API request cap reached. Stopping price crawl.")
            break
            
        logger.info(f"Fetching market statistics for item slug: {slug}...")
        market_request_count += 1
        time.sleep(1.0)
        
        price_string = fetch_market_price_stats(slug)
        if price_string:
            update_market_price(doc_id, price_string)
            updated_prices_count += 1
            
    logger.info(f"Ingestion sync cycle complete. Embedded {total_embedded} documents. Updated prices for {updated_prices_count} items.")
    return {
        "status": "success",
        "new_embeddings": total_embedded,
        "prices_updated": updated_prices_count
    }

if __name__ == "__main__":
    ingest_data()
