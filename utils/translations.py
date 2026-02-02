import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "translations.csv")


def load_translations(language: str) -> dict:
    """
    Load translations for a given language from CSV.
    Falls back to English.
    """

    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(
            f"Translation file missing! Expected at: {CSV_PATH}"
        )

    translations = {}
    fallback = {}

    with open(CSV_PATH, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            lang = row["language"].strip()
            key = row["key"].strip()
            value = row["value"].strip()

            if lang == "en":
                fallback[key] = value
            if lang == language:
                translations[key] = value

    # fallback to English if key missing
    for k, v in fallback.items():
        translations.setdefault(k, v)

    return translations
