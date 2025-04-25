import os
import json

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".hscli", "config.json")


def ensure_config_dir():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)


def load_config():
    ensure_config_dir()
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(config):
    ensure_config_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


# Optional: helper for default endpoint
def get_endpoint(override=None):
    if override:
        return override
    return load_config().get("endpoint")