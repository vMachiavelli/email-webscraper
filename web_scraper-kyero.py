#!/usr/bin/env python3
import os
import re
import csv
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX      = os.getenv("GOOGLE_CX")
if not GOOGLE_API_KEY or not GOOGLE_CX:
    raise RuntimeError("Set GOOGLE_API_KEY and GOOGLE_CX in your environment first!")

# ─── SESSION SETUP ───────────────────────────────────────────────────────────────
session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[403, 429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://",  HTTPAdapter(max_retries=retries))
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Referer":         "https://www.idealista.com/",
})

# ─── HELPERS & REGEXES ──────────────────────────────────────────────────────────
email_rx   = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,6}\b")
contact_rx = re.compile(r"conta", re.IGNORECASE)
web_rx     = re.compile(r"(sitio web|web|website|ir a su página web)", re.IGNORECASE)
AGG_BLACKLIST = {
    "kyero.com","idealista.com","realtor.com","rightmove.co.uk",
    "spainhouses.net","properstar.ca","zoopla.co.uk","spainestate.com",
}

def extract_emails_from_html(html: str) -> set[str]:
    return set(email_rx.findall(html))

def find_emails_on_site(url: str) -> set[str]:
    print(f"[DEBUG] → extracting emails from {url}")
    try:
        r = session.get(url, timeout=(5,30)); r.raise_for_status()
    except Exception as e:
        print(f"[DEBUG]    failed to fetch {url}: {e}")
        return set()

    # 1) homepage
    emails = extract_emails_from_html(r.text)
    if emails:
        print(f"[DEBUG]    found on homepage: {emails}")
        return emails

    # 2) footer snippet
    soup = BeautifulSoup(r.text, "html.parser")
    footer = soup.find("footer")
    snippet = footer.get_text("\n") if footer else r.text[-1500:]
    emails = extract_emails_from_html(snippet)
    if emails:
        print(f"[DEBUG]    found in footer: {emails}")
        return emails

    # 3) contact page fallback
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        link = urljoin(url, a["href"])
        if contact_rx.search(text) or contact_rx.search(a["href"]):
            print(f"[DEBUG]    following contact link: {link}")
            try:
                rc = session.get(link, timeout=(5,30)); rc.raise_for_status()
                found = extract_emails_from_html(rc.text)
                print(f"[DEBUG]    found on contact page: {found}")
                return found
            except Exception as e:
                print(f"[DEBUG]    contact fetch failed: {e}")
                return set()

    print(f"[DEBUG]    no emails found at {url}")
    return set()

def google_search_site(query: str) -> Optional[str]:
    print(f"[DEBUG] → google searching: {query}")
    params = {"key": GOOGLE_API_KEY, "cx": GOOGLE_CX, "q": query, "num": 5}
    try:
        r = session.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=(5,30))
        r.raise_for_status()
    except Exception as e:
        print(f"[DEBUG]    google search failed: {e}")
        return None

    for item in r.json().get("items", []):
        link = item.get("link")
        host = urlparse(link).netloc.lower().removeprefix("www.")
        if link and host not in AGG_BLACKLIST:
            print(f"[DEBUG]    google picked: {link}")
            return link
    print(f"[DEBUG]    no suitable google result")
    return None

def find_website_url(pro_url: str) -> Optional[str]:
    print(f"[DEBUG] → scanning Pro page for Web link: {pro_url}")
    try:
        r = session.get(pro_url, timeout=(5,30)); r.raise_for_status()
    except Exception as e:
        print(f"[DEBUG]    Pro page fetch failed: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if web_rx.search(a.get_text(" ", strip=True)):
            site = urljoin(pro_url, a["href"])
            print(f"[DEBUG]    found Web link: {site}")
            return site

    print(f"[DEBUG]    no Web link on Pro page")
    return None

# ─── PAGINATION VIA /pagina-N LINKS ─────────────────────────────────────────────
def get_agent_pro_pages(location_slug: str) -> list[tuple[str,str]]:
    """
    Scrape Idealista listing pages, extract agencies from the expert section
    and any stray /pro/... links, then follow /pagina-N or /pagina-N.htm links
    in ascending order until all pages are visited.
    """
    base_url      = f"https://www.idealista.com/agencias-inmobiliarias/{location_slug}/inmobiliarias"
    next_url      = base_url
    agencies      = []
    visited_pages = {1}

    while next_url:
        print(f"[DEBUG] Fetching: {next_url}")
        try:
            resp = session.get(next_url, timeout=(5,30))
            resp.raise_for_status()
        except Exception as e:
            print(f"[DEBUG]    fetch failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1) expert section
        section = soup.select_one("section.agency-list.zone-experts-list")
        if section:
            cards = section.select("article.zone-experts-agency-card")
            print(f"[DEBUG]    found {len(cards)} agency cards in expert section")
            for card in cards:
                pro_url = card.get("data-microsite-url")
                link    = card.select_one("span.agency-name a[role=heading]")
                if not pro_url or not link:
                    continue
                name = link.get_text(strip=True)
                if name and pro_url not in [u for _,u in agencies]:
                    agencies.append((name, pro_url))
                    print(f"[DEBUG]    ➕ {name}: {pro_url}")

        # 2) stray /pro/... links
        print("[DEBUG]    scanning for extra Pro links on page")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.match(r"^https?://www\.idealista\.com/pro/[^/]+/?$", href):
                name = a.get_text(strip=True)
                if name and href not in [u for _,u in agencies]:
                    agencies.append((name, href))
                    print(f"[DEBUG]    (extra) ➕ {name}: {href}")

        # 3) collect all pagina-N or pagina-N.htm links
        page_links = []
        for a in soup.find_all("a", href=True):
            m = re.search(r'pagina-(\d+)(?:\.htm)?', a["href"])
            if m:
                num = int(m.group(1))
                page_links.append((num, a["href"]))
        print(f"[DEBUG]    pagination links found: {[n for n,_ in page_links]}")

        # 4) follow the smallest unvisited page
        next_url = None
        for num, href in sorted(page_links):
            if num not in visited_pages:
                visited_pages.add(num)
                next_url = urljoin(base_url, href)
                print(f"[DEBUG]    following page {num} → {next_url}")
                time.sleep(1)
                break

        if not next_url:
            print("[DEBUG]    no more pagina-N links; stopping pagination")
            break

    print(f"[DEBUG] Completed scraping Pro pages: {len(agencies)} total")
    return agencies

# ─── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    target_url = "https://www.idealista.com/agencias-inmobiliarias/orihuela-alicante/inmobiliarias"
    m = re.search(r"/agencias-inmobiliarias/(.+?)/inmobiliarias", target_url)
    if not m:
        raise RuntimeError(f"Cannot parse slug from URL: {target_url}")
    slug = m.group(1)

    agencies = get_agent_pro_pages(slug)
    rows = []

    for name, pro_url in agencies:
        site = find_website_url(pro_url)
        if not site:
            query = f"{name} real estate {slug.replace('/', ' ')}"
            site = google_search_site(query)
        if not site:
            print(f"[DEBUG] skipping {name}, no site")
            continue

        emails = find_emails_on_site(site)
        if not emails:
            print(f"[DEBUG] no emails for {name}")
        for email in emails:
            if not email.lower().endswith((".png", ".jpg", ".js", ".webp", ".jpeg", ".mpeg")):
                rows.append((name, site, email))
                print(f"[DEBUG] saved: {name} | {site} | {email}")

    with open("agent_emails.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["company", "site", "email"])
        writer.writerows(rows)

    print(f"[DEBUG] Wrote {len(rows)} rows to agent_emails.csv")

if __name__ == "__main__":
    main()
