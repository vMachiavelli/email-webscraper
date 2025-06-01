import re
import csv
import time
import requests
import pandas as pd
from urllib.parse import urljoin
from requests_html import HTMLSession

# --- CONFIGURE THESE ---
API_KEY   = "AIzaSyAHSMkpOOnAIGKisU954yat0iBBU35CbMg"   # ← your real API key
CX        = "f3fa5c4bdb4b74bac"                        # ← your real CSE ID
CSV_IN    = "idealista(1).csv"                         # input CSV from Web Scraper
CSV_OUT   = "out.csv"                                  # output CSV (agency, email)
# ------------------------

EMAIL_RX      = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAILTO_RX     = re.compile(r'href=[\'"]mailto:([^\'"]+)[\'"]', re.IGNORECASE)
HREF_CONTA_RX = re.compile(r'href=[\'"]([^\'"]*contac[^\'"]*)[\'"]', re.IGNORECASE)

# Fallback contact suffixes (no rendering)
CONTACT_SUFFIXES = (
    "contact", "contacto", "contact-us", "contac", "kontakt", "kontakt-oss"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/115.0.0.0 Safari/537.36"
)

session = HTMLSession()


def google_search_site(query):
    """
    Use Google Custom Search API to find the first result NOT on idealista.com.
    Returns that URL or None.
    """
    print(f"    [DEBUG] Google CSE query: {query}")
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={'key': API_KEY, 'cx': CX, 'q': query},
            timeout=10
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        for item in items:
            href = item.get("link")
            if href and "idealista.com" not in href:
                print(f"    [DEBUG] → CSE returned: {href}")
                return href
        print("    [DEBUG] → No non-Idealista link found in CSE items.")
        return None
    except Exception as e:
        print(f"    [DEBUG] Google CSE request failed: {e}")
        return None


def fetch_plain_html(url):
    """
    Do a simple requests.get (no JS rendering) and return raw HTML text.
    """
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"    [DEBUG] Plain GET failed for {url}: {e}")
        return ""


def fetch_rendered_html(url):
    """
    Use requests_html to GET + .render() the URL. Returns rendered HTML or "" if it fails.
    """
    try:
        r = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        r.html.render(timeout=10, sleep=2)
        return r.html.html
    except Exception as e:
        print(f"    [DEBUG] → render failed for {url}: {e}")
        return ""


def extract_emails(html):
    """
    Returns a sorted list of unique emails found in the raw HTML string.
    """
    emails = set(EMAIL_RX.findall(html))
    emails |= set(MAILTO_RX.findall(html))
    return sorted(emails)


def find_contact_links(html):
    """
    Returns a list of hrefs matching our "contac" regex (e.g. /contact, /contacto, etc.).
    """
    return HREF_CONTA_RX.findall(html)


def main():
    # 1) Load the Idealista CSV (with a "names" column)
    df = pd.read_csv(CSV_IN, encoding="utf-8")
    if "names" not in df.columns:
        print(f"[ERROR] Input CSV has no 'names' column. Found: {df.columns.tolist()}")
        return

    agency_names = df["names"].dropna().astype(str).tolist()

    with open(CSV_OUT, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(["agency", "email"])

        for name in agency_names:
            name = name.strip()
            if not name:
                continue

            print(f"\n[INFO] Processing: {name}")
            # 2) Google CSE: "<name> real estate marbella -site:idealista.com"
            query = f"{name} real estate marbella -site:idealista.com -site:properstar.com"
            site = google_search_site(query)
            if not site:
                print(f"    [WARN] → No site found for {name}")
                writer.writerow([name, ""])
                time.sleep(1)
                continue

            emails = []

            # 3) Quick, plain GET of the homepage (no rendering) to see if an email is already present
            html_plain = fetch_plain_html(site)
            if html_plain:
                emails = extract_emails(html_plain)
                if emails:
                    print(f"    [DEBUG] Emails found in plain HTML: {emails}")

            # 4) If no email yet, look for any "contac" links in that raw HTML
            if not emails and html_plain:
                contac_hrefs = find_contact_links(html_plain)
                if contac_hrefs:
                    print(f"    [DEBUG] Found contact links (plain HTML): {contac_hrefs}")
                    for href in contac_hrefs:
                        full_url = urljoin(site, href)
                        html_contact = fetch_rendered_html(full_url)
                        if html_contact:
                            emails = extract_emails(html_contact)
                            if emails:
                                print(f"    [DEBUG] Emails found on {full_url}: {emails}")
                                break

            # 5) If still no email, render the homepage (in case JS injects it)
            if not emails:
                html_home = fetch_rendered_html(site)
                if html_home:
                    emails = extract_emails(html_home)
                    if emails:
                        print(f"    [DEBUG] Emails found in rendered homepage: {emails}")

                    # 5a) If still no email, look for any "contac" links in rendered HTML
                    if not emails:
                        contac_hrefs = find_contact_links(html_home)
                        if contac_hrefs:
                            print(f"    [DEBUG] Found contact links (rendered HTML): {contac_hrefs}")
                            for href in contac_hrefs:
                                full_url = urljoin(site, href)
                                html_contact = fetch_rendered_html(full_url)
                                if html_contact:
                                    emails = extract_emails(html_contact)
                                    if emails:
                                        print(f"    [DEBUG] Emails found on {full_url}: {emails}")
                                        break

            # 6) If still no email, try static contact suffixes with a plain GET
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
                            print(f"    [DEBUG] Emails found (static suffix) at {candidate}: {emails}")
                            break
                    except Exception:
                        # 404 or timeout, skip
                        pass

            # 7) Write out results to CSV
            if emails:
                for e in emails:
                    writer.writerow([name, e])
                    print(f"    [INFO] → saved: {e}")
            else:
                writer.writerow([name, ""])
                print(f"    [WARN] → no email found for {name}")

            out_f.flush()
            # Polite pause between agencies
            time.sleep(1)


if __name__ == "__main__":
    main()
