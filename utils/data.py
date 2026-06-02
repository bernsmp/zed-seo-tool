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


def _has_failed_batch_rows(result: dict) -> bool:
    """Detect old checkpoints that saved API failures as export rows."""
    for row in result.get("results", []):
        reason = str(row.get("reason", ""))
        notes = str(row.get("notes", ""))
        if reason.startswith("Batch failed:") or notes.startswith("Batch failed:"):
            return True
        if row.get("recommendation") == "Error":
            return True
    return False


def _select_best_cleaning_result(results: list[dict]) -> Optional[dict]:
    """Prefer completed results, or the most advanced partial checkpoint for the latest source."""
    if not results:
        return None

    usable_results = [result for result in results if not _has_failed_batch_rows(result)]
    if not usable_results:
        return results[0]

    results = usable_results
    latest = results[0]
    latest_meta = latest.get("meta", {})
    if latest_meta.get("completed") or latest.get("qc_summary"):
        return latest

    source_fields = [
        "source_keyword_count",
        "auto_removed_count",
        "llm_keyword_count",
        "total_batches",
    ]
    latest_source = tuple(latest_meta.get(field) for field in source_fields)
    has_source_meta = all(value is not None for value in latest_source)

    candidates = []
    for result in results:
        meta = result.get("meta", {})
        if meta.get("completed", True):
            continue
        if has_source_meta and tuple(meta.get(field) for field in source_fields) != latest_source:
            continue
        candidates.append(result)

    if not candidates:
        return latest

    return max(candidates, key=lambda result: result.get("meta", {}).get("processed_batches", 0))


def _select_best_mapping_result(results: list[dict]) -> Optional[dict]:
    """Prefer the most advanced active mapping checkpoint for the latest source."""
    if not results:
        return None

    usable_results = [result for result in results if not _has_failed_batch_rows(result)]
    if not usable_results:
        return results[0]

    results = usable_results
    latest = results[0]
    latest_meta = latest.get("meta", {})
    if latest_meta.get("completed"):
        return latest

    source_fields = ["source_keyword_count", "total_batches"]
    latest_source = tuple(latest_meta.get(field) for field in source_fields)
    has_source_meta = all(value is not None for value in latest_source)

    candidates = []
    for result in results:
        meta = result.get("meta", {})
        if meta.get("completed", False):
            continue
        if has_source_meta and tuple(meta.get(field) for field in source_fields) != latest_source:
            continue
        candidates.append(result)

    if not candidates:
        return latest

    return max(
        candidates,
        key=lambda result: (
            result.get("meta", {}).get("processed_batches", 0),
            len(result.get("results", [])),
        ),
    )


def save_results(slug: str, result_type: str, data: dict) -> Path:
    """Save cleaning or mapping results with timestamp.
    result_type: 'cleaning' or 'mapping'
    """
    # Save to Supabase if available
    if db.is_available():
        try:
            db.save_result(slug, result_type, data)
        except Exception as exc:
            # Keep the app running even if remote persistence is unavailable.
            print(f"[save_results] Remote save failed for {slug}/{result_type}: {exc}")

    # Also save locally
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _client_dir(slug) / f"{result_type}_{ts}.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def load_latest_results(slug: str, result_type: str) -> Optional[dict]:
    """Load most recent results file for a given type."""
    # Try Supabase first
    if db.is_available():
        if result_type == "cleaning":
            result = _select_best_cleaning_result(db.load_recent_results(slug, result_type))
        elif result_type == "mapping":
            result = _select_best_mapping_result(db.load_recent_results(slug, result_type))
        else:
            result = db.load_latest_result(slug, result_type)
        if result:
            return result

    # Fall back to local files
    client_dir = _client_dir(slug)
    files = sorted(client_dir.glob(f"{result_type}_*.json"), reverse=True)
    if files:
        if result_type == "cleaning":
            recent_results = [json.loads(path.read_text()) for path in files[:25]]
            return _select_best_cleaning_result(recent_results)
        if result_type == "mapping":
            recent_results = [json.loads(path.read_text()) for path in files[:25]]
            return _select_best_mapping_result(recent_results)
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
