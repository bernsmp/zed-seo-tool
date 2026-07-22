# Zed SEO Cowork Live Acceptance

Updated: 2026-07-22

## Verified

- `zed-seo-operator.plugin` builds as a valid archive.
- Claude Code 2.1.217 reports `Validation passed` for the plugin manifest.
- Five deterministic tests pass, including a synthetic 40,000-keyword run with 400 batches that stops after batch 42 and resumes at batch 43 without source re-upload.
- Version 0.1.0 was uploaded to Max's Claude account through **Customize → Plugins**.
- Claude displayed version 0.1.0 as enabled, sourced from an uploaded file, authored by Max Bernstein, with all seven skills visible.
- The official Semrush connector appears in Claude's connector directory and was installed.

Version 0.1.1 was rebuilt after this UI check. It adds pinned client-profile snapshots and duplicate unfinished-source protection. Its archive and tests are verified locally, but the final package still needs to be uploaded to replace version 0.1.0 in Claude.

## External gate

The Semrush connector is awaiting authentication with the approved Trackable Med SEMrush account. The login page is open. No account selection, password entry, permission approval, or connector data call was performed.

Carlos has not yet installed the package or completed a real client run. Local validation and Max-account installation do not establish Carlos acceptance.

## Acceptance run

1. Upload version 0.1.1 so it replaces the earlier package.
2. Authenticate the connector with the correct SEMrush account.
3. Unzip `dist/zed-seo-cowork-project.zip` and use the folder for a dedicated Cowork Project.
4. Add the contents of `PROJECT_INSTRUCTIONS.md` to the project's instructions.
5. Run `/zed-seo-setup` and verify a small read-only SEMrush query.
6. Create or import one real client profile.
7. Clean at least two batches, stop the task, and resume it.
8. Map the kept-keyword export and produce `keyword-mapping.csv`.
9. Run `/zed-seo-report` once and verify the incident contains no credentials or full keyword payload.

The existing Streamlit app remains the fallback until all nine steps pass.
