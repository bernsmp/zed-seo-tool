---
name: zed-seo-report
description: >
  Package a sanitized Zed SEO problem report while preserving completed work.
  Use when Carlos says "report a problem", "report SEO error", "this failed",
  "the tool is stuck", "send this to Max", or selects this skill as the error button.
metadata:
  version: "0.1.0"
---

# Report an SEO Problem

This skill is the clickable error-report action for Carlos. It diagnoses and packages; it does not erase or restart work.

## 1. Inspect current state

Run `doctor` and identify the affected job. Read its manifest and the most recent failed-batch entry. Do not read or include full keyword payloads unless needed to validate row integrity locally.

## 2. Create or refresh the incident

If the failure has not already been recorded, run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" fail \
  --job "$JOB" \
  --batch "$BATCH_NUMBER" \
  --message "$SAFE_ERROR_SUMMARY"
```

The script strips common API keys, bearer tokens, and secrets. Never paste credentials into the message anyway.

## 3. Give Carlos the practical answer

State:

- whether saved work is safe;
- completed and total batches;
- failed batch;
- incident reference;
- whether `zed-seo-resume` can retry immediately;
- the one thing Max needs if the problem requires a code change.

Do not tell Carlos to clear completed batches or start fresh unless the workspace doctor proves the normalized input or checkpoint is corrupt.
