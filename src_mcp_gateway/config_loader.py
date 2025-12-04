import os

import yaml

import settings as _settings  # noqa: F401  # ensures default env vars are populated

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.yml")


def load_settings():
    """
    Load YAML settings while expanding environment variable placeholders.
    """
    with open(SETTINGS_PATH, "r") as config_file:
        content = os.path.expandvars(config_file.read())

    return yaml.safe_load(content)
