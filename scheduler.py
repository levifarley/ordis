import time
import logging
import json
import os
from datetime import datetime, timezone
from ingest import ingest_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATUS_FILE = "/projects/ordis/scheduler_status.json"

def save_status(status: str, details: dict = None):
    try:
        data = {
            "status": status,
            "last_run": datetime.now(timezone.utc).isoformat(),
            "details": details or {}
        }
        with open(STATUS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save scheduler status: {e}")

def main():
    logger.info("Scheduler daemon started.")
    save_status("started")
    
    while True:
        logger.info("Starting scheduled ingestion cycle...")
        save_status("running")
        
        start_time = time.time()
        try:
            results = ingest_data()
            elapsed = time.time() - start_time
            logger.info(f"Ingestion cycle completed successfully in {elapsed:.2f}s. Results: {results}")
            save_status("success", {
                "duration_seconds": elapsed,
                "new_embeddings": results.get("new_embeddings", 0),
                "prices_updated": results.get("prices_updated", 0),
                "status": results.get("status", "success")
            })
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Ingestion cycle failed after {elapsed:.2f}s: {e}")
            save_status("failed", {
                "duration_seconds": elapsed,
                "error": str(e)
            })
            
        logger.info("Scheduler sleeping for 24 hours...")
        time.sleep(86400)

if __name__ == "__main__":
    main()
