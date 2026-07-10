# Zed SEO Tool

Inherits: `/Users/maxb/Desktop/mb-brain/AGENTS.md`

## Local Scope

Streamlit keyword-cleaning, mapping, content-brief, and audit app deployed at `https://zed-seo-tool.streamlit.app`.

## Source Of Truth

- Repository and deployment branch: `main` on `bernsmp/zed-seo-tool`
- Live app: `https://zed-seo-tool.streamlit.app`
- Runtime secrets: Streamlit Community Cloud app settings. Never commit `.env`, `.env.local`, or `secrets.toml`.
- LLM provider code: `utils/llm.py`

## Safety

- Do not recursively scan generated app data or browser caches.
- Run one check at a time with capped output.
- Do not start a Streamlit server or run broad browser/Playwright QA without Max's approval.
- Before and after any browser test, check for leftover `streamlit`, `playwright`, or app-server processes.
- Keep API keys only in Streamlit Secrets or local ignored env files. Never print or commit their values.

## Commands

Safe checks:

- `.venv/bin/python -m py_compile app.py utils/llm.py`
- `.venv/bin/python -m pytest` when tests are targeted and do not start a server
- `git diff --check`

Risky checks, use only with approval:

- `.venv/bin/streamlit run app.py`
- Browser or Playwright-based test suites

## Local Notes

- The live LLM provider is configured with `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, and `DEFAULT_LLM_MODEL` in Streamlit Secrets.
- Preserve the existing Haiku model unless Max explicitly requests a model-cost change.
