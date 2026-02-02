# utils/translations.py
import csv
import os
from pathlib import Path

# Path to translations CSV
TRANSLATION_FILE = Path(__file__).parent / "translations.csv"

def _validate_csv(path):
    """Ensure CSV has exactly 3 columns per row."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader, start=1):
            if len(row) != 3:
                raise ValueError(
                    f"CSV format error on line {i}: expected 3 columns (language,key,value), got {len(row)} → {row}"
                )

def load_translations(default_language="en"):
    """
    Load translations from CSV.
    Returns a dictionary: translations[lang][key] = value
    """
    if not TRANSLATION_FILE.exists():
        raise FileNotFoundError(f"Translations CSV not found at {TRANSLATION_FILE}")

    _validate_csv(TRANSLATION_FILE)

    translations = {}
    with open(TRANSLATION_FILE, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, quotechar='"')
        for language, key, value in reader:
            translations.setdefault(language, {})[key] = value

    # Fallback to default language if key missing
    def get_translation(lang, key):
        return translations.get(lang, {}).get(key) or translations.get(default_language, {}).get(key) or key

    return translations
