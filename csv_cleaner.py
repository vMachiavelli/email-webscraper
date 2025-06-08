import re
import pandas as pd
import dns.resolver
import tldextract

# --- CONFIGURATION ---
INPUT_FILES = [
    "out_combined.csv",
    "Marbella emails 1 (205).csv",
    "Marbella Emails 2 (194).csv",
    "Marbella emails 3 (180).csv",
    "Marbella emails 4 (193).csv",
    "Marbella emails 5 (191).csv",
]
OUTPUT_FILE = "all_unique_emails.csv"
# ------------------------

# 1) Strict regex for valid email addresses
EMAIL_RX = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

# 2) Regex to detect media URLs (case-insensitive)
MEDIA_EXT_RX = re.compile(
    r'.*\.(?:png|jpg|jpeg|gif|svg|mp4|mp3|webp)$',
    re.IGNORECASE
)

# 3) Regex to detect any “wixpress” emails
WIXPRESS_RX = re.compile(r'wixpress', re.IGNORECASE)
ABC_123_RX = re.compile(r'123@abc.com')

# Helpers

def has_valid_tld(email: str) -> bool:
    ext = tldextract.extract(email)
    valid = bool(ext.suffix)
    print(f"    [DEBUG] TLD check for '{email}', suffix='{ext.suffix}', valid={valid}")
    return valid


def has_mx_record(domain: str) -> bool:
    try:
        dns.resolver.resolve(domain, 'MX')
        print(f"    [DEBUG] MX record found for domain '{domain}'")
        return True
    except Exception as e:
        print(f"    [DEBUG] No MX record for domain '{domain}': {e}")
        return False


def is_valid(email: str) -> bool:
    print(f"[DEBUG] Validating email '{email}'...")
    if not EMAIL_RX.match(email):
        print("    [DEBUG] Failed EMAIL_RX")
        return False
    if MEDIA_EXT_RX.match(email):
        print("    [DEBUG] Matches MEDIA_EXT_RX, skipping")
        return False
    if WIXPRESS_RX.search(email):
        print("    [DEBUG] Contains 'wixpress', skipping")
        return False
    if not has_valid_tld(email):
        return False
    domain = email.split('@', 1)[1]
    if not has_mx_record(domain):
        return False
    print(f"    [DEBUG] Email '{email}' passed all checks")
    return True


def extract_emails_from_df(df: pd.DataFrame, path: str) -> list:
    print(f"[DEBUG] Extracting emails from '{path}'")
    cols = [c for c in df.columns if 'email' in c.lower()]
    if not cols and df.shape[1] >= 2:
        cols = [df.columns[1]]
    all_emails = []
    for col in cols:
        s = df[col].dropna().astype(str).str.strip().str.lower()
        print(f"    [DEBUG] Column '{col}' has {len(s)} entries")
        all_emails.extend(s.tolist())
    print(f"    [DEBUG] Extracted total {len(all_emails)} raw emails from '{path}'")
    return all_emails


def main():
    all_emails = []

    for path in INPUT_FILES:
        print(f"\n[INFO] Processing file: {path}")
        try:
            df = pd.read_csv(path, encoding="utf-8", dtype=str)
            print(f"    [DEBUG] Read {len(df)} rows from '{path}'")
        except Exception as e:
            print(f"[WARN] Skipping '{path}' due to read error: {e}")
            continue

        extracted = extract_emails_from_df(df, path)
        filtered = []
        for e in extracted:
            if is_valid(e):
                filtered.append(e)
        print(f"    [DEBUG] After validation: kept {len(filtered)} of {len(extracted)} emails")
        all_emails.extend(filtered)

    unique_emails = sorted(set(all_emails))
    print(f"\n[INFO] Total collected emails: {len(all_emails)}")
    print(f"[INFO] Unique emails after dedupe: {len(unique_emails)}")

    pd.DataFrame({'email': unique_emails}).to_csv(
        OUTPUT_FILE, index=False, encoding="utf-8"
    )
    print(f"\n[INFO] Saved {len(unique_emails)} unique emails to '{OUTPUT_FILE}'")

if __name__ == "__main__":
    main()
