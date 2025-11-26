import os

import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.yml")


def load_settings():
    """
    Load YAML settings while expanding environment variable placeholders.
    """
    with open(SETTINGS_PATH, "r") as config_file:
        content = os.path.expandvars(config_file.read())

    return yaml.safe_load(content)
