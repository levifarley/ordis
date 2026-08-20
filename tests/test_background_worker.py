import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.background_worker import BackgroundWorker
from backend.vector_store import BaseVectorStore
from backend.rag_engine import BaseLLMProvider
from backend.mcp_manager import MCPManager

@pytest.mark.asyncio
async def test_background_worker_ingestion_and_deduplication():
    """Test background worker ingestion cycle and MD5 content hash deduplication with mocked dependencies."""
    # Mock Vector Store
    mock_vs = MagicMock(spec=BaseVectorStore)
    hashes_store = {}
    
    def mock_get_hashes():
        return dict(hashes_store)
        
    def mock_add_docs(docs, embeddings):
        for d in docs:
            hashes_store[d["id"]] = d["content_hash"]
            
    mock_vs.get_existing_hashes.side_effect = mock_get_hashes
    mock_vs.add_documents.side_effect = mock_add_docs
    
    # Mock LLM Provider
    mock_llm = MagicMock(spec=BaseLLMProvider)
    mock_llm.get_embedding.return_value = [0.1] * 384
    
    # Mock MCP Manager
    mock_mcp = MagicMock(spec=MCPManager)
    dummy_items = [
        {"id": "item-1", "title": "Saryn", "content": "Saryn info", "source": "wfcd"},
        {"id": "item-2", "title": "Volt", "content": "Volt info", "source": "wfcd"}
    ]
    dummy_wiki = [
        {"id": "wiki-1", "title": "Damage 2.0", "content": "Damage mechanics", "source": "fandom_wiki"}
    ]
    dummy_builds = [
        {"id": "build-1", "title": "Saryn Build", "content": "Spores build", "source": "warframe_builds"}
    ]
    
    mock_mcp.fetch_items_from_mcp = AsyncMock(return_value=dummy_items)
    mock_mcp.fetch_wiki_from_mcp = AsyncMock(return_value=dummy_wiki)
    mock_mcp.fetch_builds_from_mcp = AsyncMock(return_value=dummy_builds)
    
    worker = BackgroundWorker(vector_store=mock_vs, llm=mock_llm, mcp=mock_mcp)
    assert worker.is_ingesting is False
    
    # 1. First Ingestion Run
    res1 = await worker.ingest_all_data()
    assert res1["status"] == "completed"
    assert res1["total"] == 4
    assert res1["upserted"] == 4
    assert res1["skipped"] == 0
    assert mock_vs.add_documents.call_count == 1
    
    # 2. Second Immediate Run (Deduplication check)
    res2 = await worker.ingest_all_data()
    assert res2["status"] == "completed"
    assert res2["total"] == 4
    assert res2["upserted"] == 0
    assert res2["skipped"] == 4
