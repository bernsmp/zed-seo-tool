# Zed SEO Operator

The Cowork home for Zed's keyword research, cleaning, and mapping workflow. It is designed for Carlos first and can support other Zed operators later.

## What it adds

| Skill | Use it for |
|---|---|
| `zed-seo-setup` | First-time setup and connector verification |
| `zed-seo-client` | Create or update a client profile and URL inventory |
| `zed-seo-research` | Pull keyword research through the official SEMrush connector |
| `zed-seo-clean` | Clean and classify a keyword list with durable checkpoints |
| `zed-seo-map` | Map kept keywords to existing URLs or content gaps |
| `zed-seo-resume` | Continue the next unfinished batch without starting over |
| `zed-seo-report` | Package a sanitized problem report with the exact failed batch |

## First run

1. In Claude, connect the official **Semrush** connector and authenticate with the approved Trackable Med account.
2. Create a dedicated Cowork Project backed by a folder copied from the included workspace template.
3. Install this plugin from the `.plugin` file.
4. Say **Set up Zed SEO**.

No Anthropic, Gemini, SEMrush, or Cloudflare API keys belong in the plugin or project folder. Cowork supplies the model; the official connector supplies SEMrush access.

In the skill command examples, `$WORKSPACE`, `$CLIENT_SLUG`, `$INPUT_CSV`, `$JOB`, `$BATCH_NUMBER`, and `$RESULT_JSON` are notation. Cowork must substitute the actual absolute value in every command and must never execute an unset shell variable.

## Durable state

Every job is stored under the Cowork project folder with an immutable normalized input, numbered input and output batches, a manifest, exports, and sanitized incidents. If a task stops, `zed-seo-resume` locates the first unfinished batch and continues it. Completed batches are never silently rerun.

## Current boundary

Version 0.1.1 runs while Cowork is active and resumes safely in a later task. It pins the client profile used by each job and prevents accidental duplicate jobs for the same unfinished source file. It does not continue executing after Cowork and Claude Desktop are closed. The existing Streamlit app remains the fallback during the pilot.
