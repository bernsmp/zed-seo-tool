"""
Cloudflare D1 persistence layer for client profiles and results.

Uses the D1 REST API — no SDK needed, just requests.
Falls back gracefully if D1 is not configured.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

import requests

_available: Optional[bool] = None


def _secrets():
    """Read D1 credentials from Streamlit secrets or env vars."""
    try:
        import streamlit as st
        return {
            "account_id": st.secrets.get("D1_ACCOUNT_ID") or os.getenv("D1_ACCOUNT_ID"),
            "database_id": st.secrets.get("D1_DATABASE_ID") or os.getenv("D1_DATABASE_ID"),
            "api_token": st.secrets.get("D1_API_TOKEN") or os.getenv("D1_API_TOKEN"),
        }
    except Exception:
        return {
            "account_id": os.getenv("D1_ACCOUNT_ID"),
            "database_id": os.getenv("D1_DATABASE_ID"),
            "api_token": os.getenv("D1_API_TOKEN"),
        }


def is_available() -> bool:
    """Return True if D1 credentials are configured."""
    global _available
    if _available is None:
        s = _secrets()
        _available = bool(s["account_id"] and s["database_id"] and s["api_token"])
    return _available


def _query(sql: str, params: Optional[list] = None) -> list[dict]:
    """Execute a D1 SQL query and return rows."""
    s = _secrets()
    url = f"https://api.cloudflare.com/client/v4/accounts/{s['account_id']}/d1/database/{s['database_id']}/query"
    body = {"sql": sql}
    if params:
        body["params"] = params
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {s['api_token']}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("success") and data.get("result"):
        return data["result"][0].get("results", [])
    return []


# ── Client profiles ────────────────────────────────────────────────


def save_profile(slug: str, profile: dict) -> None:
    """Upsert a client profile."""
    now = datetime.now(timezone.utc).isoformat()
    _query(
        """INSERT INTO client_profiles (slug, profile, created_at, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(slug) DO UPDATE SET profile = ?, updated_at = ?""",
        [slug, json.dumps(profile), now, now, json.dumps(profile), now],
    )


def load_profile(slug: str) -> Optional[dict]:
    """Load a client profile by slug."""
    rows = _query(
        "SELECT profile FROM client_profiles WHERE slug = ?",
        [slug],
    )
    if rows:
        return json.loads(rows[0]["profile"])
    return None


def list_profiles() -> list[str]:
    """Return all client slugs, sorted alphabetically."""
    rows = _query("SELECT slug FROM client_profiles ORDER BY slug")
    return [row["slug"] for row in rows]


# ── Results (cleaning / mapping) ──────────────────────────────────


def save_result(slug: str, result_type: str, data: dict) -> None:
    """Save a cleaning or mapping result."""
    now = datetime.now(timezone.utc).isoformat()
    _query(
        """INSERT INTO results (client_slug, result_type, data, created_at)
           VALUES (?, ?, ?, ?)""",
        [slug, result_type, json.dumps(data), now],
    )


def load_latest_result(slug: str, result_type: str) -> Optional[dict]:
    """Load the most recent result for a client + type."""
    rows = _query(
        """SELECT data FROM results
           WHERE client_slug = ? AND result_type = ?
           ORDER BY created_at DESC LIMIT 1""",
        [slug, result_type],
    )
    if rows:
        return json.loads(rows[0]["data"])
    return None


def load_recent_results(slug: str, result_type: str, limit: int = 25) -> list[dict]:
    """Load recent results for a client + type, newest first."""
    rows = _query(
        """SELECT data FROM results
           WHERE client_slug = ? AND result_type = ?
           ORDER BY created_at DESC LIMIT ?""",
        [slug, result_type, limit],
    )
    return [json.loads(row["data"]) for row in rows]
