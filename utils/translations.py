# utils/translations.py
import csv
import os
from typing import Dict

TRANSLATIONS_FILE = os.path.join(os.path.dirname(__file__), "translations.csv")

def load_translations(lang: str) -> Dict[str, str]:
    """
    Load translations for a given language from translations.csv.
    Falls back to English if key is missing in the chosen language.
    """
    translations = {}
    fallback = {}

    # First, load English fallback
    with open(TRANSLATIONS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["language"] == "en":
                fallback[row["key"]] = row["value"]

    # Load selected language
    with open(TRANSLATIONS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["language"] == lang:
                translations[row["key"]] = row["value"]

    # Ensure fallback to English if key missing
    for key, val in fallback.items():
        if key not in translations:
            translations[key] = val

    return translations
