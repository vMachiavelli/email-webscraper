
import re
import csv
import time
import requests
import pandas as pd
from urllib.parse import urljoin, urlparse
from requests_html import HTMLSession

# --- CONFIGURATION ---
API_KEY   = "AIzaSyAHSMkpOOnAIGKisU954yat0iBBU35CbMg"   # Your Google API key
CX        = "f3fa5c4bdb4b74bac"                        # Your Custom Search Engine ID
OUT_CSV   = "out.csv"                                  # CSV containing agencies and emails from previous run
CSV_DEEP  = "out_deep.csv"                             # New CSV with results of deep search
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/115.0.0.0 Safari/537.36"
)

EMAIL_RX      = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAILTO_RX     = re.compile(r'href=[\'"]mailto:([^\'"]+)[\'"]', re.IGNORECASE)

session = HTMLSession()

def google_search_site(query):
    """
    Uses Google Custom Search API to look up `query`, excluding idealista.
    Returns first non-Idealista link or None.
    """
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={'key': API_KEY, 'cx': CX, 'q': query},
            timeout=10
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            link = item.get("link")
            if link and "idealista.com" not in link:
                return link
    except Exception as e:
        print(f"[DEBUG] CSE request failed for '{query}': {e}")
    return None

def fetch_rendered_html(url):
    """
    Fetch and fully render a URL using requests_html. Returns HTML text or "".
    """
    try:
        r = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        r.html.render(timeout=10, sleep=2)
        return r.html.html
    except Exception as e:
        print(f"[DEBUG] Render failed for {url}: {e}")
        return ""

def extract_emails(html):
    """
    Extracts email addresses (plain or mailto:) from HTML text.
    Returns sorted list of unique emails.
    """
    emails = set(EMAIL_RX.findall(html))
    emails |= set(MAILTO_RX.findall(html))
    return sorted(emails)

def get_internal_links(html, base_url):
    """
    From rendered HTML, extract all internal links (same domain as base_url).
    Returns a set of absolute URLs.
    """
    base_domain = urlparse(base_url).netloc
    links = set()
    # We'll use requests_html to parse
    parsed_html = HTMLSession().parse(html)
    for a in parsed_html.find("a"):
        href = a.attrs.get("href", "")
        if not href or href.startswith("mailto:"):
            continue
        abs_link = urljoin(base_url, href)
        parsed = urlparse(abs_link)
        if parsed.netloc == base_domain:
            normalized = abs_link.split('#')[0].rstrip('/')
            links.add(normalized)
    return links

def deep_search_agency(agency_name):
    """
    Perform a deep search for emails for a single agency:
    1) Use Google CSE to find homepage URL.
    2) Fetch and render homepage; extract emails.
    3) If none found, get all internal links from homepage and fetch each (rendered),
       stopping once an email is located or all links exhausted.
    Returns list of found emails (possibly empty).
    """
    query = f"{agency_name} real estate marbella -site:idealista.com"
    site = google_search_site(query)
    if not site:
        return []

    # 1) Render homepage and extract emails
    html_home = fetch_rendered_html(site)
    emails = []
    if html_home:
        emails = extract_emails(html_home)
        if emails:
            return emails

    # 2) Gather internal links from homepage
    internal_links = get_internal_links(html_home, site) if html_home else set()
    for link in internal_links:
        html_link = fetch_rendered_html(link)
        if not html_link:
            continue
        found = extract_emails(html_link)
        if found:
            return found
        time.sleep(1)

    return []

def main():
    # Load out.csv and identify agencies missing all emails
    df = pd.read_csv(OUT_CSV, encoding="utf-8")
    grouped = df.groupby('agency')['email'].apply(lambda emails: all(str(e).strip() == '' for e in emails))
    missing_agencies = grouped[grouped].index.tolist()

    # Prepare output CSV
    with open(CSV_DEEP, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(["agency", "email", "method"])  # method: "deep" or "none"

        for agency in missing_agencies:
            print(f"[INFO] Deep searching: {agency}")
            emails = deep_search_agency(agency)
            if emails:
                for e in emails:
                    writer.writerow([agency, e, "deep"])
                    print(f"  [FOUND] {e}")
            else:
                writer.writerow([agency, "", "none"])
                print(f"  [NONE FOUND]")
            time.sleep(2)

if __name__ == "__main__":
    main()
