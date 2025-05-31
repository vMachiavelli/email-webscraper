import json
import re
import csv
import time
import requests
from urllib.parse import urljoin
from requests_html import HTMLSession

# --- CONFIGURE THESE ---
API_KEY = "GOOGLE_API_KEY"
CX      = "GOOGLE_CX"
JSON_IN = "agencies.json"
CSV_OUT = "out.csv"
# ------------------------

EMAIL_RX      = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAILTO_RX     = re.compile(r'href=[\'"]mailto:([^\'"]+)[\'"]', re.IGNORECASE)
HREF_CONTA_RX = re.compile(r'href=[\'"]([^\'"]*contac[^\'"]*)[\'"]', re.IGNORECASE)

session = HTMLSession()

def google_search_site(query):
    print(f"[DEBUG] Google search query: {query}")
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={'key': API_KEY, 'cx': CX, 'q': query},
            timeout=10
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        link = items[0]['link'] if items else None
        print(f"[DEBUG] Google returned: {link}")
        return link
    except Exception as e:
        print(f"[DEBUG] Google search failed: {e}")
        return None

def fetch_html(url, render=False):
    print(f"[DEBUG] Fetching: {url}  {'(render)' if render else ''}")
    try:
        if render:
            r = session.get(url, timeout=10)
            r.html.render(timeout=5, sleep=2)
            return r.html.html
        else:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return r.text
    except Exception as e:
        print(f"[DEBUG] → fetch/error: {e}")
        return ""

def extract_emails_from_text(text):
    emails = set(EMAIL_RX.findall(text))
    emails |= set(MAILTO_RX.findall(text))
    found = sorted(emails)
    print(f"[DEBUG] → emails found: {found}" if found else "    → no emails found")
    return found

def lookup_site(agency):
    if agency.get("website"):
        print(f"[DEBUG] Using JSON website for {agency['name']}: {agency['website']}")
        return agency["website"]
    return google_search_site(f"{agency['name']} real estate orihuela") or agency["proUrl"]

def main():
    agencies = json.load(open(JSON_IN, encoding="utf-8"))
    contact_suffixes = (
        "contact","contacto","contactar","contac","kontakt",
        "contact-us","kontakt-oss"
    )

    with open(CSV_OUT, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["agency", "email"])

        for agency in agencies:
            name = agency["name"]
            print(f"\n[INFO] Processing: {name}")
            site = lookup_site(agency)
            emails = []

            if site:
                # 1) main page (try render first for JS‐heavy sites)
                html = fetch_html(site, render=True)
                emails = extract_emails_from_text(html)

                # 2) if none, hunt *all* contac* links
                if not emails:
                    links = HREF_CONTA_RX.findall(html)
                    for href in links:
                        full = urljoin(site, href)
                        html2 = fetch_html(full, render=True)
                        emails = extract_emails_from_text(html2)
                        if emails:
                            break

                # 3) if still none, try static suffix URLs
                if not emails:
                    for suf in contact_suffixes:
                        url = urljoin(site.rstrip('/') + '/', suf)
                        html2 = fetch_html(url, render=False)
                        emails = extract_emails_from_text(html2)
                        if emails:
                            break

            # write out
            if emails:
                for e in emails:
                    writer.writerow([name, e])
                    print(f"[INFO]  → saved: {e}")
            else:
                writer.writerow([name, ""])
                print(f"[WARN]  → no email found for {name}")

            csvfile.flush()
            time.sleep(1)     # polite delay

if __name__ == "__main__":
    main()
