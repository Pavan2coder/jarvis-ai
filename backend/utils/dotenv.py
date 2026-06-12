import os

def load_dotenv():
    """Tiny .env loader (no extra package). Reads KEY=VALUE lines from the project root directory."""
    # project root is 3 levels up from backend/utils/dotenv.py
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root_dir, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)
    except Exception as e:
        print(f"  ⚠️  Could not read .env: {e}")
