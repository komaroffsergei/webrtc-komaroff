import os

ROOT = os.path.dirname(os.path.dirname(__file__))
RECORDINGS_DIR = os.path.join(ROOT, "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)
