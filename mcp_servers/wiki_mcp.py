import urllib.request
import urllib.parse
import json
import re
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

WIKI_PAGES = ["Damage", "Status_Effect", "Affinity", "Mastery_Rank"]

def clean_wikitext(text: str) -> str:
    text = re.sub(r'<[^>]*>', '', text)
    for _ in range(3):
        text = re.sub(r'\{\{[^{}]*\}\}', '', text)
    text = re.sub(r'\[\[[^|\]]*\|([^\]]*)\]\]', r'\1', text)
    text = re.sub(r'\[\[([^\]]*)\]\]', r'\1', text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r'\[\d+\]', '', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()

def chunk_wikitext(page_title: str, text: str) -> List[Dict[str, Any]]:
    sections = []
    current_title = "Overview"
    current_content = []
    
    for line in text.split('\n'):
        match = re.match(r'^==+\s*(.*?)\s*==+$', line)
        if match:
            if current_content:
                sections.append({"title": f"Wiki: {page_title} - {current_title}", "content": "\n".join(current_content).strip()})
            current_title = match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)
            
    if current_content:
        sections.append({"title": f"Wiki: {page_title} - {current_title}", "content": "\n".join(current_content).strip()})
        
    cleaned = []
    for s in sections:
        body = clean_wikitext(s["content"])
        if len(body) > 100:
            cleaned.append({
                "title": s["title"],
                "content": f"{s['title']}\n\n{body}"
            })
    return cleaned

from mcp_servers.base import BaseMCPServer

class WikiMCPServer(BaseMCPServer):
    """MCP Server Adapter for Warframe Fandom Wiki guides."""

    @property
    def name(self) -> str:
        return "fandom_wiki"

    @property
    def description(self) -> str:
        return "Warframe Fandom Wiki mechanics and guide pages"

    def fetch_data(self) -> List[Dict[str, Any]]:
        return self.fetch_pages()

    def fetch_pages(self) -> List[Dict[str, Any]]:
        chunks = []
        for page in WIKI_PAGES:
            url = f"https://warframe.fandom.com/api.php?action=parse&page={urllib.parse.quote(page)}&prop=wikitext&format=json"
            req = urllib.request.Request(url, headers={"User-Agent": "OrdisMCP/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=15) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
                    if wikitext:
                        sec_chunks = chunk_wikitext(page, wikitext)
                        for idx, sec in enumerate(sec_chunks):
                            chunks.append({
                                "id": f"wiki-{page.lower()}-sec{idx}",
                                "title": sec["title"],
                                "content": sec["content"],
                                "source": "fandom_wiki"
                            })
            except Exception as e:
                logger.error(f"Wiki MCP error fetching page {page}: {e}")
        return chunks

