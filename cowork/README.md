# Zed SEO Operator for Cowork

This folder contains the Carlos-facing Cowork version of the Zed SEO workflow.

It keeps the current Streamlit application available as a fallback while moving the operator experience into Cowork:

- the official SEMrush connector supplies live research data;
- Cowork performs keyword relevance and mapping judgments;
- `jobctl.py` owns deterministic batching, validation, checkpoints, resume, exports, and incident reports;
- the Cowork project folder holds client profiles and job state across conversations.

## Build

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_plugin.py
python3 scripts/build_plugin.py
```

The build creates `dist/zed-seo-operator.plugin`, which Carlos can upload from Cowork under **Customize → Plugins**.

## Acceptance gate

Local tests prove the job ledger and package structure. The release is not accepted until Carlos installs the plugin, authorizes the official SEMrush connector, and completes this live sequence:

1. pull or upload a keyword source;
2. clean at least two batches;
3. interrupt the task deliberately;
4. resume from the saved batch;
5. map the kept keywords;
6. export the final CSV;
7. run **Report SEO problem** once and confirm the sanitized incident file.
