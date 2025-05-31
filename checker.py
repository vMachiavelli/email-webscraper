import json

with open("agencies.json", "r") as f:
    try:
        json.load(f)
        print("✅ JSON is valid")
    except json.JSONDecodeError as e:
        print(f"❌ JSON error at line {e.lineno}, column {e.colno}: {e.msg}")
