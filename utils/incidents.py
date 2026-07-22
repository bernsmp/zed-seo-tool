"""Sanitized incident reporting for recoverable SEO batch failures."""

import hashlib
import re
from datetime import datetime, timezone
from uuid import uuid4

from utils.data import save_incident_report

INCIDENT_SCHEMA_VERSION = 1
AUTO_FIX_CATEGORIES = {
    "checkpoint_integrity",
    "output_truncation",
    "structured_output",
}

_SECRET_PATTERNS = (
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:ant-|or-v1-)?[A-Za-z0-9_-]{16,}\b", re.IGNORECASE),
    re.compile(
        r"(?i)\b(api[_ -]?key|authorization|bearer)\b\s*[:=]?\s*[A-Za-z0-9._-]{12,}"
    ),
)


def sanitize_error_message(message: str, max_length: int = 1200) -> str:
    """Remove credential-like values and cap stored error detail."""
    sanitized = str(message)
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized[:max_length]


def classify_error(message: str) -> str:
    """Map an error to a small triage category."""
    normalized = message.lower()
    if any(term in normalized for term in ("malformed json", "expecting value", "expecting property name")):
        return "structured_output"
    if any(term in normalized for term in ("truncated", "output limit", "max_tokens", "max tokens")):
        return "output_truncation"
    if any(term in normalized for term in ("checkpoint", "duplicated", "duplicate rows")):
        return "checkpoint_integrity"
    if any(term in normalized for term in ("401", "invalid api key", "authentication", "unauthorized")):
        return "authentication"
    if any(term in normalized for term in ("credit balance", "plans & billing", "billing")):
        return "billing"
    if any(term in normalized for term in ("429", "rate limit", "too many requests")):
        return "rate_limit"
    if any(term in normalized for term in ("connection", "timeout", "timed out")):
        return "connectivity"
    return "unknown"


def _provider_signals(message: str) -> list[str]:
    normalized = message.lower()
    signals = []
    if "anthropic" in normalized:
        signals.append("anthropic")
    if "gemini" in normalized:
        signals.append("gemini")
    if "openrouter" in normalized:
        signals.append("openrouter")
    return signals


def build_incident_report(
    *,
    client_slug: str,
    job_type: str,
    failed_batch: int,
    processed_batches: int,
    total_batches: int,
    saved_result_count: int,
    error_message: str,
) -> dict:
    """Build a diagnostic-only report without keyword or prompt content."""
    sanitized_message = sanitize_error_message(error_message)
    category = classify_error(sanitized_message)
    fingerprint_source = "|".join(
        (
            client_slug,
            job_type,
            str(failed_batch),
            category,
            sanitized_message,
        )
    )

    return {
        "schema_version": INCIDENT_SCHEMA_VERSION,
        "incident_id": str(uuid4()),
        "fingerprint": hashlib.sha256(fingerprint_source.encode()).hexdigest()[:20],
        "status": "new",
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "client_slug": client_slug,
        "job_type": job_type,
        "failed_batch": failed_batch,
        "processed_batches": processed_batches,
        "total_batches": total_batches,
        "saved_result_count": saved_result_count,
        "error_category": category,
        "provider_signals": _provider_signals(sanitized_message),
        "auto_fix_eligible": category in AUTO_FIX_CATEGORIES,
        "error_message": sanitized_message,
    }


def report_incident(**kwargs) -> dict:
    """Persist a sanitized incident and return its delivery status."""
    report = build_incident_report(**kwargs)
    try:
        _, remote_saved = save_incident_report(report["client_slug"], report)
    except Exception as exc:
        print(f"[incident] Save failed for {report['incident_id']}: {exc}")
        remote_saved = False
    return {**report, "remote_saved": remote_saved}
