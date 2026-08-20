import pytest
from backend.vector_store import get_vector_store, ChromaVectorStore, BaseVectorStore

def test_vector_store_factory():
    """Verify get_vector_store returns a BaseVectorStore instance."""
    vs = get_vector_store()
    assert isinstance(vs, BaseVectorStore)

def test_chroma_vector_store_operations():
    """Test document insertion, similarity search, hash retrieval, and market price update."""
    vs = get_vector_store()
    
    test_docs = [
        {
            "id": "test-warframe-saryn-1",
            "title": "Warframe - Saryn Prime",
            "content": "Saryn Prime is a toxic warframe capable of spreading deadly spores across enemy ranks.",
            "content_hash": "dummyhash123",
            "market_price": "80 Platinum",
            "source": "test"
        },
        {
            "id": "test-weapon-ignis-1",
            "title": "Weapon - Ignis Wraith",
            "content": "Ignis Wraith is a powerful flamethrower weapon dealing high heat damage.",
            "content_hash": "dummyhash456",
            "market_price": "15 Platinum",
            "source": "test"
        }
    ]
    
    # Dummy 768-dimensional embeddings (matching nomic-embed-text embedding size)
    dummy_emb_1 = [0.1] * 768
    dummy_emb_2 = [0.9] * 768
    
    # 1. Add documents
    vs.add_documents(test_docs, [dummy_emb_1, dummy_emb_2])
    
    # 2. Get existing hashes
    hashes = vs.get_existing_hashes()
    assert "test-warframe-saryn-1" in hashes
    assert hashes["test-warframe-saryn-1"] == "dummyhash123"
    assert "test-weapon-ignis-1" in hashes
    
    # 3. Search similar
    results = vs.search_similar(dummy_emb_1, limit=2)
    assert len(results) > 0
    top_doc = results[0]
    assert "id" in top_doc
    assert "content" in top_doc
    assert "title" in top_doc
    
    # 4. Update market price
    vs.update_market_price("test-warframe-saryn-1", "90 Platinum")
    updated_results = vs.search_similar(dummy_emb_1, limit=1)
    if updated_results and updated_results[0]["id"] == "test-warframe-saryn-1":
        assert updated_results[0]["market_price"] == "90 Platinum"
