#!/usr/bin/env python3
"""Deterministic job ledger for the Zed SEO Cowork plugin.

The script deliberately performs no LLM or SEMrush API calls. Cowork owns the
judgment and the official connector owns research access. This script owns the
parts that must remain deterministic across conversations: inputs, batching,
schema validation, checkpoints, resume, exports, and sanitized incidents.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


VERSION = 1
VALID_KINDS = {"cleaning", "mapping"}
VALID_CLASSIFICATIONS = {"KEEP", "REMOVE", "UNSURE"}
SPECIAL_MAPPING_TARGETS = {"NEW_PAGE", "BLOG_POST"}
DEFAULT_BATCH_SIZES = {"cleaning": 100, "mapping": 50}
MAX_BATCH_SIZE = 250
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class JobError(RuntimeError):
    """A safe, operator-facing validation or state error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise JobError(f"Required file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise JobError(f"Invalid JSON in {path}: {exc.msg}") from exc


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def require_slug(value: str, label: str = "slug") -> str:
    normalized = value.strip().lower()
    if not SLUG_PATTERN.fullmatch(normalized):
        raise JobError(
            f"Invalid {label} '{value}'. Use lowercase letters, numbers, and single hyphens."
        )
    return normalized


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def workspace_path(value: str) -> Path:
    if not value or not value.strip():
        raise JobError("Workspace path is empty. Use the absolute Cowork Project folder path.")
    return Path(value).expanduser().resolve()


def job_path(value: str) -> Path:
    if not value or not value.strip():
        raise JobError("Job path is empty. Use the absolute checkpointed job folder path.")
    path = Path(value).expanduser().resolve()
    if not (path / "manifest.json").is_file():
        raise JobError(f"Job manifest not found in {path}")
    return path


def profile_path(workspace: Path, client_slug: str) -> Path:
    return workspace / "clients" / client_slug / "profile.json"


def validate_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise JobError("Client profile must be a JSON object.")

    for field in ("business_name", "domain"):
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            raise JobError(f"Client profile requires a non-empty '{field}'.")

    for field in (
        "services",
        "locations",
        "specialties",
        "negative_keywords",
        "negative_categories",
        "url_inventory",
    ):
        value = profile.get(field, [])
        if not isinstance(value, list):
            raise JobError(f"Client profile field '{field}' must be a list.")
        profile[field] = value

    seen_urls: set[str] = set()
    for index, item in enumerate(profile["url_inventory"], start=1):
        if not isinstance(item, dict):
            raise JobError(f"URL inventory row {index} must be an object.")
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise JobError(f"URL inventory row {index} requires an absolute http(s) URL.")
        if url in seen_urls:
            raise JobError(f"URL inventory contains a duplicate URL: {url}")
        seen_urls.add(url)
        item.setdefault("title", "")
        item.setdefault("summary", "")

    profile.setdefault("updated_at", utc_now())
    profile.setdefault("source_notes", "")
    return profile


def init_workspace(workspace: Path) -> dict[str, Any]:
    created: list[str] = []
    for name in ("clients", "imports", "jobs", "exports", "incidents"):
        target = workspace / name
        if not target.exists():
            target.mkdir(parents=True)
            created.append(name)
    marker = workspace / ".zed-seo-workspace.json"
    if not marker.exists():
        atomic_write_json(marker, {"version": VERSION, "created_at": utc_now()})
        created.append(marker.name)
    return {"workspace": str(workspace), "created": created, "ready": True}


def save_client(workspace: Path, client_slug: str, source: Path) -> dict[str, Any]:
    init_workspace(workspace)
    profile = validate_profile(read_json(source))
    profile["updated_at"] = utc_now()
    destination = profile_path(workspace, client_slug)
    atomic_write_json(destination, profile)
    return {
        "client_slug": client_slug,
        "profile": str(destination),
        "urls": len(profile["url_inventory"]),
        "services": len(profile["services"]),
        "locations": len(profile["locations"]),
    }


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise JobError("CSV has no header row.")
            fieldnames = [str(name).strip() for name in reader.fieldnames]
            rows = []
            for raw_row in reader:
                normalized = {
                    fieldnames[index]: (raw_row.get(original_name) or "").strip()
                    for index, original_name in enumerate(reader.fieldnames)
                }
                if any(normalized.values()):
                    rows.append(normalized)
    except UnicodeDecodeError as exc:
        raise JobError("CSV must use UTF-8 encoding.") from exc

    keyword_field = next((name for name in fieldnames if name.lower() == "keyword"), None)
    if not keyword_field:
        raise JobError(
            f"CSV requires a 'keyword' column. Found: {', '.join(fieldnames)}"
        )

    if keyword_field != "keyword":
        for row in rows:
            row["keyword"] = row.pop(keyword_field)
        fieldnames[fieldnames.index(keyword_field)] = "keyword"

    empty_rows = [index + 2 for index, row in enumerate(rows) if not row["keyword"]]
    if empty_rows:
        preview = ", ".join(str(value) for value in empty_rows[:5])
        raise JobError(f"CSV contains empty keyword values at source rows: {preview}")
    if not rows:
        raise JobError("CSV contains no keyword rows.")
    return fieldnames, rows


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({name: row.get(name, "") for name in fieldnames})
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def chunked(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def load_manifest(job: Path) -> dict[str, Any]:
    manifest = read_json(job / "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("version") != VERSION:
        raise JobError(f"Unsupported or invalid job manifest in {job}")
    return manifest


def save_manifest(job: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    atomic_write_json(job / "manifest.json", manifest)


def batch_input_path(job: Path, batch_number: int) -> Path:
    return job / "batches" / "input" / f"batch-{batch_number:04d}.json"


def batch_output_path(job: Path, batch_number: int) -> Path:
    return job / "batches" / "output" / f"batch-{batch_number:04d}.json"


def prompt_path(job: Path, batch_number: int) -> Path:
    return job / "prompts" / f"batch-{batch_number:04d}.md"


def start_job(
    workspace: Path,
    client_slug: str,
    kind: str,
    input_csv: Path,
    batch_size: int,
    requested_job_id: str | None = None,
    force_new: bool = False,
) -> dict[str, Any]:
    init_workspace(workspace)
    if kind not in VALID_KINDS:
        raise JobError(f"Unknown job type '{kind}'.")
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise JobError(f"Batch size must be between 1 and {MAX_BATCH_SIZE}.")

    profile_file = profile_path(workspace, client_slug)
    profile = validate_profile(read_json(profile_file))
    if kind == "mapping" and not profile["url_inventory"]:
        raise JobError("Mapping requires a verified URL inventory in the client profile.")

    source_hash = sha256_file(input_csv)
    if not force_new:
        for existing_manifest_path in sorted(
            (workspace / "jobs" / client_slug).glob("*/manifest.json")
        ):
            existing = read_json(existing_manifest_path)
            if (
                isinstance(existing, dict)
                and existing.get("kind") == kind
                and existing.get("source_sha256") == source_hash
                and existing.get("status") != "complete"
            ):
                existing_job = existing_manifest_path.parent
                return {
                    **job_summary(existing_job, existing),
                    "resumed_existing": True,
                    "message": "Matching incomplete job already exists; resume it instead of starting over.",
                }

    source_fields, source_rows = read_csv_rows(input_csv)
    indexed_rows: list[dict[str, Any]] = []
    for index, row in enumerate(source_rows):
        indexed_rows.append({"_row_index": index, **row})

    auto_removed: list[dict[str, Any]] = []
    work_rows: list[dict[str, Any]] = indexed_rows
    if kind == "cleaning":
        negative_terms = [
            str(term).strip().lower()
            for term in profile.get("negative_keywords", [])
            if str(term).strip()
        ]
        work_rows = []
        for row in indexed_rows:
            lowered = row["keyword"].lower()
            matched = next((term for term in negative_terms if term in lowered), None)
            if matched:
                auto_removed.append(
                    {
                        **row,
                        "classification": "REMOVE",
                        "confidence": 100,
                        "reason": f"Matched negative keyword: {matched}",
                    }
                )
            else:
                work_rows.append(row)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_id = require_slug(
        requested_job_id or f"{kind}-{timestamp.lower()}-{uuid4().hex[:8]}",
        "job ID",
    )
    job = workspace / "jobs" / client_slug / job_id
    if job.exists():
        raise JobError(f"Job already exists: {job}")

    (job / "batches" / "input").mkdir(parents=True)
    (job / "batches" / "output").mkdir(parents=True)
    (job / "prompts").mkdir(parents=True)
    (job / "incidents").mkdir(parents=True)

    normalized_input = job / "input.csv"
    write_csv(normalized_input, source_fields, source_rows)
    pinned_profile = job / "client-profile.json"
    atomic_write_json(pinned_profile, profile)
    atomic_write_json(job / "source-rows.json", indexed_rows)
    atomic_write_json(job / "auto-removed.json", auto_removed)

    batches = list(chunked(work_rows, batch_size))
    for number, rows in enumerate(batches, start=1):
        atomic_write_json(
            batch_input_path(job, number),
            {"batch": number, "kind": kind, "rows": rows},
        )

    now = utc_now()
    manifest = {
        "version": VERSION,
        "job_id": job_id,
        "client_slug": client_slug,
        "kind": kind,
        "created_at": now,
        "updated_at": now,
        "status": "complete" if not batches else "ready",
        "source_file": input_csv.name,
        "source_sha256": source_hash,
        "normalized_input_sha256": sha256_file(normalized_input),
        "profile_sha256": sha256_file(pinned_profile),
        "profile_updated_at": profile.get("updated_at"),
        "source_fields": source_fields,
        "total_rows": len(indexed_rows),
        "work_rows": len(work_rows),
        "auto_removed_rows": len(auto_removed),
        "batch_size": batch_size,
        "total_batches": len(batches),
        "completed_batches": [],
        "failed_batches": {},
        "exports": {},
    }
    save_manifest(job, manifest)
    return job_summary(job, manifest)


def next_batch_number(manifest: dict[str, Any]) -> int | None:
    completed = {int(value) for value in manifest.get("completed_batches", [])}
    for number in range(1, int(manifest["total_batches"]) + 1):
        if number not in completed:
            return number
    return None


def job_summary(job: Path, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or load_manifest(job)
    completed = len(manifest.get("completed_batches", []))
    next_number = next_batch_number(manifest)
    total_batches = int(manifest["total_batches"])
    progress_percent = (
        100.0
        if total_batches == 0 and manifest["status"] == "complete"
        else round(100 * completed / max(total_batches, 1), 1)
    )
    return {
        "job": str(job),
        "job_id": manifest["job_id"],
        "client_slug": manifest["client_slug"],
        "kind": manifest["kind"],
        "status": manifest["status"],
        "source_file": manifest["source_file"],
        "source_sha256": manifest["source_sha256"],
        "created_at": manifest["created_at"],
        "updated_at": manifest["updated_at"],
        "profile_updated_at": manifest.get("profile_updated_at"),
        "total_rows": manifest["total_rows"],
        "work_rows": manifest.get("work_rows", manifest["total_rows"]),
        "auto_removed_rows": manifest.get("auto_removed_rows", 0),
        "completed_batches": completed,
        "total_batches": total_batches,
        "next_batch": next_number,
        "progress_percent": progress_percent,
        "failed_batches": manifest.get("failed_batches", {}),
        "exports": manifest.get("exports", {}),
    }


def build_prompt(job: Path, batch_number: int) -> str:
    manifest = load_manifest(job)
    if batch_number < 1 or batch_number > int(manifest["total_batches"]):
        raise JobError(f"Batch {batch_number} is outside this job's range.")
    batch_payload = read_json(batch_input_path(job, batch_number))
    profile = validate_profile(read_json(job / "client-profile.json"))
    rows = batch_payload["rows"]
    compact_rows = [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in rows
    ]

    if manifest["kind"] == "cleaning":
        task = """Classify every keyword as KEEP, REMOVE, or UNSURE.

Rules:
- KEEP means directly relevant to the verified services, locations, or specialties.
- REMOVE means wrong location, wrong specialty, competitor name, or a generic term with no useful SEO intent.
- UNSURE means a human should decide. Prefer UNSURE over an aggressive REMOVE.
- Preserve every keyword byte-for-byte and in the original order.
- Return exactly one result per input row.
- Return only a JSON object with a `classifications` array.
- Each result needs `keyword`, `classification`, integer `confidence` from 0 through 100, and a brief `reason`."""
    else:
        task = """Map every keyword to the best genuine destination.

Rules:
- Use an exact URL from `url_inventory` only when the page is a genuine topical match.
- Use NEW_PAGE for a transactional service or landing-page gap.
- Use BLOG_POST for an informational gap.
- Never invent an existing URL.
- Preserve every keyword byte-for-byte and in the original order.
- Return exactly one result per input row.
- Return only a JSON object with a `mappings` array.
- Each result needs `keyword`, `url`, integer `confidence` from 0 through 100, `intent`, and brief `notes`."""

    return f"""# Zed SEO {manifest['kind'].title()} Batch {batch_number}/{manifest['total_batches']}

You are performing a checkpointed SEO batch for Zed. Follow the literal result contract.

## Client profile

```json
{json.dumps(profile, indent=2, ensure_ascii=False)}
```

## Task

{task}

## Input rows

```json
{json.dumps(compact_rows, indent=2, ensure_ascii=False)}
```
"""


def prepare_batch(job: Path, requested: int | None = None) -> dict[str, Any]:
    manifest = load_manifest(job)
    batch_number = requested or next_batch_number(manifest)
    if batch_number is None:
        return {**job_summary(job, manifest), "message": "All batches are complete."}
    if batch_number in {int(value) for value in manifest["completed_batches"]}:
        raise JobError(f"Batch {batch_number} is already complete.")
    destination = prompt_path(job, batch_number)
    atomic_write_text(destination, build_prompt(job, batch_number))
    manifest["status"] = "running"
    save_manifest(job, manifest)
    return {
        **job_summary(job, manifest),
        "prepared_batch": batch_number,
        "prompt": str(destination),
        "result_contract": "classifications" if manifest["kind"] == "cleaning" else "mappings",
    }


def confidence(value: Any, batch_number: int, row_number: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JobError(
            f"Batch {batch_number} row {row_number} confidence must be a number."
        )
    integer = int(value)
    if integer != value or not 0 <= integer <= 100:
        raise JobError(
            f"Batch {batch_number} row {row_number} confidence must be an integer from 0 through 100."
        )
    return integer


def validate_result_rows(
    kind: str,
    input_rows: list[dict[str, Any]],
    payload: Any,
    profile: dict[str, Any],
    batch_number: int,
) -> list[dict[str, Any]]:
    key = "classifications" if kind == "cleaning" else "mappings"
    rows = payload.get(key) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise JobError(f"Batch {batch_number} result must contain a '{key}' array.")
    if len(rows) != len(input_rows):
        raise JobError(
            f"Batch {batch_number} returned {len(rows)} rows for {len(input_rows)} inputs."
        )

    allowed_urls = {item["url"] for item in profile["url_inventory"]}
    validated: list[dict[str, Any]] = []
    for index, (source, result) in enumerate(zip(input_rows, rows), start=1):
        if not isinstance(result, dict):
            raise JobError(f"Batch {batch_number} row {index} must be an object.")
        if result.get("keyword") != source["keyword"]:
            raise JobError(
                f"Batch {batch_number} row {index} changed or reordered keyword "
                f"'{source['keyword']}'."
            )
        checked = {**source, "keyword": result["keyword"]}
        checked["confidence"] = confidence(result.get("confidence"), batch_number, index)

        if kind == "cleaning":
            classification = result.get("classification")
            if classification not in VALID_CLASSIFICATIONS:
                raise JobError(
                    f"Batch {batch_number} row {index} has invalid classification '{classification}'."
                )
            reason = result.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                raise JobError(f"Batch {batch_number} row {index} requires a reason.")
            checked.update(
                {"classification": classification, "reason": reason.strip()}
            )
        else:
            target = result.get("url")
            if target not in allowed_urls | SPECIAL_MAPPING_TARGETS:
                raise JobError(
                    f"Batch {batch_number} row {index} uses an unknown URL '{target}'."
                )
            intent = result.get("intent")
            notes = result.get("notes")
            if not isinstance(intent, str) or not intent.strip():
                raise JobError(f"Batch {batch_number} row {index} requires intent.")
            if not isinstance(notes, str) or not notes.strip():
                raise JobError(f"Batch {batch_number} row {index} requires notes.")
            recommendation = (
                "New Page"
                if target == "NEW_PAGE"
                else "Blog Post"
                if target == "BLOG_POST"
                else "Existing URL"
            )
            checked.update(
                {
                    "mapped_url": target,
                    "search_intent": intent.strip(),
                    "recommendation": recommendation,
                    "notes": notes.strip(),
                }
            )
        validated.append(checked)
    return validated


def record_batch(
    job: Path,
    batch_number: int,
    result_file: Path,
    replace: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(job)
    input_payload = read_json(batch_input_path(job, batch_number))
    result_payload = read_json(result_file)
    profile = validate_profile(read_json(job / "client-profile.json"))
    validated = validate_result_rows(
        manifest["kind"], input_payload["rows"], result_payload, profile, batch_number
    )
    output = batch_output_path(job, batch_number)
    new_payload = {
        "batch": batch_number,
        "kind": manifest["kind"],
        "recorded_at": utc_now(),
        "rows": validated,
    }

    if output.exists() and not replace:
        existing = read_json(output)
        if existing.get("rows") != validated:
            raise JobError(
                f"Batch {batch_number} is already complete with different results. "
                "Use --replace only after intentional human review."
            )
    else:
        atomic_write_json(output, new_payload)

    completed = {int(value) for value in manifest.get("completed_batches", [])}
    completed.add(batch_number)
    manifest["completed_batches"] = sorted(completed)
    manifest.get("failed_batches", {}).pop(str(batch_number), None)
    manifest["status"] = (
        "complete" if len(completed) == int(manifest["total_batches"]) else "running"
    )
    save_manifest(job, manifest)
    return {**job_summary(job, manifest), "recorded_batch": batch_number}


SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"sk-[0-9A-Za-z_-]{12,}"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret)\s*[=:]\s*)[^\s,;]+"),
)


def sanitize_error(message: str, max_length: int = 1200) -> str:
    cleaned = str(message).replace("\x00", " ")
    for pattern in SECRET_PATTERNS:
        if pattern.groups:
            cleaned = pattern.sub(r"\1[REDACTED]", cleaned)
        else:
            cleaned = pattern.sub("[REDACTED]", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned[:max_length]


def fail_batch(job: Path, batch_number: int, message: str) -> dict[str, Any]:
    manifest = load_manifest(job)
    if batch_number in {int(value) for value in manifest.get("completed_batches", [])}:
        raise JobError(f"Cannot fail completed batch {batch_number}.")
    if batch_number < 1 or batch_number > int(manifest["total_batches"]):
        raise JobError(f"Batch {batch_number} is outside this job's range.")

    safe_message = sanitize_error(message)
    failed = manifest.setdefault("failed_batches", {})
    previous = failed.get(str(batch_number), {})
    failed[str(batch_number)] = {
        "attempts": int(previous.get("attempts", 0)) + 1,
        "last_error": safe_message,
        "last_failed_at": utc_now(),
    }
    manifest["status"] = "failed"
    save_manifest(job, manifest)

    incident_id = f"seo-{uuid4().hex[:12]}"
    incident = {
        "incident_id": incident_id,
        "created_at": utc_now(),
        "client_slug": manifest["client_slug"],
        "job_id": manifest["job_id"],
        "kind": manifest["kind"],
        "failed_batch": batch_number,
        "completed_batches": len(manifest.get("completed_batches", [])),
        "total_batches": manifest["total_batches"],
        "source_sha256": manifest["source_sha256"],
        "error": safe_message,
    }
    local_incident = job / "incidents" / f"{incident_id}.json"
    workspace_incident = job.parents[2] / "incidents" / f"{incident_id}.json"
    atomic_write_json(local_incident, incident)
    atomic_write_json(workspace_incident, incident)
    return {
        **job_summary(job, manifest),
        "incident_id": incident_id,
        "incident": str(workspace_incident),
    }


def result_fieldnames(
    source_fields: list[str], kind: str
) -> tuple[list[str], list[str] | None, list[str] | None]:
    base = [name for name in source_fields if not name.startswith("_")]
    if kind == "cleaning":
        all_fields = list(dict.fromkeys(base + ["classification", "confidence", "reason"]))
        return all_fields, all_fields, all_fields
    mapping_fields = list(
        dict.fromkeys(
            base
            + [
                "mapped_url",
                "confidence",
                "search_intent",
                "recommendation",
                "notes",
            ]
        )
    )
    return mapping_fields, None, None


def collect_results(job: Path, manifest: dict[str, Any], allow_partial: bool) -> list[dict[str, Any]]:
    if manifest["status"] != "complete" and not allow_partial:
        raise JobError(
            "Job is incomplete. Resume it or pass --allow-partial for a clearly partial export."
        )
    rows: list[dict[str, Any]] = []
    if manifest["kind"] == "cleaning":
        rows.extend(read_json(job / "auto-removed.json"))
    for batch_number in sorted(int(value) for value in manifest["completed_batches"]):
        rows.extend(read_json(batch_output_path(job, batch_number))["rows"])
    rows.sort(key=lambda item: int(item["_row_index"]))
    return rows


def export_job(job: Path, allow_partial: bool = False) -> dict[str, Any]:
    manifest = load_manifest(job)
    rows = collect_results(job, manifest, allow_partial)
    workspace = job.parents[2]
    output_dir = workspace / "exports" / manifest["client_slug"] / manifest["job_id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    all_fields, keep_fields, review_fields = result_fieldnames(
        manifest["source_fields"], manifest["kind"]
    )
    exports: dict[str, str] = {}

    suffix = "-partial" if manifest["status"] != "complete" else ""
    if manifest["kind"] == "cleaning":
        all_path = output_dir / f"cleaned-all{suffix}.csv"
        keep_path = output_dir / f"cleaned-keep{suffix}.csv"
        review_path = output_dir / f"cleaned-review{suffix}.csv"
        write_csv(all_path, all_fields, rows)
        write_csv(
            keep_path,
            keep_fields or all_fields,
            [row for row in rows if row.get("classification") == "KEEP"],
        )
        write_csv(
            review_path,
            review_fields or all_fields,
            [
                row
                for row in rows
                if row.get("classification") == "UNSURE"
                or int(row.get("confidence", 0)) < 70
            ],
        )
        exports = {
            "all": str(all_path),
            "keep": str(keep_path),
            "review": str(review_path),
        }
    else:
        mapping_path = output_dir / f"keyword-mapping{suffix}.csv"
        write_csv(mapping_path, all_fields, rows)
        exports = {"mapping": str(mapping_path)}

    manifest["exports"] = exports
    save_manifest(job, manifest)
    return {**job_summary(job, manifest), "exported_rows": len(rows)}


def doctor(workspace: Path) -> dict[str, Any]:
    init_workspace(workspace)
    jobs: list[dict[str, Any]] = []
    problems: list[str] = []
    for manifest_path in sorted((workspace / "jobs").glob("*/*/manifest.json")):
        job = manifest_path.parent
        try:
            manifest = load_manifest(job)
            summary = job_summary(job, manifest)
            if manifest["normalized_input_sha256"] != sha256_file(job / "input.csv"):
                problems.append(f"Normalized input changed: {job}")
            if manifest["profile_sha256"] != sha256_file(job / "client-profile.json"):
                problems.append(f"Pinned client profile changed: {job}")
            for batch_number in manifest.get("completed_batches", []):
                if not batch_output_path(job, int(batch_number)).is_file():
                    problems.append(
                        f"Manifest marks batch {batch_number} complete but output is missing: {job}"
                    )
            jobs.append(summary)
        except (JobError, KeyError, TypeError, ValueError) as exc:
            problems.append(f"{job}: {exc}")
    return {
        "workspace": str(workspace),
        "jobs": jobs,
        "incomplete_jobs": [job for job in jobs if job["status"] != "complete"],
        "problems": problems,
        "healthy": not problems,
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    subcommands = command.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="Create a Cowork project workspace.")
    init.add_argument("--workspace", required=True)

    client = subcommands.add_parser("client-put", help="Validate and save a client profile.")
    client.add_argument("--workspace", required=True)
    client.add_argument("--client", required=True)
    client.add_argument("--profile", required=True)

    start = subcommands.add_parser("start", help="Create a checkpointed SEO job.")
    start.add_argument("--workspace", required=True)
    start.add_argument("--client", required=True)
    start.add_argument("--kind", choices=sorted(VALID_KINDS), required=True)
    start.add_argument("--input", required=True)
    start.add_argument("--batch-size", type=int)
    start.add_argument("--job-id")
    start.add_argument(
        "--force-new",
        action="store_true",
        help="Create a new job even when the same incomplete source already exists.",
    )

    status = subcommands.add_parser("status", help="Show job progress.")
    status.add_argument("--job", required=True)

    prepare = subcommands.add_parser("prepare", help="Write the next batch prompt.")
    prepare.add_argument("--job", required=True)
    prepare.add_argument("--batch", type=int)

    record = subcommands.add_parser("record", help="Validate and checkpoint a batch result.")
    record.add_argument("--job", required=True)
    record.add_argument("--batch", type=int, required=True)
    record.add_argument("--result", required=True)
    record.add_argument("--replace", action="store_true")

    fail = subcommands.add_parser("fail", help="Record a sanitized batch failure.")
    fail.add_argument("--job", required=True)
    fail.add_argument("--batch", type=int, required=True)
    fail.add_argument("--message", required=True)

    export = subcommands.add_parser("export", help="Create validated CSV exports.")
    export.add_argument("--job", required=True)
    export.add_argument("--allow-partial", action="store_true")

    check = subcommands.add_parser("doctor", help="Audit a Cowork project workspace.")
    check.add_argument("--workspace", required=True)
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            payload = init_workspace(workspace_path(args.workspace))
        elif args.command == "client-put":
            payload = save_client(
                workspace_path(args.workspace),
                require_slug(args.client, "client slug"),
                Path(args.profile).expanduser().resolve(),
            )
        elif args.command == "start":
            batch_size = args.batch_size or DEFAULT_BATCH_SIZES[args.kind]
            payload = start_job(
                workspace_path(args.workspace),
                require_slug(args.client, "client slug"),
                args.kind,
                Path(args.input).expanduser().resolve(),
                batch_size,
                args.job_id,
                args.force_new,
            )
        elif args.command == "status":
            job = job_path(args.job)
            payload = job_summary(job)
        elif args.command == "prepare":
            payload = prepare_batch(job_path(args.job), args.batch)
        elif args.command == "record":
            payload = record_batch(
                job_path(args.job),
                args.batch,
                Path(args.result).expanduser().resolve(),
                args.replace,
            )
        elif args.command == "fail":
            payload = fail_batch(job_path(args.job), args.batch, args.message)
        elif args.command == "export":
            payload = export_job(job_path(args.job), args.allow_partial)
        elif args.command == "doctor":
            payload = doctor(workspace_path(args.workspace))
        else:
            raise JobError(f"Unsupported command: {args.command}")
        emit(payload)
        return 0
    except JobError as exc:
        emit({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
