#!/usr/bin/env python3
import os
import re
import csv
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── CONFIG ─────────────────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX      = os.getenv("GOOGLE_CX")     # Custom Search Engine ID
if not GOOGLE_API_KEY or not GOOGLE_CX:
    raise RuntimeError("Set GOOGLE_API_KEY and GOOGLE_CX in your environment first!")

# ─── SESSION SETUP ───────────────────────────────────────────────────────────────
session = requests.Session()

# Retries for 403, 429 and server errors with exponential backoff
retries = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[403, 429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

# More “browser-like” headers
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.idealista.com/",
})

# Hit the homepage once to pick up any cookies Idealista sets
try:
    session.get("https://www.idealista.com", timeout=(5, 30))
except Exception:
    pass

AGG_BLACKLIST = {
    "kyero.com", "idealista.com", "realtor.com", "rightmove.co.uk",
    "spainhouses.net", "properstar.ca", "zoopla.co.uk", "spainestate.com",
}

email_rx   = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,6}\b")
contact_rx = re.compile(r"conta", re.IGNORECASE)

# ─── SCRAPE IDEALISTA AGENTS ────────────────────────────────────────────────────
def get_agent_names_idealista(location_slug: str) -> list[str]:
    """
    Scrape Idealista listing pages for agency names, paginating until no more listings.
    `location_slug` is the URL fragment like "torrevieja-alicante".
    """
    base_url = f"https://www.idealista.com/agencias-inmobiliarias/{location_slug}/inmobiliarias"
    names = []
    page = 1

    while True:
        url = base_url if page == 1 else f"{base_url}/pagina-{page}.htm"
        print(f"[DEBUG] Fetching Idealista page {page}: {url}")
        try:
            resp = session.get(url, timeout=(5, 30))
            resp.raise_for_status()
        except requests.HTTPError as e:
            print(f"[ERROR] HTTP error on Idealista page {page}: {e}")
            break
        except requests.RequestException as e:
            print(f"[ERROR] Request failed on Idealista page {page}: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        # adjust this selector if the DOM changes
        items = soup.select("a.item-link[data-testid='listing-title'], h3.item-title")
        page_names = []
        for el in items:
            name = el.get_text(strip=True)
            if name and name not in names:
                page_names.append(name)
                names.append(name)

        print(f"[DEBUG] Found {len(page_names)} new names on page {page}")
        if not page_names:
            break

        # stop when there’s no “Siguiente” button
        if not soup.find("a", attrs={"aria-label": re.compile(r"siguiente", re.IGNORECASE)}):
            break

        page += 1
        time.sleep(1)

    print(f"[DEBUG] Total agency names: {len(names)}")
    return names

# ─── GOOGLE SEARCH SITE ─────────────────────────────────────────────────────────
def google_search_site(company: str) -> Optional[str]:
    params = {"key": GOOGLE_API_KEY, "cx": GOOGLE_CX, "q": company, "num": 5}
    print(f"[DEBUG] Searching Google for '{company}'…")
    try:
        r = session.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=(5, 30))
        r.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Google search failed for '{company}': {e}")
        return None

    for item in r.json().get("items", []):
        link = item.get("link")
        if not link:
            continue
        host = urlparse(link).netloc.lower().removeprefix("www.")
        if host in AGG_BLACKLIST:
            print(f"[DEBUG] Skipping aggregator host: {host}")
            continue
        print(f"[DEBUG] Selected site for '{company}': {link}")
        return link
    return None

# ─── EMAIL EXTRACTION ────────────────────────────────────────────────────────────
def extract_emails_from_html(html: str) -> set[str]:
    return set(email_rx.findall(html))

def find_emails_on_site(url: str) -> set[str]:
    """Fetch homepage, footer, then ‘contact*’ page if needed."""
    try:
        r = session.get(url, timeout=(5, 30))
        r.raise_for_status()
    except:
        return set()

    # 1) homepage
    emails = extract_emails_from_html(r.text)
    if emails:
        print(f"[DEBUG] Emails on homepage {url}: {emails}")
        return emails

    # 2) footer snippet
    soup = BeautifulSoup(r.text, "html.parser")
    footer = soup.find("footer")
    snippet = footer.get_text("\n") if footer else r.text[-1500:]
    emails = extract_emails_from_html(snippet)
    if emails:
        print(f"[DEBUG] Emails in footer/tail of {url}: {emails}")
        return emails

    # 3) find a ‘contact*’ link
    contact_link = None
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a["href"]
        if contact_rx.search(text) or contact_rx.search(href):
            contact_link = urljoin(url, href)
            print(f"[DEBUG] Found contact link: {contact_link}")
            break

    if not contact_link:
        print(f"[DEBUG] No contact link found on {url}")
        return set()

    # 4) scrape contact page
    try:
        rc = session.get(contact_link, timeout=(5, 30))
        rc.raise_for_status()
    except Exception as e:
        print(f"[ERROR] Could not fetch contact page {contact_link}: {e}")
        return set()

    emails = extract_emails_from_html(rc.text)
    print(f"[DEBUG] Emails on contact page {contact_link}: {emails}")
    return emails

# ─── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    # Drop in any Idealista agencias URL here:
    target_url = "https://www.idealista.com/agencias-inmobiliarias/torrevieja-alicante/inmobiliarias"
    m = re.search(r"/agencias-inmobiliarias/([^/]+)/inmobiliarias", target_url)
    if not m:
        raise RuntimeError(f"Cannot parse slug from URL: {target_url}")
    slug = m.group(1)

    agents = get_agent_names_idealista(slug)
    rows = []
    for name in agents:
        site = google_search_site(name)
        if not site:
            continue
        emails = find_emails_on_site(site)
        for e in emails:
            if any(e.lower().endswith(ext) for ext in (".png", ".jpg", ".js", ".webp", ".jpeg", ".mpeg")):
                continue
            rows.append((name, site, e))

    # write CSV
    with open("agent_emails.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["company", "site", "email"])
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to agent_emails.csv")

if __name__ == "__main__":
    main()
