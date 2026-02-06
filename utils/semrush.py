"""
SEMRush API client — Pull competitor keywords and check API units.
Handles organic keyword research, API unit tracking, and cost estimation.
"""

import io
import os

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.local"))
load_dotenv()  # Fallback to .env

SEMRUSH_BASE_URL = "https://api.semrush.com/"


def _api_key() -> str:
    """Get SEMRush API key from environment."""
    key = os.getenv("SEMRUSH_API_KEY", "")
    if not key:
        raise ValueError(
            "SEMRUSH_API_KEY not set. "
            "Add it to .env.local or set the environment variable."
        )
    return key


def check_api_units() -> dict:
    """Check remaining SEMRush API units.

    Returns:
        Dict with 'units_remaining' key.
    """
    try:
        resp = requests.get(
            "https://www.semrush.com/users/countapiunit",
            params={"key": _api_key()},
            timeout=15,
        )
        resp.raise_for_status()
        units = int(resp.text.strip())
    except Exception:
        # API units endpoint may not be available for all accounts
        units = -1

    return {"units_remaining": units}


def pull_competitor_keywords(
    competitor_domain: str,
    database: str = "us",
    limit: int = 500,
    export_columns: str = "Ph,Nq,Kd,Co,Nr,In",
) -> pd.DataFrame:
    """Pull organic keywords for a competitor domain from SEMRush API.

    Args:
        competitor_domain: Domain to pull keywords for (e.g. "competitor.com")
        database: Regional database (default "us"). Options: us, uk, ca, au, etc.
        limit: Max number of keywords to return (each costs 10 API units)
        export_columns: Comma-separated column codes:
            Ph = Keyword phrase
            Po = Position
            Nq = Search volume (monthly)
            Cp = CPC
            Co = Competition (0-1)
            Kd = Keyword Difficulty (0-100)
            Tr = Traffic
            Td = Traffic cost (USD)
            Nr = Number of results
            In = Search intent

    Returns:
        DataFrame with columns: keyword, volume, keyword_difficulty, competition, intent
        (column names normalized to match the tool's existing format)
    """
    params = {
        "type": "domain_organic",
        "key": _api_key(),
        "domain": competitor_domain,
        "database": database,
        "display_limit": limit,
        "export_columns": export_columns,
    }

    resp = requests.get(SEMRUSH_BASE_URL, params=params, timeout=60)
    resp.raise_for_status()

    # SEMRush returns semicolon-delimited CSV text
    # First line is headers, rest is data
    text = resp.text.strip()
    if not text or "ERROR" in text[:50]:
        error_msg = text[:200] if text else "Empty response"
        raise ValueError(f"SEMRush API error: {error_msg}")

    df = pd.read_csv(io.StringIO(text), sep=";")

    # Normalize column names to match our tool's format
    column_map = {
        "Keyword": "keyword",
        "Ph": "keyword",
        "Search Volume": "volume",
        "Nq": "volume",
        "Keyword Difficulty": "keyword_difficulty",
        "Kd": "keyword_difficulty",
        "Competition": "competition",
        "Co": "competition",
        "CPC": "cpc",
        "Cp": "cpc",
        "Number of Results": "number_of_results",
        "Nr": "number_of_results",
        "Intent": "intent",
        "Intents": "intent",
        "In": "intent",
        "Position": "position",
        "Po": "position",
        "Traffic": "traffic",
        "Tr": "traffic",
        "Traffic Cost": "traffic_cost",
        "Td": "traffic_cost",
    }
    df.rename(columns=column_map, inplace=True)

    # Ensure lowercase column names
    df.columns = [c.lower().strip() for c in df.columns]

    return df


def estimate_api_cost(num_keywords: int) -> dict:
    """Estimate SEMRush API unit cost for a keyword pull.

    Args:
        num_keywords: Number of keywords to pull

    Returns:
        Dict with 'api_units' and 'description'
    """
    units = num_keywords * 10  # 10 API units per line for domain_organic
    return {
        "api_units": units,
        "description": f"{num_keywords} keywords × 10 units/keyword = {units:,} API units",
    }
