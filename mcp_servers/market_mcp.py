import urllib.request
import json
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def get_market_slug(item_name: str) -> str:
    s = item_name.lower()
    s = s.replace(" - ", "_").replace(" -", "_").replace("- ", "_").replace("-", "_")
    s = re.sub(r'[^a-z0-9_\s]', '', s)
    s = re.sub(r'\s+', '_', s.strip())
    if s.endswith("_prime"):
        return f"{s}_set"
    return s

from mcp_servers.base import BaseMCPServer
from typing import List

class MarketMCPServer(BaseMCPServer):
    """MCP Server Adapter for warframe.market trade pricing statistics."""

    @property
    def name(self) -> str:
        return "warframe_market"

    @property
    def description(self) -> str:
        return "warframe.market live trade statistics and pricing data"

    def fetch_data(self) -> List[Dict[str, Any]]:
        # Returns market price data for key prime sets as default resources
        sample_items = ["Saryn Prime", "Nikana Prime", "Glaive Prime", "Volt Prime"]
        results = []
        for item in sample_items:
            price_info = self.fetch_price_stats(item)
            if price_info:
                results.append({
                    "id": f"market-{get_market_slug(item)}",
                    "title": f"Market Price - {item}",
                    "content": f"{item}: {price_info}",
                    "source": "warframe_market"
                })
        return results

    def fetch_price_stats(self, item_name: str) -> str:
        slug = get_market_slug(item_name)
        url = f"https://api.warframe.market/v1/items/{slug}/statistics"
        req = urllib.request.Request(url, headers={"User-Agent": "OrdisMCP/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode("utf-8"))
                stats = data.get("payload", {}).get("statistics_closed", {}).get("48hours", [])
                if stats:
                    latest = stats[-1]
                    median = latest.get("median", 0)
                    avg = latest.get("avg", 0.0)
                    volume = latest.get("volume", 0)
                    min_p = latest.get("min_price", 0)
                    max_p = latest.get("max_price", 0)
                    return f"Median Price: {median} platinum (Avg: {avg:.1f}p, Min: {min_p}p, Max: {max_p}p, Volume: {volume} traded in 48h)"
        except Exception as e:
            logger.debug(f"Market MCP price query failed for '{slug}': {e}")
        return ""

