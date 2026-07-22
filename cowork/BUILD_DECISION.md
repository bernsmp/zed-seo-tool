# Zed SEO Cowork Build Decision

Date: 2026-07-22

## Decision

Build the full operator workflow as a dedicated Cowork Project plus the installable `zed-seo-operator` plugin.

The official Semrush connector owns live SEO retrieval. Cowork owns AI judgments. A deterministic project-folder ledger owns normalized inputs, numbered batches, schema validation, checkpoints, resume, exports, and sanitized incidents.

Keep the existing Streamlit app live as a fallback until Carlos completes the acceptance run.

## Why this v1

The immediate failures came from external API credits, truncated or malformed structured output, and long jobs stopping after dozens of batches. Running the judgment inside Cowork removes separate Anthropic and Gemini credentials from Carlos's workflow. The job ledger prevents a stopped Cowork task from erasing or duplicating completed work.

The official Semrush connector is read-only and remains separately authenticated by the operator. The plugin does not contain a SEMrush API key.

## Carlos flow

1. Open the Zed SEO Cowork Project.
2. Ask for SEMrush research or upload a CSV.
3. Run cleaning.
4. Review the `UNSURE` and low-confidence export.
5. Run mapping from the kept-keywords export.
6. Download the validated mapping CSV.
7. Select **Report SEO problem** if a batch cannot be repaired.

Normal resume does not require Carlos to remember a batch number or re-upload the source file.

## Explicit v1 boundaries

- Work runs while Cowork is active. It resumes safely after closure but does not continue executing with Claude Desktop closed.
- The plugin uses the official Semrush connector's available reports and plan limits. It does not claim unlimited 40K-row retrieval.
- Version 0.1 uses filesystem checkpoints instead of a new remote MCP job service. This avoids duplicating the deployed Streamlit engine and avoids introducing another authentication surface before Carlos validates the Cowork interaction.
- An MCP App progress panel and always-on remote worker are phase-two options. Add them only if the pilot proves that background execution after Cowork closes materially improves the job.

## Acceptance proof

- Native Claude plugin validation passes.
- Deterministic unit tests pass, including a synthetic 40,000-keyword job that stops after batch 42 and resumes at batch 43 without source re-upload.
- The remaining gate is a live Cowork install with Carlos's authenticated Semrush connector and a real client dataset.
