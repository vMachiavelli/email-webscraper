import re
import pandas as pd

# --- CONFIGURATION ---
INPUT_CSV   = "out_combined.csv"
OUTPUT_CSV  = "out_combined_cleaned.csv"
# ------------------------

# Strict regex for valid email addresses
EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

# Regex to detect media files (case-insensitive)
MEDIA_EXT_REGEX = re.compile(
    r'.*\.(?:png|jpg|jpeg|gif|svg|mp4|mp3|webp)$',
    re.IGNORECASE
)

def main():
    # 1) Load the CSV into a DataFrame
    try:
        df = pd.read_csv(INPUT_CSV, encoding="utf-8")
    except FileNotFoundError:
        print(f"[ERROR] '{INPUT_CSV}' not found. Please ensure it’s in the same folder.")
        return
    except Exception as e:
        print(f"[ERROR] Failed to read '{INPUT_CSV}': {e}")
        return

    if "email" not in df.columns:
        print(f"[ERROR] '{INPUT_CSV}' has no 'email' column. Columns found: {list(df.columns)}")
        return

    total_rows = len(df)

    # 2) Build masks for valid email and non-media
    is_valid_email = df["email"].astype(str).str.match(EMAIL_REGEX)
    is_not_media  = ~df["email"].astype(str).str.match(MEDIA_EXT_REGEX)

    # 3) Combine masks: only keep rows where both are True
    mask = is_valid_email & is_not_media
    df_cleaned = df[mask].reset_index(drop=True)

    kept_rows    = len(df_cleaned)
    removed_rows = total_rows - kept_rows

    # 4) Save the cleaned DataFrame
    try:
        df_cleaned.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    except Exception as e:
        print(f"[ERROR] Failed to write '{OUTPUT_CSV}': {e}")
        return

    # 5) Print summary
    print("Email‐cleaning summary:")
    print(f"  Total rows in '{INPUT_CSV}':       {total_rows}")
    print(f"  Rows with valid emails kept:      {kept_rows}")
    print(f"  Rows removed (invalid/media):     {removed_rows}")
    print(f"\nCleaned CSV written to: '{OUTPUT_CSV}'")

if __name__ == "__main__":
    main()
