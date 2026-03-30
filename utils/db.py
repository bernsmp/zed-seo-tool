"""
Supabase persistence layer for client profiles and results.

Falls back gracefully if Supabase is not configured — callers should
check `is_available()` before using these functions.
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

_client = None
_available: Optional[bool] = None


def is_available() -> bool:
    """Return True if Supabase credentials are configured."""
    global _available
    if _available is None:
        try:
            import streamlit as st
            url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
            key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
            _available = bool(url and key)
        except Exception:
            _available = False
    return _available


def _get_client():
    """Lazy-init Supabase client."""
    global _client
    if _client is None:
        import streamlit as st
        from supabase import create_client

        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
        _client = create_client(url, key)
    return _client


# ── Client profiles ────────────────────────────────────────────────


def save_profile(slug: str, profile: dict) -> None:
    """Upsert a client profile."""
    _get_client().table("client_profiles").upsert(
        {
            "slug": slug,
            "profile": json.dumps(profile),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="slug",
    ).execute()


def load_profile(slug: str) -> Optional[dict]:
    """Load a client profile by slug."""
    resp = (
        _get_client()
        .table("client_profiles")
        .select("profile")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )
    if resp.data:
        return json.loads(resp.data[0]["profile"])
    return None


def list_profiles() -> list[str]:
    """Return all client slugs, sorted alphabetically."""
    resp = (
        _get_client()
        .table("client_profiles")
        .select("slug")
        .order("slug")
        .execute()
    )
    return [row["slug"] for row in resp.data]


# ── Results (cleaning / mapping) ──────────────────────────────────


def save_result(slug: str, result_type: str, data: dict) -> None:
    """Save a cleaning or mapping result."""
    _get_client().table("results").insert(
        {
            "client_slug": slug,
            "result_type": result_type,
            "data": json.dumps(data),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()


def load_latest_result(slug: str, result_type: str) -> Optional[dict]:
    """Load the most recent result for a client + type."""
    resp = (
        _get_client()
        .table("results")
        .select("data")
        .eq("client_slug", slug)
        .eq("result_type", result_type)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if resp.data:
        return json.loads(resp.data[0]["data"])
    return None
