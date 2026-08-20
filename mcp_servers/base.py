from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ordis.mcp_servers")

class BaseMCPServer(ABC):
    """Abstract Base Class for all ORDIS Model Context Protocol (MCP) Servers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier name of the MCP server."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of the dataset or service provided."""
        pass

    @abstractmethod
    def fetch_data(self) -> List[Dict[str, Any]]:
        """Fetch all resources/chunks provided by this MCP server."""
        pass


from mcp_servers.wfcd_mcp import WFCDMCPServer
from mcp_servers.wiki_mcp import WikiMCPServer
from mcp_servers.market_mcp import MarketMCPServer
from mcp_servers.builds_mcp import BuildsMCPServer

app = FastAPI(title="ORDIS MCP Server Cluster", version="1.0.0")

wfcd_server = WFCDMCPServer()
wiki_server = WikiMCPServer()
market_server = MarketMCPServer()
builds_server = BuildsMCPServer()

registered_servers: Dict[str, BaseMCPServer] = {
    wfcd_server.name: wfcd_server,
    wiki_server.name: wiki_server,
    market_server.name: market_server,
    builds_server.name: builds_server,
}

@app.get("/mcp/health")
def mcp_health():
    return {
        "status": "ok",
        "mcp_cluster": "active",
        "servers": [
            {"name": s.name, "description": s.description}
            for s in registered_servers.values()
        ]
    }

@app.get("/mcp/servers")
def list_servers() -> List[Dict[str, str]]:
    return [
        {"name": s.name, "description": s.description}
        for s in registered_servers.values()
    ]

@app.get("/mcp/items")
def get_items() -> List[Dict[str, Any]]:
    logger.info("MCP Request: Fetching items from WFCD server...")
    return wfcd_server.fetch_data()

@app.get("/mcp/wiki")
def get_wiki() -> List[Dict[str, Any]]:
    logger.info("MCP Request: Fetching guide pages from Wiki server...")
    return wiki_server.fetch_data()

@app.get("/mcp/market/{item_name}")
def get_market_price(item_name: str) -> Dict[str, str]:
    logger.info(f"MCP Request: Fetching market price for '{item_name}'...")
    price = market_server.fetch_price_stats(item_name)
    return {"item_name": item_name, "market_price": price}

@app.get("/mcp/builds")
def get_builds() -> List[Dict[str, Any]]:
    logger.info("MCP Request: Fetching community weapon/frame builds...")
    return builds_server.fetch_data()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

