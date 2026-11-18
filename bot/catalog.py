"""Load sample inventory from the shared English content pack."""
import json
from pathlib import Path

CONTENT_PATH = Path(__file__).resolve().parent.parent / "content" / "en.json"
with CONTENT_PATH.open(encoding="utf-8") as source:
    CONTENT = json.load(source)

APARTMENTS = CONTENT["apartments"]

def apartment(apartment_id):
    return next((item for item in APARTMENTS if item["id"] == apartment_id), None)
