import pytest
from mcp_servers.base import BaseMCPServer, app, registered_servers
from mcp_servers.wfcd_mcp import WFCDMCPServer
from mcp_servers.wiki_mcp import WikiMCPServer
from mcp_servers.market_mcp import MarketMCPServer
from mcp_servers.builds_mcp import BuildsMCPServer
from fastapi.testclient import TestClient

client = TestClient(app)

def test_mcp_server_inheritance():
    """Verify all MCP servers inherit from BaseMCPServer and implement required contract."""
    servers = [WFCDMCPServer(), WikiMCPServer(), MarketMCPServer(), BuildsMCPServer()]
    for s in servers:
        assert isinstance(s, BaseMCPServer)
        assert isinstance(s.name, str) and len(s.name) > 0
        assert isinstance(s.description, str) and len(s.description) > 0

def test_mcp_health_endpoint():
    """Test health endpoint of MCP cluster."""
    response = client.get("/mcp/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["mcp_cluster"] == "active"
    assert len(data["servers"]) == 4

def test_mcp_servers_endpoint():
    """Test listing of registered MCP servers."""
    response = client.get("/mcp/servers")
    assert response.status_code == 200
    servers = response.json()
    assert len(servers) == 4
    names = [s["name"] for s in servers]
    assert "wfcd" in names
    assert "fandom_wiki" in names
    assert "warframe_market" in names
    assert "warframe_builds" in names

def test_builds_mcp_server():
    """Test Warframe Builds MCP server data retrieval."""
    server = BuildsMCPServer()
    builds = server.fetch_data()
    assert isinstance(builds, list)
    assert len(builds) >= 4
    for item in builds:
        assert "id" in item
        assert "title" in item
        assert "content" in item
        assert item["source"] == "warframe_builds"

def test_market_mcp_server():
    """Test Warframe Market MCP server slug transformation and price lookup."""
    server = MarketMCPServer()
    assert server.name == "warframe_market"
    # Market slug mapping check
    from mcp_servers.market_mcp import get_market_slug
    assert get_market_slug("Saryn Prime") == "saryn_prime_set"
    assert get_market_slug("Ignis Wraith") == "ignis_wraith"

def test_wiki_mcp_cleaner():
    """Test Wiki wikitext cleaning utility."""
    from mcp_servers.wiki_mcp import clean_wikitext
    dirty = "<p>Test ''italic'' and '''bold''' with [[Link|Display Text]]</p>"
    cleaned = clean_wikitext(dirty)
    assert "italic" in cleaned
    assert "bold" in cleaned
    assert "Display Text" in cleaned
    assert "<p>" not in cleaned

def test_builds_endpoint():
    """Test HTTP API endpoint for builds."""
    response = client.get("/mcp/builds")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 4

