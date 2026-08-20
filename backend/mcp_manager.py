import httpx
import logging
from typing import List, Dict, Any, Optional
from backend.config import settings

logger = logging.getLogger("ordis.mcp_manager")

class MCPManager:
    """Manager for connecting to and retrieving data from containerized MCP servers."""
    def __init__(self, mcp_url: str = None):
        self.base_url = mcp_url or settings.MCP_SERVERS_URL

    async def fetch_items_from_mcp(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/mcp/items"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.warning(f"MCP Manager HTTP error fetching items from '{url}': {e}. Falling back to direct MCP server call.")
            try:
                from mcp_servers.wfcd_mcp import WFCDMCPServer
                return WFCDMCPServer().fetch_data()
            except Exception as fallback_err:
                logger.error(f"Fallback error fetching items: {fallback_err}")
        return []

    async def fetch_wiki_from_mcp(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/mcp/wiki"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.warning(f"MCP Manager HTTP error fetching wiki from '{url}': {e}. Falling back to direct MCP server call.")
            try:
                from mcp_servers.wiki_mcp import WikiMCPServer
                return WikiMCPServer().fetch_data()
            except Exception as fallback_err:
                logger.error(f"Fallback error fetching wiki: {fallback_err}")
        return []

    async def fetch_market_price_from_mcp(self, item_name: str) -> str:
        url = f"{self.base_url}/mcp/market/{item_name}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("market_price", "")
        except Exception as e:
            logger.debug(f"MCP Manager HTTP error fetching market price for '{item_name}': {e}. Falling back to direct MCP server call.")
            try:
                from mcp_servers.market_mcp import MarketMCPServer
                return MarketMCPServer().fetch_price_stats(item_name)
            except Exception as fallback_err:
                logger.error(f"Fallback error fetching market price: {fallback_err}")
        return ""

    async def fetch_builds_from_mcp(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/mcp/builds"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.warning(f"MCP Manager HTTP error fetching builds from '{url}': {e}. Falling back to direct MCP server call.")
            try:
                from mcp_servers.builds_mcp import BuildsMCPServer
                return BuildsMCPServer().fetch_data()
            except Exception as fallback_err:
                logger.error(f"Fallback error fetching builds: {fallback_err}")
        return []

mcp_manager = MCPManager()
