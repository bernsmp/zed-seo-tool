---
name: zed-seo-resume
description: >
  Resume a stopped or failed Zed SEO cleaning or mapping job from the first
  unfinished batch. Use when Carlos says "resume", "continue", "it stopped",
  "pick up from batch", "continue cleaning", or "continue mapping".
metadata:
  version: "0.1.0"
---

# Resume an SEO Job

## 1. Locate the durable checkpoint

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" doctor --workspace "$WORKSPACE"
```

If exactly one incomplete job matches Carlos's client and job type, use it. If more than one matches, show the job IDs, source names, completed batches, and creation times and ask which one to continue.

Never ask Carlos to re-upload the source when the job's normalized `input.csv` and manifest pass the doctor check.

## 2. Continue from the first unfinished batch

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" prepare --job "$JOB"
```

Process and record the generated batch according to the job kind. Keep going until complete or until the same current batch fails validation twice.

Completed output files are immutable by default. Do not pass `--replace` unless Carlos intentionally reviewed and approved changing a completed batch.

## 3. Close

Report the starting checkpoint, ending checkpoint, remaining batches, and export paths when complete. Carlos should never need to know or enter a batch number for a normal resume.
