---
name: zed-seo-research
description: >
  Pull SEO keyword research through the official Semrush connector and save a
  provenance-preserving CSV for downstream cleaning. Use when Carlos says
  "research keywords", "pull SEMrush keywords", "competitor gap", "keyword
  gap", "organic keywords", or "get keywords for this client".
metadata:
  version: "0.1.0"
---

# Research Keywords with SEMrush

Read `${CLAUDE_PLUGIN_ROOT}/references/semrush-connector.md` before calling the connector.

## 1. Lock the query

Confirm the client profile, target or competitor domain, country database, report type, and requested row count. Default to the client profile's domain and US database only when the request and profile make that correct.

## 2. Use the official connector

Use the verified **Semrush** connector. Paginate when available. After every completed page, write the returned rows to `imports/<client-slug>/semrush/` so a connector interruption cannot erase prior pages.

Preserve keyword text and all returned source fields. Add provenance columns for `source_domain`, `database`, `report_type`, and `retrieved_at` when they are not already present.

Never manufacture missing metrics. If the connector or plan returns fewer rows than requested, state the exact returned count and limit.

## 3. Merge deterministically

Create one UTF-8 CSV with a literal `keyword` header. Deduplicate exact duplicate rows only. Save it under:

`imports/<client-slug>/semrush/<date>-<report-type>.csv`

## 4. Handoff

Report the source domains, database, requested rows, returned rows, final rows, and file path. Offer to begin `zed-seo-clean` using that exact file.
