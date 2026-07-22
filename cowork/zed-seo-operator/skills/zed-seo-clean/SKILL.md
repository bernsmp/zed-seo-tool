---
name: zed-seo-clean
description: >
  Run checkpointed Zed SEO keyword cleaning inside Cowork. Use when Carlos says
  "clean these keywords", "run keyword cleaning", "classify the list", "remove
  irrelevant keywords", or provides a keyword CSV for cleaning.
metadata:
  version: "0.1.0"
---

# Clean Keywords

Every completed batch must be validated and saved before the next batch begins. Never keep the only copy of results in conversation context.

## 1. Prevent accidental restarts

Run the workspace doctor:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" doctor --workspace "$WORKSPACE"
```

If an incomplete cleaning job exists for the same client and source, resume it. Do not create a duplicate job unless Carlos explicitly chooses to start over.

## 2. Start the job

Confirm the client profile exists and the source CSV contains a `keyword` column. Start with the default 100-row batch:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" start \
  --workspace "$WORKSPACE" \
  --client "$CLIENT_SLUG" \
  --kind cleaning \
  --input "$INPUT_CSV"
```

Save the returned job path as `$JOB`.

## 3. Process checkpointed batches

For each unfinished batch:

1. Run `prepare`:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" prepare --job "$JOB"
   ```

2. Read the generated prompt file in full.
3. Perform the classification yourself. Return only the required JSON object in a temporary result file.
4. Record it:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" record \
     --job "$JOB" \
     --batch "$BATCH_NUMBER" \
     --result "$RESULT_JSON"
   ```

5. Delete the temporary result file after `record` succeeds.
6. Continue from the newly reported next batch.

The validator enforces exact row count, order, keyword text, classification labels, confidence, and reasons. If validation fails, repair only that batch and retry twice. Do not alter earlier completed batches.

## 4. Handle an unrecoverable batch

After two repair attempts, record the failure:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" fail \
  --job "$JOB" \
  --batch "$BATCH_NUMBER" \
  --message "$SAFE_ERROR_SUMMARY"
```

Stop with the incident reference and tell Carlos the completed batch count. Do not discard the job.

## 5. Export

When every batch is complete:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jobctl.py" export --job "$JOB"
```

Give Carlos the `cleaned-all.csv`, `cleaned-keep.csv`, and `cleaned-review.csv` paths. State the KEEP, REMOVE, UNSURE, and low-confidence counts. The `cleaned-keep.csv` file is the default input for mapping.
