import time

import pandas as pd
import streamlit as st

from utils.data import (
    export_csv,
    list_clients,
    load_client_profile,
    load_latest_results,
    parse_keyword_csv,
    save_results,
)
from utils.llm import classify_keywords, cost_tracker, estimate_cost, generate_qc_summary
from utils.semrush import pull_competitor_keywords, check_api_units, estimate_api_cost

st.markdown("""
<div class="page-hero">
    <span class="step-badge">Step 2 of 4</span>
    <h1>Keyword Cleaning</h1>
    <p>Pull keywords from SEMRush or upload a CSV, and the AI will sort each keyword into <strong>Keep</strong>, <strong>Remove</strong>, or <strong>Unsure</strong> based on your client profile.</p>
</div>
""", unsafe_allow_html=True)

# ── How it works guide ───────────────────────────────────────────

with st.expander("How does this work?", expanded=False):
    st.markdown("""
    <div class="guide-step">
        <span class="step-num">1</span>
        <span class="step-title">Select your client</span>
        <div class="step-desc">Choose the client profile you set up in Step 1. The AI uses their services, locations, and specialties to judge relevance.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">2</span>
        <span class="step-title">Add your keywords</span>
        <div class="step-desc">Pull keywords directly from SEMRush using the API tab, upload a CSV from any tool, or paste keywords manually. The SEMRush pull automatically includes volume, difficulty, and intent data.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">3</span>
        <span class="step-title">AI classifies each keyword</span>
        <div class="step-desc">Each keyword gets classified as <strong>Keep</strong> (relevant), <strong>Remove</strong> (irrelevant), or <strong>Unsure</strong> (needs your judgment) — plus a confidence score from 0-100.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">4</span>
        <span class="step-title">Review & export</span>
        <div class="step-desc">Check the QC summary, review flagged keywords, override any classifications you disagree with, then export the cleaned list as CSV.</div>
    </div>
    """, unsafe_allow_html=True)

# ── Client selection ─────────────────────────────────────────────

clients = list_clients()
if not clients:
    st.markdown("""
    <div class="info-callout">
        No client profiles found yet. Head to <strong>Client Setup</strong> to create one — you'll need a client profile before cleaning keywords.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

selected_client = st.selectbox("Select Client", clients)
profile = load_client_profile(selected_client)
if not profile:
    st.error("Could not load client profile.")
    st.stop()

st.success(f"Client: **{profile.get('business_name', selected_client)}**")

# ── Auto-load saved results if they exist ────────────────────────

if "cleaning_results" not in st.session_state or not st.session_state.cleaning_results:
    saved = load_latest_results(selected_client, "cleaning")
    if saved and saved.get("results"):
        st.session_state.cleaning_results = saved["results"]
        if saved.get("qc_summary"):
            st.session_state.cleaning_qc = saved["qc_summary"]

# ── Keyword input ────────────────────────────────────────────────

st.subheader("Add Keywords")
input_tab_semrush, input_tab_csv, input_tab_paste = st.tabs(["Pull from SEMRush", "Upload CSV", "Paste Keywords"])

df = None

with input_tab_semrush:
    st.caption("Pull competitor keywords directly from SEMRush — no CSV export needed.")

    col_sr1, col_sr2 = st.columns(2)
    with col_sr1:
        competitor_domain = st.text_input(
            "Competitor Domain",
            placeholder="competitor.com",
            key="semrush_competitor",
            help="Enter a competitor's domain to pull their organic keywords. These are keywords they rank for that you might want to target.",
        )
    with col_sr2:
        sr_database = st.selectbox(
            "Database",
            ["us", "uk", "ca", "au", "de", "fr", "es", "it", "br", "in"],
            key="semrush_db",
            help="Regional Google database to pull keywords from.",
        )

    sr_limit = st.slider(
        "Max Keywords",
        min_value=50,
        max_value=2000,
        value=500,
        step=50,
        key="semrush_limit",
        help="Number of keywords to pull. Each keyword costs 10 SEMRush API units.",
    )

    # Show cost estimate
    sr_est = estimate_api_cost(sr_limit)
    st.markdown(f"""
    <div class="info-callout">
        <strong>API Cost:</strong> {sr_est['description']}
    </div>
    """, unsafe_allow_html=True)

    if competitor_domain and st.button("Pull Keywords from SEMRush", type="primary", key="pull_semrush"):
        with st.status("Pulling keywords from SEMRush...", expanded=True) as status:
            try:
                # Check API units first (may return -1 if check unavailable)
                units_info = check_api_units()
                if units_info["units_remaining"] >= 0:
                    st.write(f"API units remaining: {units_info['units_remaining']:,}")
                    if units_info["units_remaining"] < sr_est["api_units"]:
                        st.error(f"Not enough API units. Need {sr_est['api_units']:,}, have {units_info['units_remaining']:,}.")
                        st.stop()

                sr_df = pull_competitor_keywords(
                    competitor_domain=competitor_domain,
                    database=sr_database,
                    limit=sr_limit,
                )
                st.session_state._cleaning_semrush_df = sr_df
                status.update(label=f"Done! Pulled {len(sr_df)} keywords from {competitor_domain}.", state="complete")
            except Exception as e:
                st.error(f"SEMRush API error: {e}")
                status.update(label="Failed to pull keywords.", state="error")

    # Persist SEMRush results across reruns
    if "_cleaning_semrush_df" in st.session_state:
        df = st.session_state._cleaning_semrush_df

with input_tab_csv:
    st.caption("Upload a keyword gap CSV from any SEO tool. Needs a 'keyword' column — volume, KD, and intent are optional.")
    uploaded = st.file_uploader("Choose CSV file", type=["csv"], key="cleaning_csv")
    if uploaded is not None:
        try:
            df = parse_keyword_csv(uploaded)
        except Exception as e:
            st.error(f"Failed to parse CSV: {e}")

with input_tab_paste:
    st.caption("No CSV? Just paste your keywords below, one per line.")
    pasted = st.text_area(
        "Paste keywords (one per line)",
        height=200,
        key="cleaning_paste",
        placeholder="spine surgery near me\nbest orthopedic surgeon\nmedical marketing agency",
    )
    if pasted.strip() and st.button("Use These Keywords", key="use_pasted"):
        lines = [line.strip() for line in pasted.strip().split("\n") if line.strip()]
        df = pd.DataFrame({"keyword": lines})
        st.session_state._cleaning_pasted_df = df

    if "_cleaning_pasted_df" in st.session_state:
        df = st.session_state._cleaning_pasted_df

if df is not None and len(df) > 0:

    # Find the keyword column
    keyword_col = None
    for col_name in ["keyword", "keywords", "query", "search query", "term"]:
        if col_name in df.columns:
            keyword_col = col_name
            break

    if keyword_col is None:
        st.error(f"Could not find a keyword column. Found columns: {', '.join(df.columns)}")
        st.stop()

    st.write(f"**{len(df)} keywords** loaded. Columns: {', '.join(df.columns)}")
    st.dataframe(df.head(10), use_container_width=True)

    # Cost estimate
    est = estimate_cost(len(df), "cleaning")
    model_short = est["model"].split("/")[-1]
    st.markdown(f"""
    <div class="info-callout">
        <strong>Estimate</strong> ({model_short}): {est['batches']} batch{'es' if est['batches'] > 1 else ''}, ~{est['est_minutes']} min, ~${est['est_cost_usd']:.2f} LLM cost
    </div>
    """, unsafe_allow_html=True)

    # ── Batch processing ─────────────────────────────────────────

    BATCH_SIZE = 100

    if st.button("Clean Keywords", type="primary"):
        all_results = []
        anchor_examples = []

        progress_bar = st.progress(0)

        with st.status("Classifying keywords...", expanded=True) as status:
            total_batches = max(1, (len(df) + BATCH_SIZE - 1) // BATCH_SIZE)

            for batch_idx in range(total_batches):
                start = batch_idx * BATCH_SIZE
                end = min(start + BATCH_SIZE, len(df))
                batch_df = df.iloc[start:end]

                st.write(f"Batch {batch_idx + 1}/{total_batches} ({start+1}–{end})...")

                keywords = []
                for _, row in batch_df.iterrows():
                    kw = {"keyword": row[keyword_col]}
                    if "volume" in df.columns:
                        kw["volume"] = row.get("volume", "")
                    if "keyword difficulty" in df.columns:
                        kw["kd"] = row.get("keyword difficulty", "")
                    elif "kd" in df.columns:
                        kw["kd"] = row.get("kd", "")
                    if "intent" in df.columns:
                        kw["intent"] = row.get("intent", "")
                    keywords.append(kw)

                try:
                    batch_results = classify_keywords(
                        profile, keywords, examples=anchor_examples if anchor_examples else None
                    )

                    for i, result in enumerate(batch_results):
                        row_idx = start + i
                        if row_idx < len(df):
                            row_data = df.iloc[row_idx].to_dict()
                            row_data["classification"] = result.get("classification", "UNSURE")
                            row_data["confidence"] = result.get("confidence", 50)
                            row_data["reason"] = result.get("reason", "")
                            all_results.append(row_data)

                    for cat in ["KEEP", "REMOVE", "UNSURE"]:
                        examples_of_cat = [r for r in batch_results if r.get("classification") == cat]
                        if examples_of_cat and len(anchor_examples) < 3:
                            anchor_examples.append(examples_of_cat[0])

                except Exception as e:
                    st.error(f"Batch {batch_idx + 1} failed: {e}")
                    for i in range(len(batch_df)):
                        row_idx = start + i
                        if row_idx < len(df):
                            row_data = df.iloc[row_idx].to_dict()
                            row_data["classification"] = "UNSURE"
                            row_data["confidence"] = 0
                            row_data["reason"] = f"Batch failed: {e}"
                            all_results.append(row_data)

                progress_bar.progress((batch_idx + 1) / total_batches)

                save_results(
                    selected_client,
                    "cleaning",
                    {"results": all_results, "original_data": df.to_dict(orient="records")},
                )

                if batch_idx < total_batches - 1:
                    time.sleep(1)

            status.update(label=f"Done! Classified {len(all_results)} keywords.", state="complete")

        # ── Generate QC summary ──────────────────────────────────
        with st.status("Running quality check...", expanded=True):
            try:
                qc = generate_qc_summary(profile, all_results)
                st.session_state.cleaning_qc = qc
                # Re-save with QC
                save_results(
                    selected_client,
                    "cleaning",
                    {
                        "results": all_results,
                        "original_data": df.to_dict(orient="records"),
                        "qc_summary": qc,
                    },
                )
            except Exception as e:
                st.warning(f"QC summary generation failed: {e}")

        st.session_state.cleaning_results = all_results
        cost_tracker.save_log(selected_client)

# ── Results view ─────────────────────────────────────────────────

results = st.session_state.get("cleaning_results", [])
if not results:
    st.stop()

results_df = pd.DataFrame(results)

# Ensure confidence column exists
if "confidence" not in results_df.columns:
    results_df["confidence"] = 50

st.divider()

# ── QC Summary Card ──────────────────────────────────────────────

qc = st.session_state.get("cleaning_qc")
if qc:
    quality = qc.get("overall_quality", "fair")
    qc_class = f"qc-{quality.replace('_', '-')}"
    score = qc.get("score", "—")
    score_color = "#38A169" if score >= 80 else "#D69E2E" if score >= 60 else "#E53E3E"

    flagged_html = ""
    for flag in qc.get("flagged_keywords", [])[:3]:
        flagged_html += f"""<div class="qc-flag">
            <strong>{flag.get('keyword', '')}</strong>: Currently {flag.get('current', '?')} →
            Suggested {flag.get('suggested', '?')} — {flag.get('reason', '')}
        </div>"""

    st.markdown(f"""
    <div class="qc-card {qc_class}">
        <div class="qc-header">
            <div>
                <div class="qc-label">Quality Score</div>
                <div class="qc-score" style="color: {score_color}">{score}/100</div>
            </div>
            <div style="flex:1">
                <div class="qc-title">QC Assessment</div>
                <div class="qc-body">{qc.get('summary', '')}</div>
            </div>
        </div>
        {flagged_html}
        <div class="qc-tip">💡 {qc.get('tip', '')}</div>
    </div>
    """, unsafe_allow_html=True)

# ── Metrics row ──────────────────────────────────────────────────

st.subheader("Results")

keep_count = len(results_df[results_df["classification"] == "KEEP"])
remove_count = len(results_df[results_df["classification"] == "REMOVE"])
unsure_count = len(results_df[results_df["classification"] == "UNSURE"])
avg_conf = results_df["confidence"].mean()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total", len(results_df))
col2.metric("Keep", keep_count)
col3.metric("Remove", remove_count)
col4.metric("Unsure", unsure_count)
col5.metric("Avg Confidence", f"{avg_conf:.0f}%")

# ── Find keyword column in results ───────────────────────────────

keyword_col_result = "keyword"
for col_name in ["keyword", "keywords", "query", "search query", "term"]:
    if col_name in results_df.columns:
        keyword_col_result = col_name
        break

# ── Display columns ──────────────────────────────────────────────

display_cols = [keyword_col_result, "classification", "confidence", "reason"]
for c in ["volume", "keyword difficulty", "kd", "intent"]:
    if c in results_df.columns and c not in display_cols:
        display_cols.append(c)

classification_options = ["KEEP", "REMOVE", "UNSURE"]

# ── Tabs ─────────────────────────────────────────────────────────

tab_keep, tab_remove, tab_unsure, tab_flagged, tab_all = st.tabs(
    ["Keep", "Remove", "Unsure", "Flagged for Review", "All"]
)

with tab_keep:
    keep_df = results_df[results_df["classification"] == "KEEP"][display_cols].copy()
    if len(keep_df) > 0:
        st.caption(f"{len(keep_df)} keywords to keep — these are directly relevant to the client.")
        st.data_editor(
            keep_df.sort_values("confidence", ascending=True),
            column_config={
                "classification": st.column_config.SelectboxColumn("Classification", options=classification_options),
                "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d%%"),
            },
            use_container_width=True,
            key="keep_editor",
        )
    else:
        st.info("No keywords classified as KEEP.")

with tab_remove:
    remove_df = results_df[results_df["classification"] == "REMOVE"][display_cols].copy()
    if len(remove_df) > 0:
        st.caption(f"{len(remove_df)} keywords to remove — wrong location, wrong specialty, or irrelevant.")
        st.data_editor(
            remove_df.sort_values("confidence", ascending=True),
            column_config={
                "classification": st.column_config.SelectboxColumn("Classification", options=classification_options),
                "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d%%"),
            },
            use_container_width=True,
            key="remove_editor",
        )
    else:
        st.info("No keywords classified as REMOVE.")

with tab_unsure:
    unsure_df = results_df[results_df["classification"] == "UNSURE"][display_cols].copy()
    if len(unsure_df) > 0:
        st.caption(f"{len(unsure_df)} keywords need your judgment — the AI wasn't confident enough to decide.")
        st.data_editor(
            unsure_df.sort_values("confidence", ascending=True),
            column_config={
                "classification": st.column_config.SelectboxColumn("Classification", options=classification_options),
                "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d%%"),
            },
            use_container_width=True,
            key="unsure_editor",
        )
    else:
        st.info("No keywords classified as UNSURE.")

with tab_flagged:
    flagged_df = results_df[results_df["confidence"] < 70][display_cols].copy()
    if len(flagged_df) > 0:
        st.caption(f"{len(flagged_df)} keywords with confidence below 70% — review these first.")
        st.data_editor(
            flagged_df.sort_values("confidence", ascending=True),
            column_config={
                "classification": st.column_config.SelectboxColumn("Classification", options=classification_options),
                "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d%%"),
            },
            use_container_width=True,
            key="flagged_editor",
        )
    else:
        st.success("All keywords have confidence 70% or higher — no flags!")

with tab_all:
    st.caption(f"All {len(results_df)} keywords. Click column headers to sort.")
    st.dataframe(
        results_df[display_cols].sort_values("confidence", ascending=True),
        column_config={
            "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=100, format="%d%%"),
        },
        use_container_width=True,
    )

# ── Export ────────────────────────────────────────────────────────

st.divider()
st.subheader("Export")

col_export1, col_export2 = st.columns(2)
with col_export1:
    st.download_button(
        "Download All Results (CSV)",
        data=export_csv(results_df),
        file_name=f"{selected_client}_cleaned_all.csv",
        mime="text/csv",
    )
with col_export2:
    keep_only = results_df[results_df["classification"] == "KEEP"]
    st.download_button(
        "Download KEEP Only (CSV)",
        data=export_csv(keep_only),
        file_name=f"{selected_client}_cleaned_keep.csv",
        mime="text/csv",
    )

st.markdown("""
<div class="info-callout">
    <strong>Next step:</strong> Take the KEEP keywords to <strong>Keyword Mapping</strong> (Step 3) to map them to existing client URLs or flag new pages needed.
</div>
""", unsafe_allow_html=True)

if st.button("Clear Results & Start Over"):
    st.session_state.cleaning_results = []
    st.session_state.cleaning_qc = None
    if "_cleaning_pasted_df" in st.session_state:
        del st.session_state._cleaning_pasted_df
    st.rerun()
