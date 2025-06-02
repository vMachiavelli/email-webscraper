import os
import re
import csv
import time
import requests
from urllib.parse import urljoin, urlparse
from requests_html import HTMLSession, HTML

# --- CONFIGURATION ---
API_KEY    = os.environ.get("GOOGLE_API_KEY")   # Your Google API key
CX         = os.environ.get("GOOGLE_CX")        # Your Custom Search Engine ID
OUT_CSV    = "out.csv"                          # CSV containing agencies and emails from previous run
CSV_DEEP   = "out_deep.csv"                     # New CSV with results of deep search
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/115.0.0.0 Safari/537.36"
)
# ------------------------

EMAIL_RX      = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAILTO_RX     = re.compile(r'href=[\'"]mailto:([^\'"]+)[\'"]', re.IGNORECASE)

# New regex to detect "contact" pages in multiple languages/formats
CONTACT_RX    = re.compile(r"contac|contacto|contatto|kontakt|contato|contact-us|contacter", re.IGNORECASE)

session = HTMLSession()


def google_search_site(query):
    """
    Uses Google Custom Search API to look up `query`, excluding idealista.
    Returns first non-Idealista link or None.
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


def fetch_rendered_html(url):
    """
    Fetch and fully render a URL using requests_html. Returns HTML text or "".
    """
    print(f"    [DEBUG] Fetching & rendering: {url}")
    try:
        r = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        print(f"    [DEBUG] → HTTP status: {r.status_code}")
        r.html.render(timeout=10, sleep=2)
        print(f"    [DEBUG] → Render complete: {url} (length {len(r.html.html)} chars)")
        return r.html.html
    except Exception as e:
        print(f"    [DEBUG] → Render failed for {url}: {e}")
        return ""


def extract_emails(html):
    """
    Extracts email addresses (plain or mailto:) from HTML text.
    Returns sorted list of unique emails.
    """
    found = set(EMAIL_RX.findall(html))
    found |= set(MAILTO_RX.findall(html))
    emails = sorted(found)
    print(f"        [DEBUG] extract_emails: found {len(emails)} => {emails}")
    return emails


def get_internal_links(html, base_url):
    """
    From rendered HTML, extract all internal links (same domain as base_url).
    Returns a set of absolute URLs.
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
        if parsed.netloc == base_domain:
            normalized = abs_link.split('#')[0].rstrip('/')
            links.add(normalized)
    print(f"        [DEBUG] get_internal_links: found {len(links)} links on {base_url}")
    return links


def deep_search_agency(agency_name):
    """
    Perform a deep search for emails for a single agency:
    1) Use Google CSE to find homepage URL.
    2) Fetch and render homepage; extract emails.
    3) If none found, identify any contact‐page links first (via CONTACT_RX).
       – Render each contact link and check for emails.
       – If still none, iterate all other internal links (rendered) and check for emails.
    Returns list of found emails (possibly empty).
    """
    print(f"    [DEBUG] Starting deep_search_agency for: {agency_name}")
    query = f"{agency_name} real estate marbella -site:idealista.com -site:properstar.com -site:aplaceinthesun.com -site:linkedin.com -site:instagram.com, -site:facebook.com"
    site = google_search_site(query)    
    if not site:
        print("    [DEBUG] → No site found via CSE.")
        return []

    print(f"    [DEBUG] Homepage URL: {site}")
    # 1) Render homepage and extract emails
    html_home = fetch_rendered_html(site)
    emails = []
    if html_home:
        print("    [DEBUG] Extracting emails from rendered homepage...")
        emails = extract_emails(html_home)
        if emails:
            print(f"    [DEBUG] Emails found on homepage: {emails}")
            return emails
        else:
            print("    [DEBUG] No emails on homepage, searching for contact‐page links first.")

    # 2) Gather internal links from homepage
    internal_links = get_internal_links(html_home, site) if html_home else set()

    # 2a) Filter for contact‐type links first
    contact_links = [link for link in internal_links if CONTACT_RX.search(link)]
    print(f"        [DEBUG] Found {len(contact_links)} contact‐type links via regex.")
    for idx, link in enumerate(contact_links, 1):
        print(f"    [DEBUG] Fetching contact link {idx}/{len(contact_links)}: {link}")
        html_contact = fetch_rendered_html(link)
        if not html_contact:
            print(f"    [DEBUG] → Skipping (no HTML) for {link}")
            continue
        print(f"    [DEBUG] Extracting emails from contact page: {link}")
        found = extract_emails(html_contact)
        if found:
            print(f"    [DEBUG] Emails found on contact page {link}: {found}")
            return found
        else:
            print(f"    [DEBUG] No emails on contact page {link}, continuing.")
        time.sleep(1)

    # 2b) If still no emails, iterate all other internal links
    non_contact_links = [link for link in internal_links if link not in contact_links]
    print(f"        [DEBUG] Falling back to {len(non_contact_links)} non‐contact links.")
    for idx, link in enumerate(non_contact_links, 1):
        print(f"    [DEBUG] Fetching internal link {idx}/{len(non_contact_links)}: {link}")
        html_link = fetch_rendered_html(link)
        if not html_link:
            print(f"    [DEBUG] → Skipping (no HTML) for {link}")
            continue
        print(f"    [DEBUG] Extracting emails from: {link}")
        found = extract_emails(html_link)
        if found:
            print(f"    [DEBUG] Emails found on {link}: {found}")
            return found
        else:
            print(f"    [DEBUG] No emails on {link}, continuing.")
        time.sleep(1)

    print("    [DEBUG] Completed deep search, no emails found.")
    return []


def main():
    # ----------------------------------------------------------------------------
    # 1) Read out.csv with csv.reader
    # ----------------------------------------------------------------------------
    print("[INFO] Reading existing out.csv to find agencies missing all emails…")
    agency_email_map = {}  # agency_name -> list of all emails (could be empty)
    with open(OUT_CSV, newline="", encoding="utf-8") as csvfile:
        reader = csv.reader(csvfile)
        next(reader, None)  # skip header
        for row in reader:
            if not row:
                continue
            agency = row[0]
            email = row[-1].strip() if len(row) >= 2 else ""
            agency_email_map.setdefault(agency, []).append(email)

    missing_agencies = [
        agency
        for agency, emails in agency_email_map.items()
        if all(e == "" for e in emails)
    ]
    print(f"[INFO] Found {len(missing_agencies)} agencies with no email so far.")

    # ----------------------------------------------------------------------------
    # 2) Deep-search every missing agency
    # ----------------------------------------------------------------------------
    with open(CSV_DEEP, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(["agency", "email", "method"])  # method: "deep" or "none"

        for idx, agency in enumerate(missing_agencies, 1):
            print(f"\n[INFO] ({idx}/{len(missing_agencies)}) Deep searching: {agency}")
            emails = deep_search_agency(agency)
            if emails:
                for e in emails:
                    writer.writerow([agency, e, "deep"])
                    print(f"  [FOUND] {e}")
            else:
                writer.writerow([agency, "", "none"])
                print(f"  [NONE FOUND]")
            time.sleep(2)  # polite pause between agencies


if __name__ == "__main__":
    main()
