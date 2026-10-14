from urllib.parse import quote_plus


def get_nhs_search_url(condition: str) -> str:
    """Return an NHS search URL for a confirmed condition."""
    condition = (condition or "").strip()

    if not condition:
        return "https://www.nhs.uk/health-a-z/"

    return (
        "https://www.nhs.uk/search/results/?q="
        + quote_plus(condition)
    )
