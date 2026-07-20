"""Simple async website crawler. Downloads up to N pages, extracts readable text,
chunks it, and returns list of (source_url, title, chunk_text)."""
import asyncio
import re
from urllib.parse import urljoin, urlparse
from typing import List, Tuple
import aiohttp
from bs4 import BeautifulSoup

MAX_PAGES = 15
CHUNK_SIZE = 700  # approx words
CHUNK_OVERLAP = 80


def _normalize_url(base: str) -> str:
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    return base.rstrip("/")


def _same_domain(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc.replace("www.", "") == urlparse(b).netloc.replace("www.", "")
    except Exception:
        return False


def _extract_text(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg", "iframe"]):
        tag.decompose()
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return title, text


def _chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + size])
        if len(chunk.strip()) > 40:
            chunks.append(chunk)
        i += size - overlap
    return chunks


async def _fetch(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                               headers={"User-Agent": "AIEmployeeBot/1.0"}) as r:
            if r.status != 200 or "text/html" not in r.headers.get("Content-Type", ""):
                return ""
            return await r.text()
    except Exception:
        return ""


async def crawl_site(start_url: str, max_pages: int = MAX_PAGES) -> List[Tuple[str, str, str]]:
    start_url = _normalize_url(start_url)
    seen: set[str] = set()
    queue: list[str] = [start_url]
    results: list[Tuple[str, str, str]] = []

    async with aiohttp.ClientSession() as session:
        while queue and len(seen) < max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            html = await _fetch(session, url)
            if not html:
                continue
            title, text = _extract_text(html)
            for c in _chunk(text):
                results.append((url, title, c))

            # discover links
            try:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    link = urljoin(url, a["href"]).split("#")[0]
                    if link.startswith("http") and _same_domain(link, start_url) and link not in seen:
                        if len(queue) + len(seen) < max_pages * 2:
                            queue.append(link)
            except Exception:
                pass
    return results
