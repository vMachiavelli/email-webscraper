import os
import re
import csv
import time
import requests
import pandas as pd
from urllib.parse import urljoin, urlparse
from requests_html import HTMLSession, HTML

# --- CONFIGURATION ---
API_KEY    = os.environ.get("GOOGLE_API_KEY")    # Your Google API key
CX         = os.environ.get("GOOGLE_CX")         # Your Custom Search Engine ID
CSV_IN     = "idealista(1).csv"                  # Input CSV from Web Scraper
OUT_CSV    = "out_combined.csv"                  # Combined output CSV
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/115.0.0.0 Safari/537.36"
)
# ------------------------

# Regexes for extracting emails and matching “contact” links
EMAIL_RX      = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAILTO_RX     = re.compile(r'href=[\'"]mailto:([^\'"]+)[\'"]', re.IGNORECASE)
HREF_CONTA_RX = re.compile(r'href=[\'"]([^\'"]*contac[^\'"]*)[\'"]', re.IGNORECASE)
CONTACT_RX    = re.compile(r"contac|contacto|contatto|kontakt|contato|contact-us|contacter", 
                           re.IGNORECASE)

# Static fallback suffixes (no rendering)
CONTACT_SUFFIXES = (
    "contact", "contacto", "contact-us", "contac", "kontakt", "kontakt-oss"
)

# File extensions to skip when crawling internal links
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf",
    ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar"
}

session = HTMLSession()


def google_search_site(query):
    """
    Uses Google Custom Search API to look up `query`, excluding idealista.
    Returns the first non‐Idealista link or None.
    """
    print(f"    [DEBUG] CSE Query: {query}")
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={'key': API_KEY, 'cx': CX, 'q': query},
            timeout=10
        )
        print(f"    [DEBUG] → CSE HTTP status: {resp.status_code}")
        resp.raise_for_status()
        items = resp.json().get("items", [])
        print(f"    [DEBUG] → Number of CSE results: {len(items)}")
        for idx, item in enumerate(items):
            link = item.get("link")
            print(f"        [DEBUG] Result {idx+1}: {link}")
            if link and "idealista.com" not in link:
                print(f"    [DEBUG] → Using: {link}")
                return link
        print("    [DEBUG] → No non-Idealista link found in CSE results.")
        return None
    except Exception as e:
        print(f"    [DEBUG] Google CSE request failed: {e}")
        return None


def fetch_plain_html(url):
    """
    Simple GET (no JS rendering) and return raw HTML, or "" on failure.
    """
    print(f"    [DEBUG] Plain GET: {url}")
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        print(f"    [DEBUG] → HTTP status: {r.status_code}")
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"    [DEBUG] Plain GET failed for {url}: {e}")
        return ""


def fetch_rendered_html(url):
    """
    GET + .render() the URL via requests_html. Return rendered HTML or "" on failure.
    """
    print(f"    [DEBUG] Rendering: {url}")
    try:
        r = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        print(f"    [DEBUG] → HTTP status: {r.status_code}")
        r.html.render(timeout=10, sleep=2)
        rendered = r.html.html or ""
        print(f"    [DEBUG] → Render length: {len(rendered)} chars")
        return rendered
    except Exception as e:
        print(f"    [DEBUG] → Render failed for {url}: {e}")
        return ""

def extract_emails(html):
    """
    Return a sorted list of unique emails found in `html`.
    """
    found = set(EMAIL_RX.findall(html))
    found |= set(MAILTO_RX.findall(html))
    emails = sorted(found)
    print(f"        [DEBUG] extract_emails: found {len(emails)} => {emails}")
    return emails

def find_contact_links(html):
    """
    Return list of all hrefs matching the “contac…” regex in raw HTML.
    """
    links = HREF_CONTA_RX.findall(html)
    print(f"        [DEBUG] find_contact_links: found {len(links)} raw hrefs")
    return links

def get_internal_links(html, base_url):
    """
    Extract all internal links (same domain) from rendered HTML, skipping
    any URL whose path ends with a known non‐HTML extension.
    Returns a set of normalized absolute URLs.
    """
    base_domain = urlparse(base_url).netloc
    links = set()
    parsed_html = HTML(html=html)
    for a in parsed_html.find("a"):
        href = a.attrs.get("href", "")
        if not href or href.startswith("mailto:"):
            continue
        abs_link = urljoin(base_url, href)
        parsed = urlparse(abs_link)
        if parsed.netloc != base_domain:
            continue
        ext = os.path.splitext(parsed.path)[1].lower()
        if ext in SKIP_EXTENSIONS:
            # Skip links to images, PDFs, docx, etc.
            continue
        normalized = abs_link.split('#')[0].rstrip('/')
        links.add(normalized)
    print(f"        [DEBUG] get_internal_links: found {len(links)} valid links on {base_url}")
    return links

def deep_search_agency(agency_name, homepage_html=None, homepage_url=None):
    """
    Deep crawl: renders homepage if not provided, extracts emails.
    Then prioritizes contact‐type links (via CONTACT_RX), renders and checks.
    Finally, if still none, renders each remaining internal link until an email appears.
    Returns list of found emails (or []).
    """
    print(f"    [DEBUG] Starting deep_search_agency for: {agency_name}")

    # If homepage was already rendered once, reuse it; else fetch+render now
    if not homepage_html and homepage_url:
        homepage_html = fetch_rendered_html(homepage_url)

    # Step 1: Extract from rendered homepage
    if homepage_html:
        print("    [DEBUG] Deep‐search: extracting from rendered homepage")
        emails = extract_emails(homepage_html)
        if emails:
            print(f"    [DEBUG] Deep‐search found on homepage: {emails}")
            return emails

    # Step 2: Gather internal links (skipping non‐HTML resources)
    internal_links = set()
    if homepage_html and homepage_url:
        internal_links = get_internal_links(homepage_html, homepage_url)

    # 2a: Prioritize contact‐type links
    contact_links = [link for link in internal_links if CONTACT_RX.search(link)]
    print(f"        [DEBUG] Deep‐search: found {len(contact_links)} contact‐type links")
    for idx, link in enumerate(contact_links, 1):
        print(f"    [DEBUG] Deep‐search rendering contact {idx}/{len(contact_links)}: {link}")
        html_contact = fetch_rendered_html(link)
        if not html_contact:
            print(f"    [DEBUG] → No HTML for {link}, skipping")
            continue
        print(f"    [DEBUG] Deep‐search extracting from {link}")
        found = extract_emails(html_contact)
        if found:
            print(f"    [DEBUG] Deep‐search found on contact page {link}: {found}")
            return found
        time.sleep(1)

    # 2b: Fallback to all other internal links
    non_contact_links = [link for link in internal_links if link not in contact_links]
    print(f"        [DEBUG] Deep‐search: {len(non_contact_links)} non‐contact links left")
    for idx, link in enumerate(non_contact_links, 1):
        print(f"    [DEBUG] Deep‐search rendering link {idx}/{len(non_contact_links)}: {link}")
        html_link = fetch_rendered_html(link)
        if not html_link:
            print(f"    [DEBUG] → No HTML for {link}, skipping")
            continue
        print(f"    [DEBUG] Deep‐search extracting from {link}")
        found = extract_emails(html_link)
        if found:
            print(f"    [DEBUG] Deep‐search found on {link}: {found}")
            return found
        time.sleep(1)

    print("    [DEBUG] Deep‐search completed, no emails found")
    return []

def main():
    # 1) Load the Idealista CSV and grab the "names" column
    df = pd.read_csv(CSV_IN, encoding="utf-8")
    if "names" not in df.columns:
        print(f"[ERROR] Input CSV has no 'names' column. Found: {df.columns.tolist()}")
        return
    agency_names = df["names"].dropna().astype(str).tolist()

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(["agency", "email", "method"])

        for idx, name in enumerate(agency_names, 1):
            name = name.strip()
            if not name:
                continue

            print(f"\n[INFO] ({idx}/{len(agency_names)}) Processing: {name}")
            # 2) Google CSE for homepage URL
            query = f"{name} real estate marbella -site:idealista.com -site:linkedin.com -site:instagram.com -site:facebook.com -site:properstar.com -site:aplaceinthesun.com"
            site = google_search_site(query)
            if not site:
                print(f"    [WARN] No site found for {name}")
                writer.writerow([name, "", "none"])
                time.sleep(1)
                continue

            emails = []
            method = ""
            rendered_home = ""  # store if we render homepage

            # Step A: Plain GET homepage
            html_plain = fetch_plain_html(site)
            if html_plain:
                emails = extract_emails(html_plain)
                if emails:
                    method = "plain"
                    print(f"    [DEBUG] Found in plain HTML: {emails}")

            # Step B: If still none, contact‐links in raw HTML
            if not emails and html_plain:
                contac_hrefs = find_contact_links(html_plain)
                print(f"    [DEBUG] Plain HTML contact‐links: {contac_hrefs}")
                for href in contac_hrefs:
                    full_url = urljoin(site, href)
                    html_contact = fetch_rendered_html(full_url)
                    if html_contact:
                        emails = extract_emails(html_contact)
                        if emails:
                            method = "plain-contact"
                            print(f"    [DEBUG] Found on contact‐type page (plain) {full_url}: {emails}")
                            break

            # Step C: If still none, render homepage
            if not emails:
                rendered_home = fetch_rendered_html(site)
                if rendered_home:
                    emails = extract_emails(rendered_home)
                    if emails:
                        method = "rendered"
                        print(f"    [DEBUG] Found in rendered homepage: {emails}")

            # Step D: If still none, contact‐links in rendered HTML
            if not emails and rendered_home:
                contac_hrefs = find_contact_links(rendered_home)
                print(f"    [DEBUG] Rendered HTML contact‐links: {contac_hrefs}")
                for href in contac_hrefs:
                    full_url = urljoin(site, href)
                    html_contact = fetch_rendered_html(full_url)
                    if html_contact:
                        emails = extract_emails(html_contact)
                        if emails:
                            method = "rendered-contact"
                            print(f"    [DEBUG] Found on contact‐type page (rendered) {full_url}: {emails}")
                            break

            # Step E: If still none, static /contact… suffixes
            if not emails:
                for suf in CONTACT_SUFFIXES:
                    candidate = urljoin(site.rstrip("/") + "/", suf)
                    try:
                        r = requests.get(candidate, headers={"User-Agent": USER_AGENT}, timeout=10)
                        r.raise_for_status()
                        txt = r.text
                        found = extract_emails(txt)
                        if found:
                            emails = found
                            method = "static-suffix"
                            print(f"    [DEBUG] Found via static suffix {candidate}: {emails}")
                            break
                    except Exception:
                        continue

            # Step F: If still none, deep‐search internal links
            if not emails:
                print("    [DEBUG] No email found in A–E, falling back to deep‐search.")
                emails = deep_search_agency(name, homepage_html=rendered_home, homepage_url=site)
                if emails:
                    method = "deep"
                else:
                    method = "none"

            # Write results to CSV
            if emails:
                for e in emails:
                    writer.writerow([name, e, method])
                print(f"  [FOUND] {emails} (method={method})")
            else:
                writer.writerow([name, "", method])
                print(f"  [NONE FOUND] (method={method})")

            out_f.flush()
            time.sleep(1)  # polite pause between agencies


if __name__ == "__main__":
    main()
