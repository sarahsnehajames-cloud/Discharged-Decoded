import requests


LANGUAGE_CODES = {
    "English": "en",
    "Español": "es",
    "Français": "fr",
    "中文": "zh",
    "العربية": "ar",
}


def translate_text(text: str, language: str) -> str:
    """Translate text into the selected language."""
    if not text or not text.strip():
        return text

    if language not in LANGUAGE_CODES:
        raise ValueError(f"Unsupported language: {language}")

    if language == "English":
        return text

    raise NotImplementedError(
        "Translation provider has not been connected yet."
    )