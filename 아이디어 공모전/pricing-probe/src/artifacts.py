import os, json
from .utils_common import ensure_dir, now_utc_iso

def artifact_paths(base_dir, platform, run_dir_ts, profile_id, sku_id):
    root = os.path.join(base_dir, "runs", platform, run_dir_ts, "artifacts", profile_id, sku_id)
    ensure_dir(root)
    tsz = now_utc_iso().replace(":", "-")
    return {
        "dir": root,
        "ts": tsz,
        "html": os.path.join(root, f"pdp_{tsz}.html"),
        "img": os.path.join(root, f"pdp_{tsz}.png"),
        "csv": os.path.join(root, f"price_{tsz}.csv"),
    }

def save_html(path, html: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

def save_binary(path, data: bytes):
    with open(path, "wb") as f:
        f.write(data)

def save_csv(path, header, row_dict):
    import csv, os
    is_new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if is_new:
            w.writeheader()
        w.writerow(row_dict)
