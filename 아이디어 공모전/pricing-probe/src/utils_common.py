import os, re, json, yaml, time, random, hashlib
from datetime import datetime, timezone

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def now_utc_iso():
    return datetime.now(timezone.utc).isoformat()

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def jitter(sleep_range):
    lo, hi = sleep_range
    time.sleep(random.uniform(lo, hi))

def clean_price_text(txt: str):
    t = txt.strip().replace("\u00a0", " ").replace(",", "")
    m = re.findall(r"[\d]+(?:\.\d+)?", t)
    return m[0] if m else None
