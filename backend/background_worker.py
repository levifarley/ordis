import asyncio
import hashlib
import logging
from typing import List, Dict, Any, Optional
from backend.config import settings
from backend.vector_store import get_vector_store, BaseVectorStore
from backend.rag_engine import get_llm_provider, BaseLLMProvider
from backend.mcp_manager import mcp_manager, MCPManager

logger = logging.getLogger("ordis.background_worker")


class BackgroundWorker:
    """Manages initial and scheduled data ingestion from MCP servers into ChromaDB."""

    def __init__(
        self,
        vector_store: Optional[BaseVectorStore] = None,
        llm: Optional[BaseLLMProvider] = None,
        mcp: Optional[MCPManager] = None
    ):
        self._vector_store = vector_store
        self._llm = llm
        self._mcp = mcp or mcp_manager
        self.is_ingesting = False

    @property
    def vector_store(self) -> BaseVectorStore:
        if self._vector_store is None:
            self._vector_store = get_vector_store()
        return self._vector_store

    @property
    def llm(self) -> BaseLLMProvider:
        if self._llm is None:
            self._llm = get_llm_provider()
        return self._llm

    async def ingest_all_data(self) -> Dict[str, Any]:
        """Fetch records from all MCP servers, compute content hashes, and upsert changed/new documents."""
        if self.is_ingesting:
            logger.info("Ingestion cycle already in progress. Skipping.")
            return {"status": "in_progress", "processed": 0}

        self.is_ingesting = True
        logger.info("Starting background ingestion cycle from MCP servers...")

        try:
            # 1. Fetch data from all connected MCP servers asynchronously
            items_task = asyncio.create_task(self._mcp.fetch_items_from_mcp())
            wiki_task = asyncio.create_task(self._mcp.fetch_wiki_from_mcp())
            builds_task = asyncio.create_task(self._mcp.fetch_builds_from_mcp())

            items, wiki, builds = await asyncio.gather(items_task, wiki_task, builds_task)

            all_docs_raw = items + wiki + builds
            logger.info(f"Retrieved total {len(all_docs_raw)} document chunks from MCP servers.")

            if not all_docs_raw:
                logger.warning("No documents retrieved from MCP servers.")
                return {"status": "completed", "total": 0, "upserted": 0, "skipped": 0}

            # Ensure doc IDs are strictly unique
            seen_ids = set()
            all_docs = []
            for doc in all_docs_raw:
                doc_id = doc.get("id", "")
                if doc_id in seen_ids:
                    suffix = 2
                    new_id = f"{doc_id}-{suffix}"
                    while new_id in seen_ids:
                        suffix += 1
                        new_id = f"{doc_id}-{suffix}"
                    doc["id"] = new_id
                seen_ids.add(doc["id"])
                all_docs.append(doc)

            # 2. Get existing document hashes from ChromaDB vector store
            existing_hashes = self.vector_store.get_existing_hashes()

            new_or_updated_docs = []
            for doc in all_docs:
                content = doc.get("content", "")
                content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                doc["content_hash"] = content_hash

                doc_id = doc["id"]
                if doc_id not in existing_hashes or existing_hashes[doc_id] != content_hash:
                    new_or_updated_docs.append(doc)

            skipped_count = len(all_docs) - len(new_or_updated_docs)
            logger.info(f"Found {len(new_or_updated_docs)} new/updated documents ({skipped_count} skipped - unchanged).")

            # 3. Generate embeddings and upsert in batches
            batch_size = 50
            upserted_count = 0

            for i in range(0, len(new_or_updated_docs), batch_size):
                batch_docs = new_or_updated_docs[i:i + batch_size]
                batch_embeddings = []

                for d in batch_docs:
                    emb = self.llm.get_embedding(d["content"])
                    batch_embeddings.append(emb)

                self.vector_store.add_documents(batch_docs, batch_embeddings)
                upserted_count += len(batch_docs)

            logger.info(f"Background ingestion completed. Upserted: {upserted_count}, Skipped: {skipped_count}.")
            return {
                "status": "completed",
                "total": len(all_docs),
                "upserted": upserted_count,
                "skipped": skipped_count
            }

        except Exception as e:
            logger.error(f"Error during background ingestion: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
        finally:
            self.is_ingesting = False

    async def start_scheduled_worker(self, interval_seconds: int = 86400):
        """Initial check and periodic scheduled loop for background data sync."""
        logger.info("Initializing background worker daemon...")

        # Run initial ingestion immediately upon startup
        await self.ingest_all_data()

        # Run periodic background loop (default 24 hours)
        while True:
            await asyncio.sleep(interval_seconds)
            logger.info("Triggering periodic 24-hour scheduled ingestion...")
            await self.ingest_all_data()


background_worker = BackgroundWorker()
