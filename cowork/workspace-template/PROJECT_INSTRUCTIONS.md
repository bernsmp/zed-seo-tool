# Zed SEO Project Instructions

This project is Carlos's operating surface for Zed SEO research, keyword cleaning, and keyword mapping.

## Start every task

1. Use the Zed SEO Operator plugin.
2. Read the relevant client profile before making an SEO judgment.
3. Check for an incomplete job before creating a new job for the same client and type.
4. Treat the job manifest and completed batch files as the source of truth for progress.

## Operating rules

- Use the official Semrush connector for live SEMrush data.
- Preserve keyword text, source columns, domain names, and URLs exactly.
- Never call a partial connector response or partial job complete.
- Never restart a resumable job merely because a task or model response failed.
- Keep completed batches and resume from the first unfinished batch.
- Route ambiguous keywords to `UNSURE` for Carlos's judgment.
- Map only to URLs in the client profile. Use `NEW_PAGE` or `BLOG_POST` for genuine gaps.
- Export only after deterministic validation succeeds.
- Never write credentials into this project folder.

## Recovery

When a batch fails validation, repair and retry that batch twice. If it still fails, record the failure with `zed-seo-report`, preserve every completed batch, and give Carlos the incident reference plus the exact resume command.
