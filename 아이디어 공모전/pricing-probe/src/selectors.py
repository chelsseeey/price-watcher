from .utils_common import load_yaml

def load_selectors(platform: str):
    return load_yaml(f"config/selectors/{platform}.yaml")
