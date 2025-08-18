import os, csv, json
from .utils_common import ensure_dir

def init_run_dirs(data_dir, platform, ts_dir):
    root = os.path.join(data_dir, "runs", platform, ts_dir)
    ensure_dir(root)
    return root, os.path.join(root, "raw.csv")

def append_csv(csv_path, row: dict, header_order=None):
    is_new = not os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        import csv
        writer = csv.DictWriter(f, fieldnames=header_order or list(row.keys()))
        if is_new:
            writer.writeheader()
        writer.writerow(row)

def append_observation(obs_path, record: dict):
    ensure_dir(os.path.dirname(obs_path))
    with open(obs_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
