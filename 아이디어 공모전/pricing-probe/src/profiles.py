from .utils_common import load_yaml

def load_profiles():
    base = load_yaml("config/profiles/common_16.yaml")
    profiles = {p["id"]: p for p in base["profiles"]}
    ua_presets = base.get("ua_presets", {})
    network = base.get("network", {})
    return profiles, ua_presets, network
