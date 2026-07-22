# Zed SEO Cowork

Inherits: `/Users/maxb/Desktop/Vibe Projects/Zed_SEO Tool/AGENTS.md`

## Local Scope

Cowork plugin source, deterministic job-ledger scripts, project template, packaging, and tests for the Carlos-facing Zed SEO workflow.

## Source Of Truth

- Plugin source: `zed-seo-operator/`
- Job contract: `zed-seo-operator/scripts/jobctl.py`
- Cowork project starter: `workspace-template/`
- Installable artifact: `dist/zed-seo-operator.plugin`

## Safety

- Never place API keys, OAuth tokens, client exports, or live keyword data in the plugin package or repository.
- SEMrush access must use the official Claude connector authenticated by the operator.
- Keep client profiles and job outputs in the operator-selected Cowork project folder, outside the plugin.
- Do not deploy or replace the existing Streamlit app from this folder.
- Do not claim an end-to-end Cowork acceptance pass until the packaged plugin is installed in Cowork and tested against a real connector session.

## Safe Commands

- `python3 -m unittest discover -s tests -v`
- `python3 scripts/validate_plugin.py`
- `python3 scripts/build_plugin.py`
- `claude plugin validate zed-seo-operator`
