# SEO Keyword Tool - Build Todo

## Phase A: Scaffold

- [x] 1. Project setup (requirements.txt, .env.example, .gitignore, folder structure)
- [x] 2. App shell (app.py with st.navigation routing, sidebar, session state init)

## Phase B: Utilities (Independent)

- [x] 3. `utils/llm.py` — OpenRouter client (classify, map, generate profile, cost estimate, retry logic)
- [x] 4. `utils/crawler.py` — Site crawler (sitemap parsing + trafilatura content extraction)
- [x] 5. `utils/data.py` — Data layer (CSV parsing, JSON save/load, client management, export)

## Phase C: Pages (Sequential)

- [x] 6. Client Setup page — domain input, crawl, LLM profile generation, editable form, save/load
- [x] 7. Keyword Cleaning page — CSV upload, batch LLM classification, 3-tab review UI, export
- [x] 8. Keyword Mapping page — CSV upload, batch URL matching, review UI, export

## Phase D: Harden

- [x] 9. Error handling audit (LLM retries, CSV validation, crawl fallbacks, session state)
- [x] 10. End-to-end testing (full workflow with real data, edge cases)

---

## Review Section

- **Summary of changes made:**
  - Created full project structure: app.py, 3 pages, 3 utility modules
  - `app.py` — Streamlit entry point with st.navigation routing and sidebar client selector
  - `utils/data.py` — All file I/O: client profiles (JSON), CSV parsing, result save/load, export
  - `utils/llm.py` — OpenRouter client with structured JSON output, tenacity retry (3x exponential), batch classification/mapping/profile generation, cost estimator
  - `utils/crawler.py` — Sitemap discovery (ultimate-sitemap-parser) + content extraction (trafilatura)
  - `pages/client_setup.py` — Domain input, crawl site, LLM profile generation, editable form, negative keywords, save/load
  - `pages/keyword_cleaning.py` — CSV upload, batch processing with progress, 3-tab review (Keep/Remove/Unsure), data_editor for re-classification, auto-save per batch, CSV export
  - `pages/keyword_mapping.py` — CSV upload, batch URL mapping, 3-tab results (Existing/New Page/Blog), auto-save, CSV export
  - Error handling: API key validation, retry logic, CSV delimiter auto-detection, graceful crawl failures

- **New dependencies added:**
  - streamlit, openai, trafilatura, ultimate-sitemap-parser, pandas, tenacity, python-dotenv

- **Environment variables needed:**
  - `OPENROUTER_API_KEY` — Required for LLM calls
  - `DEFAULT_LLM_MODEL` — Optional (defaults to anthropic/claude-sonnet-4-5-20250929)

- **Known limitations:**
  - SEMRush API not integrated (v1.1 — CSV upload covers all v1 use cases)
  - No "Unsure" re-classification pass (v1.1)
  - No near-duplicate keyword grouping (v1.1)
  - No Excel export formatting (v1.1)
  - Browser refresh during processing requires manual "Load Previous Results" click
  - Data editor changes in review tabs don't persist back to results (display only for now)
