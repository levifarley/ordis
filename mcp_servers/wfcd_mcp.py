import urllib.request
import json
import re
import logging
from typing import Dict, List, Tuple, Any

logger = logging.getLogger(__name__)

DATA_FEEDS = {
    "Warframes": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Warframes.json",
    "Primary": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Primary.json",
    "Secondary": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Secondary.json",
    "Melee": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Melee.json",
    "Mods": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Mods.json",
    "Arcanes": "https://cdn.jsdelivr.net/gh/WFCD/warframe-items@latest/data/json/Arcanes.json"
}

def format_warframe(item: dict) -> str:
    name = item.get("name", "Unknown Warframe")
    desc = item.get("description", "")
    health = item.get("health", 100)
    shield = item.get("shield", 100)
    armor = item.get("armor", 100)
    power = item.get("power", 100)
    passive = item.get("passiveDescription", "None")
    
    abilities = [f"- {a.get('name')}: {a.get('description', '')}" for a in item.get("abilities", [])]
    abilities_str = "\n".join(abilities)
    
    return f"""Warframe Name: {name}
Description: {desc}
Base Stats: Health {health}, Shield {shield}, Armor {armor}, Energy/Power {power}
Passive Ability: {passive}
Abilities:
{abilities_str}"""

def format_weapon(item: dict) -> str:
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
    damage_details = ", ".join([f"{k}: {v}" for k, v in damage.items() if k != "total"]) if isinstance(damage, dict) else str(damage)
        
    return f"""Weapon Name: {name}
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
- Damage Types: {damage_details}"""

def format_mod(item: dict) -> str:
    name = item.get("name", "Unknown Mod")
    desc = re.sub(r'<[^>]*>', '', item.get("description", ""))
    compat = item.get("compatName", "") or item.get("type", "Mod")
    polarity = item.get("polarity", "")
    rarity = item.get("rarity", "")
    base_drain = item.get("baseDrain", 0)
    
    return f"""Mod Name: {name}
Compatibility/Type: {compat}
Polarity: {polarity}
Rarity: {rarity}
Base Drain: {base_drain}
Description / Effects: {desc}"""

def format_arcane(item: dict) -> str:
    name = item.get("name", "Unknown Upgrade/Arcane")
    desc = re.sub(r'<[^>]*>', '', item.get("description", ""))
    type_str = item.get("type", "Upgrade")
    
    return f"""Upgrade Name: {name}
Type: {type_str}
Description / Effects: {desc}"""

from mcp_servers.base import BaseMCPServer

class WFCDMCPServer(BaseMCPServer):
    """MCP Server Adapter for Warframe Community Items data."""

    @property
    def name(self) -> str:
        return "wfcd"

    @property
    def description(self) -> str:
        return "Warframe Community Data (Warframes, Primary, Secondary, Melee, Mods, Arcanes)"

    def fetch_data(self) -> List[Dict[str, Any]]:
        return self.fetch_items()

    def fetch_items(self) -> List[Dict[str, Any]]:
        chunks = []
        for category, url in DATA_FEEDS.items():
            req = urllib.request.Request(url, headers={"User-Agent": "OrdisMCP/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=15) as res:
                    items = json.loads(res.read().decode("utf-8"))
                    for item in items:
                        name = item.get("name")
                        desc = item.get("description", "")
                        if not name or not desc or "skin" in name.lower() or "relic" in name.lower():
                            continue
                        
                        if category == "Warframes":
                            content = format_warframe(item)
                            title = f"Warframe - {name}"
                        elif category in ("Primary", "Secondary", "Melee"):
                            content = format_weapon(item)
                            title = f"Weapon - {name}"
                        elif category == "Mods":
                            content = format_mod(item)
                            title = f"Mod - {name}"
                        elif category == "Arcanes":
                            content = format_arcane(item)
                            title = f"Arcane - {name}"
                        else:
                            continue
                        
                        doc_id = f"item-{category.lower()}-{re.sub(r'[^a-z0-9_-]', '', name.lower())}"[:100]
                        chunks.append({
                            "id": doc_id,
                            "title": title,
                            "content": content,
                            "source": "wfcd"
                        })
            except Exception as e:
                logger.error(f"WFCD MCP error fetching feed {category}: {e}")
        return chunks

