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
  - `DEFAULT_LLM_MODEL` — Optional (defaults to anthropic/claude-haiku-4.5)

- **Known limitations:**
  - SEMRush API not integrated (v1.1 — CSV upload covers all v1 use cases)
  - No "Unsure" re-classification pass (v1.1)
  - No near-duplicate keyword grouping (v1.1)
  - No Excel export formatting (v1.1)
  - Browser refresh during processing requires manual "Load Previous Results" click
  - Data editor changes in review tabs don't persist back to results (display only for now)

---

## Post-Build Fixes (Session 2)

- **UI/UX improvements:**
  - Moved "How It Works" page under "Resources" section in sidebar (separated from Workflow)
  - Added branded hero headers with step badges (Step 1/2/3) to all pages
  - Added contextual descriptions to each page header
  - How It Works page gets distinct purple theme to stand out from workflow pages
  - Hidden Streamlit's default anchor link icons on headers via CSS

- **Bug fixes:**
  - Fixed invalid OpenRouter model ID: `anthropic/claude-haiku-4-5-20251001` → `anthropic/claude-haiku-4.5`
  - Fixed JSON parser: Haiku returns JSON inside markdown code fences — added regex extraction
  - Fixed response_format: `json_schema` mode doesn't work with Claude on OpenRouter — switched to `json_object` + explicit JSON instructions in prompts
  - Updated MODEL_PRICING table with correct model IDs

- **Testing results:**
  - Client Setup: Crawled trackablemed.com (50 pages), profile generated with accurate data
  - Keyword Cleaning: 10 test keywords classified correctly (KEEP/REMOVE/UNSURE with good reasoning)
  - Keyword Mapping: 5 keywords mapped to correct URLs with 88-95% confidence scores

---

## Session 3: QC, Confidence Scores, UX Polish

### Todo

- [x] 1. Add confidence scores (0-100) to keyword classifications
  - Updated LLM prompt to return confidence per keyword
  - ProgressColumn bars in results tables (cleaning + mapping)
  - Avg Confidence metric in summary row

- [x] 2. Add QC summary after cleaning completes
  - Second LLM pass reviews classification quality
  - QC card with score, flagged keywords, tips
  - "Flagged for Review" tab for confidence < 70%

- [x] 3. Add clear instructions/hand-holding on every page
  - All 3 pages: "How does this work?" expandable guide with numbered steps
  - Info callouts replacing plain st.warning/st.info
  - Help tooltips on all profile text areas
  - Descriptive captions on every tab and section
  - "Next step" callouts guiding users through the workflow

- [x] 4. Brainstorm & document additional tool ideas (present to user)

---

## Additional Tool Ideas (Brainstorm)

### High-Impact (Next Sprint)

1. **Content Gap Analyzer**
   - Compare client's existing content coverage against keyword clusters
   - Show which topics have pages vs. which are uncovered
   - Output: prioritized list of new pages/posts to create, sorted by opportunity (volume x gap)

2. **Keyword Clustering / Grouping**
   - Group related keywords into topic clusters (e.g., "knee replacement" + "knee surgery cost" + "knee surgery recovery")
   - Suggest one target page per cluster instead of per keyword
   - Reduces content cannibalization, speeds up strategy

3. **SERP Intent Analyzer**
   - For top keywords, pull SERP data to see what's actually ranking (service pages vs blogs vs videos)
   - Helps validate whether a keyword needs a service page, blog post, or something else
   - Could use SEMRush/Ahrefs API or scrape

4. **Competitor Keyword Overlap Matrix**
   - Upload multiple competitor keyword lists
   - Show: keywords only competitor A has, keywords all competitors share, keywords nobody targets
   - Heatmap visualization of competitive coverage

### Medium-Impact (v2)

5. **On-Page Optimization Scorer**
   - For each mapped keyword + URL pair, crawl the page and score:
     - Title tag (keyword presence, length)
     - H1, H2s, meta description
     - Content length, keyword density
   - Output: actionable checklist per page

6. **Internal Linking Recommender**
   - Analyze the URL inventory for internal linking opportunities
   - For each page, suggest other client pages to link to/from
   - Based on topical relevance and keyword mapping

7. **Rank Tracking Dashboard**
   - Import rank data over time (from SEMRush CSV exports)
   - Show keyword position trends, winners/losers
   - Correlate with content changes or new pages

8. **AI Content Brief Generator**
   - Given a keyword cluster and target URL (or NEW_PAGE)
   - Generate a content brief: target word count, H2 outline, related keywords to include, competitor analysis
   - Ready for a writer to execute

### Nice-to-Have (v3)

9. **Technical SEO Audit (Lite)**
   - During site crawl, flag common issues: missing meta descriptions, duplicate titles, slow pages, broken links
   - Quick wins report

10. **Client Reporting Template**
    - Auto-generate a PDF/PPTX summary of the keyword research
    - Stats, key findings, recommendations, next steps
    - Branded with client logo

---

## Session 4: Content Brief Generator (Step 4)

### Todo

- [x] 1. Add LLM functions for content briefs
  - `cluster_keywords()` — groups related keywords into topic clusters
  - `generate_content_brief()` — generates 5-section briefs (overview, audience, direction, SEO, CTA)
  - Updated `estimate_cost()` with "briefs" task type

- [x] 2. Build `pages/content_briefs.py`
  - Hero header "Step 4 of 4", how-it-works guide, client selection
  - Auto-loads mapping results, filters to New Page + Blog Post keywords
  - Clustering → brief generation with progress bar and auto-save
  - Expandable brief cards with all 5 sections
  - Copy-to-clipboard text area per brief
  - CSV export (flattened)

- [x] 3. Register page in app.py navigation
  - Added `content_briefs` to Workflow section
  - Updated step badges: "Step X of 3" → "Step X of 4" on all pages

- [x] 4. UX copy updates
  - Keyword Mapping hero/guide rewritten to spell out outcomes and actions
  - How It Works page: new "Why this tool?" section, 4-step workflow, new glossary/FAQ entries
  - "Why can't I just do this in SEMRush?" FAQ added

### Review

- **Summary of changes:**
  - `utils/llm.py` — Added `cluster_keywords()` and `generate_content_brief()` functions, "briefs" branch in `estimate_cost()`
  - `pages/content_briefs.py` — New Step 4 page (clustering → brief generation → review → export)
  - `app.py` — Registered Content Briefs in navigation Workflow section
  - `pages/client_setup.py`, `keyword_cleaning.py`, `keyword_mapping.py` — Step badges updated to "of 4"
  - `pages/keyword_mapping.py` — Hero/guide copy rewritten for clarity and outcomes
  - `pages/how_it_works.py` — Major rewrite: "Why this tool?" section, 4-step workflow, new glossary/FAQ

- **No new dependencies added**

- **Known limitations:**
  - Content Briefs requires mapping results from Step 3 (no standalone mode yet)
  - Brief quality depends on client profile completeness
  - No brief editing/customization UI (export and edit externally)
  - Copy-to-clipboard uses text_area (manual select+copy, not one-click)

---

## Session 5: Negative Keywords Enhancement

### Todo

- [x] 1. **Feature 1: Hard Pre-Filter** — `utils/llm.py`
  - Add `pre_filter_negatives()` function before `classify_keywords()`
  - Case-insensitive substring matching against negative keywords list
  - Returns (pass_through, auto_removed) tuple
  - Auto-removed get classification=REMOVE, confidence=100, reason="Matched negative keyword: {term}"

- [x] 2. **Feature 1: Pre-Filter Integration** — `pages/keyword_cleaning.py`
  - Extract negative_terms from profile before batching
  - Call `pre_filter_negatives()` on full keyword list
  - Show info message: "X keywords auto-removed by negative keyword filter"
  - Only send pass_through keywords to LLM batch loop
  - Merge auto_removed results back into all_results after batches

- [x] 3. **Feature 3: Category-Based Negatives UI** — `pages/client_setup.py`
  - Add "Negative Categories" text area below existing negative keywords
  - Caption explaining these are broader AI-interpreted rules
  - Add `negative_categories` to profile save dict

- [x] 4. **Feature 3: Category Prompt Injection** — `utils/llm.py`
  - Modify `classify_keywords()` prompt to include negative_categories if present
  - Add conditional block after existing rules section

- [x] 5. **Feature 2: Suggest Function** — `utils/llm.py`
  - Add `suggest_negative_keywords()` function
  - Sends sample keywords + profile to LLM
  - Returns list of suggested terms with reason + match count

- [x] 6. **Feature 2: Suggester UI** — `pages/keyword_cleaning.py`
  - Add expander between cost estimate and "Clean Keywords" button
  - "Analyze keywords for negative terms" button
  - Display suggestions as checkboxes with term + reason + match count
  - "Add Selected to Profile" button that saves to profile and updates session state

### Review

- **Summary of changes:**
  - `utils/llm.py` — Added `pre_filter_negatives()` (deterministic substring filter), `suggest_negative_keywords()` (LLM-powered suggestion), and injected `negative_categories` into `classify_keywords()` prompt
  - `pages/keyword_cleaning.py` — Pre-filter runs before LLM batching, suggester expander with checkboxes + "Add to Profile" button, info message for filtered count
  - `pages/client_setup.py` — Added "Negative Categories" text area and saves to profile

- **No new dependencies added**

- **No new environment variables needed**

- **Backward compatibility:** Old profiles without `negative_categories` work fine via `profile.get("negative_categories", [])`
