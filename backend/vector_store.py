from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
import chromadb
from chromadb.config import Settings as ChromaSettings
from backend.config import settings

logger = logging.getLogger("ordis.vector_store")

class BaseVectorStore(ABC):
    """Abstract interface for pluggable vector databases."""
    @abstractmethod
    def add_documents(self, docs: List[Dict[str, Any]], embeddings: List[List[float]]):
        pass

    @abstractmethod
    def search_similar(self, query_embedding: List[float], limit: int = 3) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_existing_hashes(self) -> Dict[str, str]:
        pass

    @abstractmethod
    def update_market_price(self, doc_id: str, market_price: str):
        pass


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB implementation of BaseVectorStore."""
    def __init__(self):
        hosts_to_try = []
        if settings.CHROMA_HOST:
            hosts_to_try.append(settings.CHROMA_HOST)
        for fallback in ["http://chromadb:8000", "http://localhost:8002", "http://127.0.0.1:8002"]:
            if fallback not in hosts_to_try:
                hosts_to_try.append(fallback)

        connected = False
        for host_url in hosts_to_try:
            try:
                if "://" in host_url:
                    host = host_url.split("://")[-1].split(":")[0]
                    port = int(host_url.split(":")[-1]) if ":" in host_url.split("://")[-1] else 8000
                else:
                    host = host_url
                    port = settings.CHROMA_PORT
                self.client = chromadb.HttpClient(host=host, port=port)
                self.client.heartbeat()
                logger.info(f"Connected to ChromaDB HTTP server at {host}:{port}")
                connected = True
                break
            except Exception:
                continue

        if not connected:
            logger.warning("Could not connect to ChromaDB HTTP server. Falling back to local persistent Chroma client.")
            self.client = chromadb.PersistentClient(path="./chroma_db_storage")

        self.collection = self.client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    def add_documents(self, docs: List[Dict[str, Any]], embeddings: List[List[float]]):
        if not docs:
            return
        
        ids = [d["id"] for d in docs]
        documents = [d["content"] for d in docs]
        metadatas = [
            {
                "title": d.get("title", ""),
                "content_hash": d.get("content_hash", ""),
                "market_price": d.get("market_price", ""),
                "source": d.get("source", "mcp")
            }
            for d in docs
        ]
        
        try:
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
        except Exception as e:
            if "dimension" in str(e).lower():
                logger.warning(f"Dimension mismatch in ChromaDB upsert ({e}). Recreating collection...")
                try:
                    self.client.delete_collection(name=settings.COLLECTION_NAME)
                except Exception:
                    pass
                self.collection = self.client.get_or_create_collection(
                    name=settings.COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"}
                )
                self.collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
            else:
                raise e
        logger.info(f"Successfully upserted {len(docs)} documents into ChromaDB.")

    def search_similar(self, query_embedding: List[float], limit: int = 3) -> List[Dict[str, Any]]:
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            if "dimension" in str(e).lower():
                logger.warning(f"Dimension mismatch in ChromaDB query ({e}). Recreating collection...")
                try:
                    self.client.delete_collection(name=settings.COLLECTION_NAME)
                except Exception:
                    pass
                self.collection = self.client.get_or_create_collection(
                    name=settings.COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"}
                )
                return []
            raise e
        
        docs = []
        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0]
            
            for idx in range(len(ids)):
                docs.append({
                    "id": ids[idx],
                    "title": metadatas[idx].get("title", ""),
                    "content": documents[idx],
                    "market_price": metadatas[idx].get("market_price", ""),
                    "distance": distances[idx]
                })
        return docs

    def get_existing_hashes(self) -> Dict[str, str]:
        try:
            data = self.collection.get(include=["metadatas"])
            hashes = {}
            if data and data.get("ids"):
                for idx, doc_id in enumerate(data["ids"]):
                    hashes[doc_id] = data["metadatas"][idx].get("content_hash", "")
            return hashes
        except Exception as e:
            logger.error(f"Error reading hashes from ChromaDB: {e}")
            return {}

    def update_market_price(self, doc_id: str, market_price: str):
        try:
            res = self.collection.get(ids=[doc_id], include=["metadatas", "documents"])
            if res and res.get("ids"):
                meta = res["metadatas"][0]
                doc = res["documents"][0]
                meta["market_price"] = market_price
                self.collection.update(ids=[doc_id], metadatas=[meta], documents=[doc])
        except Exception as e:
            logger.error(f"Failed to update market price for doc {doc_id}: {e}")


def get_vector_store() -> BaseVectorStore:
    """Factory function for obtaining configured BaseVectorStore implementation."""
    provider = settings.VECTOR_STORE_PROVIDER.lower()
    if provider == "chroma":
        return ChromaVectorStore()
    else:
        logger.warning(f"Unsupported VECTOR_STORE_PROVIDER '{provider}'. Defaulting to ChromaVectorStore.")
        return ChromaVectorStore()
