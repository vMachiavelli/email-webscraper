import json
import re
import csv
import time
import requests
from urllib.parse import urljoin

# --- CONFIGURE THESE ---
API_KEY = "GOOGLE_API_KEY"
CX      = "GOOGLE_CX"
JSON_IN = "agencies.json"
CSV_OUT = "out.csv"
# ------------------------

EMAIL_REGEX    = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HREF_CONTA_RX  = re.compile(r'href=[\'"]([^\'"]*contac[^\'"]*)[\'"]', re.IGNORECASE)

def google_search_site(query):
    print(f"[DEBUG] Google searching for: {query}")
    params = {'key': API_KEY, 'cx': CX, 'q': query}
    try:
        resp = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            link = items[0]['link']
            print(f"[DEBUG] → Google returned: {link}")
            return link
        else:
            print("[DEBUG] → Google returned no items")
    except Exception as e:
        print(f"[DEBUG] → Google search failed: {e}")
    return None

def fetch_html(url):
    print(f"[DEBUG] Fetching: {url}")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"[DEBUG] → fetch/error: {e}")
        html = ""
    time.sleep(1)  # ← polite delay
    return html

def extract_emails_from_text(text):
    found = sorted(set(EMAIL_REGEX.findall(text)))
    if found:
        print(f"[DEBUG] → emails found: {found}")
    else:
        print("    → no emails found")
    return found

def find_conta_link(html, base_url):
    matches = HREF_CONTA_RX.findall(html)
    if matches:
        href = matches[0]
        full = urljoin(base_url, href)
        print(f"[DEBUG] → found conta‐link in HTML: {full}")
        return full
    print("    → no conta‐link found in HTML")
    return None

def lookup_site(agency):
    if agency.get("website"):
        print(f"[DEBUG] Using JSON website for {agency['name']}: {agency['website']}")
        return agency["website"]
    # only fallback: google
    return google_search_site(f"{agency['name']} real estate orihuela")

def main():
    agencies = json.load(open(JSON_IN, encoding="utf-8"))
    with open(CSV_OUT, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["agency", "email"])

        for agency in agencies:
            name = agency["name"]
            print(f"\n[INFO] Processing: {name}")
            site = lookup_site(agency)
            emails = []

            if site:
                # 1) fetch main page
                html = fetch_html(site)
                emails = extract_emails_from_text(html)

                # 2) if none, look for any contac* link in the HTML
                if not emails:
                    conta_url = find_conta_link(html, site)
                    if conta_url:
                        html2 = fetch_html(conta_url)
                        emails = extract_emails_from_text(html2)

            # 3) write to CSV
            if emails:
                for e in emails:
                    writer.writerow([name, e])
                print(f"[INFO] → saved {len(emails)} emails for {name}")
            else:
                writer.writerow([name, ""])
                print(f"[WARN]  → no email found for {name}")

            csvfile.flush()

if __name__ == "__main__":
    main()
