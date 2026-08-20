import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Essential community meta build knowledge base (can be extended dynamically via Overframe API or community feeds)
COMMUNITY_BUILDS = [
    {
        "id": "build-frame-saryn-prime-eso",
        "title": "Build: Saryn Prime - ESO / Map Nuke (Spore Build)",
        "content": """Warframe Build: Saryn Prime - Sanctuary Onslaught / Map Nuke
Core Focus: Range (200%+), Efficiency/Duration, Spore damage stacking.
Essential Mods:
- Aura: Growing Power / Corrosive Projection
- Exilus: Cunning Drift / Handspring
- Core: Overextended, Stretch, Transient Fortitude, Blind Rage, Umbral Intensify, Primed Continuity, Streamline, Adaptability / Rolling Guard
Helminth Subsume Option: Roar (over 4th ability) or Nourish for viral damage & energy sustain.
Archon Shards: 2 Crimson Shards (+Ability Strength), 3 Amber Shards (+Casting Speed / Energy on spawn).
Mechanics & Playstyle: Cast Spores (1st) on enemy, pop spores with Toxic Lash (3rd) or weapon, spread spores endlessly across room. Maintain Venom Dose buff for weapon elemental damage.""",
        "source": "warframe_builds"
    },
    {
        "id": "build-weapon-ignis-wraith-viral-hm",
        "title": "Build: Ignis Wraith - Steel Path Viral & Hunter Munitions",
        "content": """Weapon Build: Ignis Wraith (Primary Beam Rifle)
Core Focus: High Critical Chance, Viral Damage, Slash Proc generation.
Essential Mods:
- Serration (or Primary Merciless Arcane)
- Split Chamber / Galvanized Chamber (Multishot)
- Point Strike / Critical Delay (Critical Chance)
- Vital Sense (Critical Damage)
- Malignant Force (Toxic + Status Chance)
- Rime Rounds (Cold + Status Chance -> combines to Viral)
- Hunter Munitions (Slash procs on Crit)
- Vile Acceleration / Speed Trigger (Fire rate multiplier)
Arcane: Primary Merciless (Rank 5) or Primary Deadhead.
Mechanics: Fire continuous beam to apply high-stack Viral status (+300% damage to health) while Hunter Munitions forces armor-bypassing Slash damage over time.""",
        "source": "warframe_builds"
    },
    {
        "id": "build-weapon-nikana-prime-slash-combo",
        "title": "Build: Nikana Prime - Steel Path Slash Combo Melee",
        "content": """Weapon Build: Nikana Prime (Melee Katana)
Core Focus: 12x Combo Counter, Blood Rush Crit, Weeping Wounds Status.
Stance: Blind Justice
Essential Mods:
- Condition Overload (Base Damage per status type)
- Blood Rush (Critical Chance scaling with Combo)
- Weeping Wounds (Status Chance scaling with Combo)
- Organ Shatter (Critical Damage)
- Primed Reach (Range)
- Primed Fury / Quickening (Attack Speed)
- Carnis Mandible / Buzz Kill (Increased Slash ratio)
- Drifting Contact / Body Count (Combo Duration) or Naramon Focus School
Arcane: Melee Exposure or Melee Animosity.
Mechanics: Build 12x combo count quickly using stance neutral block combo. Blood Rush pushes crit rate above 200% (Red Crits) while forced slash procs bypass all Steel Path enemy armor.""",
        "source": "warframe_builds"
    },
    {
        "id": "build-frame-rhino-prime-steel-path",
        "title": "Build: Rhino Prime - Steel Path Iron Skin & Roar Support",
        "content": """Warframe Build: Rhino Prime - Steel Path Iron Skin Tank
Core Focus: Armor stacking for Iron Skin base math, Ability Strength.
Essential Mods:
- Ironclad Charge (Increases armor by % per enemy hit by Charge)
- Shrapnel (Allows recasting Iron Skin manually)
- Umbral Intensify, Transient Fortitude, Blind Rage (Ability Strength)
- Umbral Fiber, Armored Agility (Base Armor)
- Stretch (Roar range for team buff)
Helminth Subsume: Parasitic Armor over 4th ability (converts shields into massive bonus armor before casting Iron Skin).
Mechanics: Cast Charge into dense mob with Ironclad Charge to get +1000%+ armor, immediately cast Iron Skin to receive 100,000+ invulnerability health pool. Cast Roar to buff all weapon damage by +100%+.""",
        "source": "warframe_builds"
    }
]

from mcp_servers.base import BaseMCPServer

class BuildsMCPServer(BaseMCPServer):
    """MCP Server Adapter for Warframe Builds, mod setups, and gear set synergies."""

    @property
    def name(self) -> str:
        return "warframe_builds"

    @property
    def description(self) -> str:
        return "Curated community weapon/frame builds, Archon shard recommendations, and gear synergies"

    def fetch_data(self) -> List[Dict[str, Any]]:
        return self.fetch_builds()

    def fetch_builds(self) -> List[Dict[str, Any]]:
        return COMMUNITY_BUILDS

