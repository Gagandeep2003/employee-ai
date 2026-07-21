"""Async website crawler. Downloads up to N pages, strips boilerplate/duplicate
chrome (nav, cookie-consent banners, footers) that would otherwise pollute
every chunk, prioritizes business-relevant pages (services, appointments,
contact) over utility pages (login, cart, track-order), and drops
near-duplicate pages -- so the knowledge base ends up dense with real
content instead of the same repeated menu and cookie notice.
"""
import asyncio
import hashlib
import heapq
import re
from collections import Counter
from itertools import count
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode
from typing import List, Tuple
import aiohttp
from bs4 import BeautifulSoup, Comment

MAX_PAGES = 15
CHUNK_SIZE = 700  # approx words
CHUNK_OVERLAP = 80
MIN_LINE_LEN = 15  # shorter lines are almost always nav labels/buttons, not content

# Priority buckets for the crawl queue -- lower number = crawled sooner. An AI
# receptionist needs "what do you offer / how much / how do I book" far more
# than "login" or "track my order", so the limited page budget is actively
# steered toward the former instead of first-come-first-served link order.
HIGH_PRIORITY_HINTS = [
    "about", "service", "treatment", "product", "menu", "pricing", "price",
    "book", "appointment", "booking", "contact", "faq", "doctor", "team",
    "location", "hours", "gallery", "specialt", "consult",
]
LOW_PRIORITY_HINTS = [
    "login", "log-in", "signin", "sign-in", "signup", "sign-up", "register",
    "cart", "checkout", "wishlist", "account", "my-account", "track-order",
    "track_order", "trackorder", "logout", "password", "compare",
]
LEGAL_HINTS = ["privacy", "terms", "cookie-policy", "disclaimer", "refund-policy",
              "return-policy", "shipping-policy"]

# Boilerplate containers many sites mark with a class/id keyword rather than a
# semantic <nav>/<header>/<footer> tag -- tag-name removal alone misses these,
# which is why identical menu/cookie-banner text was showing up inside almost
# every crawled chunk. Kept intentionally specific/compound (not bare words
# like "menu" or "header") to avoid false-positiving on real content sections
# such as a restaurant's own "food-menu" or a page's "page-header" title block.
BOILERPLATE_KEYWORDS = [
    "site-header", "site-footer", "sitewide-header", "sitewide-footer",
    "top-bar", "topbar", "navbar", "nav-menu", "main-nav", "mobile-nav",
    "mobile-menu", "primary-menu", "menu-toggle", "hamburger",
    "cookie-consent", "cookie-banner", "cookie-notice", "cookie-law-info",
    "cky-", "gdpr-consent", "consent-banner", "consent-manager", "onetrust",
    "cookiebot", "cookieyes", "termly", "iubenda",
    "newsletter-signup", "subscribe-box", "subscribe-form",
    "breadcrumb", "back-to-top", "scroll-to-top",
    "social-share", "share-buttons", "social-icons",
    "site-search", "widget-area", "sidebar-widget", "announcement-bar",
]

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                   "fbclid", "gclid", "ref", "referrer", "source", "session", "sid", "_ga"}


def _normalize_url(base: str) -> str:
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    return base.rstrip("/")


def _same_domain(a: str, b: str) -> bool:
    try:
        return urlparse(a).netloc.replace("www.", "") == urlparse(b).netloc.replace("www.", "")
    except Exception:
        return False


def _canonicalize(url: str) -> str:
    """Strips tracking params, fragments, and trailing slashes, and lowercases
    host+path -- so /login, /login/, and /login?utm_source=footer are all
    recognized as the same page instead of being crawled and indexed three
    times over."""
    try:
        parsed = urlparse(url)
        path = (parsed.path.rstrip("/") or "/").lower()
        netloc = parsed.netloc.replace("www.", "").lower()
        query_pairs = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in TRACKING_PARAMS]
        canon = f"{parsed.scheme}://{netloc}{path}"
        if query_pairs:
            canon += f"?{urlencode(sorted(query_pairs))}"
        return canon
    except Exception:
        return url


def _priority(url: str, link_text: str) -> int:
    haystack = f"{url} {link_text}".lower()
    if any(h in haystack for h in HIGH_PRIORITY_HINTS):
        return 0
    if any(h in haystack for h in LOW_PRIORITY_HINTS):
        return 3
    if any(h in haystack for h in LEGAL_HINTS):
        return 2
    return 1


def _is_boilerplate_container(tag) -> bool:
    if tag.attrs is None:  # already decomposed (its parent was removed this pass)
        return False
    ident = " ".join(tag.get("class", []) + [tag.get("id", "") or ""]).lower()
    return any(kw in ident for kw in BOILERPLATE_KEYWORDS)


def _extract_lines(html: str) -> Tuple[str, List[str]]:
    """Returns (title, lines) where each line is one text node from the page,
    in document order -- preserving this granularity (rather than joining
    everything into one blob) is what lets the boilerplate passes below
    recognize "Home", "About", "Cart" etc. as individually repeated/low-value,
    even when the source HTML has no punctuation between nav items."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg", "iframe", "form", "button"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    for tag in soup.find_all(True):
        if tag.name in ("html", "body"):
            continue
        if _is_boilerplate_container(tag):
            tag.decompose()

    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup
    raw = main.get_text(separator="\n", strip=True)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in raw.split("\n")]
    lines = [ln for ln in lines if len(ln) >= MIN_LINE_LEN]
    return title, lines


def _strip_cross_page_boilerplate(pages: List[Tuple[str, str, List[str]]]) -> List[Tuple[str, str, List[str]]]:
    """Second pass, after all pages are fetched: any line that appears
    near-identically on most pages is site-wide chrome (cookie-consent
    paragraphs, footer taglines, repeated CTAs) that survived the structural
    removal above -- strip it so each page's indexed text is dominated by
    what's actually unique to that page."""
    if len(pages) < 3:
        return pages
    line_counts = Counter()
    for _, _, lines in pages:
        line_counts.update(set(lines))  # count each line once per page, not per occurrence

    threshold = max(3, int(len(pages) * 0.5))
    boilerplate = {ln for ln, c in line_counts.items() if c >= threshold}
    if not boilerplate:
        return pages
    return [(url, title, [ln for ln in lines if ln not in boilerplate]) for url, title, lines in pages]


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
    seen_canonical: set = set()
    content_hashes: set = set()
    counter = count()
    # heap items: (priority, insertion_seq, url) -- insertion_seq keeps FIFO
    # order within a priority tier and guarantees heapq never needs to fall
    # back to comparing two URL strings against each other.
    heap: list = [(0, next(counter), start_url)]
    pages: List[Tuple[str, str, List[str]]] = []  # (url, title, lines) before boilerplate pass 2 + chunking

    async with aiohttp.ClientSession() as session:
        while heap and len(seen_canonical) < max_pages:
            _, _, url = heapq.heappop(heap)
            canon = _canonicalize(url)
            if canon in seen_canonical:
                continue
            seen_canonical.add(canon)

            html = await _fetch(session, url)
            if not html:
                continue
            title, lines = _extract_lines(html)

            joined = " ".join(lines)
            if len(joined) > 60:
                content_hash = hashlib.sha1(joined[:2000].encode("utf-8", "ignore")).hexdigest()
                if content_hash not in content_hashes:
                    content_hashes.add(content_hash)
                    pages.append((url, title, lines))
                # else: near-duplicate of a page already indexed under a
                # different URL -- skip rather than index the same content twice

            try:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    link = urljoin(url, a["href"]).split("#")[0]
                    if not link.startswith("http") or not _same_domain(link, start_url):
                        continue
                    link_canon = _canonicalize(link)
                    if link_canon in seen_canonical:
                        continue
                    if len(heap) + len(seen_canonical) >= max_pages * 3:
                        continue
                    prio = _priority(link, a.get_text(" ", strip=True) or "")
                    heapq.heappush(heap, (prio, next(counter), link))
            except Exception:
                pass

    pages = _strip_cross_page_boilerplate(pages)

    results: List[Tuple[str, str, str]] = []
    for url, title, lines in pages:
        text = " ".join(lines)
        for c in _chunk(text):
            results.append((url, title, c))
    return results
