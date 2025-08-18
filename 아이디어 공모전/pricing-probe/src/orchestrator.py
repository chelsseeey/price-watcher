import argparse, os, time
from datetime import datetime, timezone
from rich import print
from .utils_common import load_yaml, ensure_dir, now_utc_iso
from .profiles import load_profiles
from .selectors import load_selectors
from .storage import init_run_dirs, append_csv, append_observation
from .crawler_pdp import fetch_pdp

CSV_HEADER = ["run_id","ts","platform","profile_id","sku_id","source","price","currency","url","artifact_html","artifact_img"]

def load_skus(path):
    return load_yaml(path)["skus"]

def run_once(platform: str, profiles_want=None):
    base = load_yaml("config/base.yaml")
    plan = load_yaml("runtime/batch_plan.yaml")
    ua_profiles, ua_presets, network = load_profiles()
    data_dir = base["paths"]["data_dir"]
    ensure_dir(os.path.join(data_dir, "runs", platform))

    job = plan["platform_jobs"][platform]
    profiles = job["profiles"]
    if profiles_want:
        profiles = [p for p in profiles if p in profiles_want]
    skus = load_skus(job["skus_from"])

    run_id = f"{platform}-{int(time.time())}"
    ts_dir = datetime.now(timezone.utc).isoformat().replace(":", "-")
    run_root, csv_path = init_run_dirs(data_dir, platform, ts_dir)
    obs_path = os.path.join(data_dir, "observations.jsonl")

    selectors_conf = load_selectors(platform)

    for p_id in profiles:
        prof = ua_profiles[p_id]
        proxy_url = None  # wire from runtime/proxy_endpoints.yaml if needed

        for sku in skus:
            rec = fetch_pdp(platform, sku["url"], prof, ua_presets, selectors_conf, data_dir, ts_dir, proxy_url, sku_id=sku["id"])
            row = {
                "run_id": run_id,
                "ts": now_utc_iso(),
                "platform": platform,
                "profile_id": p_id,
                "sku_id": sku["id"],
                "source": rec["source"],
                "price": rec["price"],
                "currency": rec["currency"],
                "url": sku["url"],
                "artifact_html": rec["artifact_html"],
                "artifact_img": rec["artifact_img"],
            }
            append_csv(csv_path, row, CSV_HEADER)
            append_observation(obs_path, {**row, "meta": sku.get("meta", {})})

    print(f"[bold green]Done[/bold green]: {platform} -> {run_root}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=["agoda","amazon","kayak"], required=True)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--profiles", nargs="*", help="subset of profile IDs")
    args = ap.parse_args()
    if args.once:
        run_once(args.platform, args.profiles)
    else:
        run_once(args.platform, args.profiles)

if __name__ == "__main__":
    main()
