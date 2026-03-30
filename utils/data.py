"""
Data layer — all file I/O, CSV parsing, client management, and export.

Uses Supabase for persistence when configured (Streamlit Cloud),
falls back to local filesystem for development.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from utils import db

DATA_DIR = Path(__file__).parent.parent / "data" / "clients"


def slugify(name: str) -> str:
    """Convert a client name to a filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _client_dir(slug: str) -> Path:
    path = DATA_DIR / slug
    path.mkdir(parents=True, exist_ok=True)
    return path


# --- Client profile ---


def save_client_profile(slug: str, profile: dict) -> Path:
    # Always save to Supabase if available
    if db.is_available():
        db.save_profile(slug, profile)

    # Also save locally (useful for dev and as cache)
    path = _client_dir(slug) / "profile.json"
    path.write_text(json.dumps(profile, indent=2))
    return path


def load_client_profile(slug: str) -> Optional[dict]:
    # Try Supabase first
    if db.is_available():
        profile = db.load_profile(slug)
        if profile:
            return profile

    # Fall back to local file
    path = _client_dir(slug) / "profile.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def list_clients() -> list[str]:
    """Return slugs of all clients that have a profile."""
    # Try Supabase first
    if db.is_available():
        slugs = db.list_profiles()
        if slugs:
            return slugs

    # Fall back to local files
    if not DATA_DIR.exists():
        return []
    return sorted(
        d.name
        for d in DATA_DIR.iterdir()
        if d.is_dir() and (d / "profile.json").exists()
    )


# --- Results (cleaning / mapping) ---


def save_results(slug: str, result_type: str, data: dict) -> Path:
    """Save cleaning or mapping results with timestamp.
    result_type: 'cleaning' or 'mapping'
    """
    # Save to Supabase if available
    if db.is_available():
        db.save_result(slug, result_type, data)

    # Also save locally
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _client_dir(slug) / f"{result_type}_{ts}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def load_latest_results(slug: str, result_type: str) -> Optional[dict]:
    """Load most recent results file for a given type."""
    # Try Supabase first
    if db.is_available():
        result = db.load_latest_result(slug, result_type)
        if result:
            return result

    # Fall back to local files
    client_dir = _client_dir(slug)
    files = sorted(client_dir.glob(f"{result_type}_*.json"), reverse=True)
    if files:
        return json.loads(files[0].read_text())
    return None


# --- CSV parsing ---


def parse_keyword_csv(file) -> pd.DataFrame:
    """Parse a keyword CSV (SEMRush export, API pull, or generic).
    Auto-detects delimiter. Normalizes column names to lowercase.
    """
    # Read a sample to detect delimiter
    sample = file.read(4096)
    file.seek(0)
    if isinstance(sample, bytes):
        sample = sample.decode("utf-8", errors="ignore")

    delimiter = ";" if sample.count(";") > sample.count(",") else ","

    df = pd.read_csv(file, delimiter=delimiter)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


# --- Export ---


def export_csv(df: pd.DataFrame) -> bytes:
    """Convert a DataFrame to CSV bytes for st.download_button."""
    return df.to_csv(index=False).encode("utf-8")
