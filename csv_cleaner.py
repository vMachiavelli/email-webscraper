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

def has_valid_tld(email: str) -> bool:
    ext = tldextract.extract(email)
    return bool(ext.suffix)

def has_mx_record(domain: str) -> bool:
    try:
        dns.resolver.resolve(domain, 'MX')
        return True
    except Exception:
        return False

def is_valid(email: str) -> bool:
    """Return True if email passes all checks: format, non-media, non-wixpress, valid TLD, MX record."""
    if not EMAIL_RX.match(email):
        return False
    if MEDIA_EXT_RX.match(email):
        return False
    if WIXPRESS_RX.search(email):
        return False

    # TLD check
    if not has_valid_tld(email):
        return False

    # MX record check
    domain = email.split('@', 1)[1]
    if not has_mx_record(domain):
        return False

    return True

def extract_emails_from_df(df: pd.DataFrame) -> list:
    """Extract all values from columns containing 'email' (or second column fallback)."""
    cols = [c for c in df.columns if 'email' in c.lower()]
    if not cols and df.shape[1] >= 2:
        cols = [df.columns[1]]
    emails = []
    for col in cols:
        s = df[col].dropna().astype(str).str.strip().str.lower()
        emails.extend(s.tolist())
    return emails

def main():
    all_emails = []

    for path in INPUT_FILES:
        try:
            df = pd.read_csv(path, encoding="utf-8", dtype=str)
        except Exception as e:
            print(f"[WARN] Could not read '{path}': {e}")
            continue

        extracted = extract_emails_from_df(df)
        filtered = [e for e in extracted if is_valid(e)]
        print(f"{path}: {len(extracted)} extracted, {len(filtered)} valid")
        all_emails.extend(filtered)

    unique_emails = sorted(set(all_emails))
    print(f"\nTotal collected: {len(all_emails)}")
    print(f"Unique after dedupe: {len(unique_emails)}")

    pd.DataFrame({'email': unique_emails}).to_csv(
        OUTPUT_FILE, index=False, encoding="utf-8"
    )
    print(f"\nSaved {len(unique_emails)} emails to '{OUTPUT_FILE}'")

if __name__ == "__main__":
    main()

# Dependencies:
# pip install pandas dnspython tldextract
