---
name: zed-seo-map
description: >
  Map cleaned keywords to verified client URLs or content gaps with durable
  checkpoints. Use when Carlos says "map keywords", "run keyword mapping",
  "map to URLs", "find content gaps", or asks what pages should target the
  cleaned keywords.
metadata:
  version: "0.1.0"
---

# Map Keywords

Mapping uses only the verified URL inventory in the client profile. Never invent an existing destination.

## 1. Check prerequisites and prior progress

- Confirm `clients/<client-slug>/profile.json` has a current URL inventory.
- Prefer the completed cleaning job's `cleaned-keep.csv` export.
- Run `doctor` and resume a matching incomplete mapping job instead of starting over.

## 2. Start the job

Use 50-row batches because mapping output is larger than cleaning output:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" start \
  --workspace "$WORKSPACE" \
  --client "$CLIENT_SLUG" \
  --kind mapping \
  --input "$INPUT_CSV"
```

Save the returned job path as `$JOB`.

## 3. Process batches

Repeat `prepare → read prompt → write result JSON → record` exactly as in keyword cleaning. Read `${CLAUDE_PLUGIN_ROOT}/references/result-contracts.md` when repairing a validation error.

Accept only:

- an exact existing URL from the client profile;
- `NEW_PAGE` for a transactional page gap;
- `BLOG_POST` for an informational gap.

The validator rejects row loss, reordering, changed keywords, and invented URLs. Repair the current batch twice, then run `fail` and preserve the checkpoint.

## 4. Export

When complete:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" export --job "$JOB"
```

Give Carlos the `keyword-mapping.csv` path and summarize Existing URL, New Page, Blog Post, low-confidence, and total counts.
