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
from utils.llm import classify_keywords, cost_tracker, estimate_cost

st.header("Keyword Cleaning")

# ── Client selection ─────────────────────────────────────────────

clients = list_clients()
if not clients:
    st.warning("No client profiles found. Go to **Client Setup** first.")
    st.stop()

selected_client = st.selectbox("Select Client", clients)
profile = load_client_profile(selected_client)
if not profile:
    st.error("Could not load client profile.")
    st.stop()

st.success(f"Client: **{profile.get('business_name', selected_client)}**")

# ── CSV upload ───────────────────────────────────────────────────

st.subheader("Upload Keyword Gap CSV")
uploaded = st.file_uploader("Choose CSV file", type=["csv"], key="cleaning_csv")

if uploaded is None:
    # Check for saved partial results
    saved = load_latest_results(selected_client, "cleaning")
    if saved:
        st.info("Found saved results from a previous session.")
        if st.button("Load Previous Results"):
            st.session_state.cleaning_results = saved.get("results", [])
            st.session_state.cleaning_df = pd.DataFrame(saved.get("original_data", []))
            st.rerun()
    st.stop()

# Parse CSV
try:
    df = parse_keyword_csv(uploaded)
except Exception as e:
    st.error(f"Failed to parse CSV: {e}")
    st.stop()

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

# ── Cost estimate ────────────────────────────────────────────────

est = estimate_cost(len(df), "cleaning")
model_short = est["model"].split("/")[-1]
st.info(
    f"**Estimate** ({model_short}): {est['batches']} batches, ~{est['est_minutes']} min, "
    f"~${est['est_cost_usd']:.2f} LLM cost"
)

# ── Batch processing ─────────────────────────────────────────────

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

            # Build keyword dicts from dataframe
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

                # Merge classification back with original row data
                for i, result in enumerate(batch_results):
                    row_idx = start + i
                    if row_idx < len(df):
                        row_data = df.iloc[row_idx].to_dict()
                        row_data["classification"] = result.get("classification", "UNSURE")
                        row_data["reason"] = result.get("reason", "")
                        all_results.append(row_data)

                # Update anchor examples (pick one from each category if available)
                for cat in ["KEEP", "REMOVE", "UNSURE"]:
                    examples_of_cat = [r for r in batch_results if r.get("classification") == cat]
                    if examples_of_cat and len(anchor_examples) < 3:
                        anchor_examples.append(examples_of_cat[0])

            except Exception as e:
                st.error(f"Batch {batch_idx + 1} failed: {e}")
                # Save partial results
                for i in range(len(batch_df)):
                    row_idx = start + i
                    if row_idx < len(df):
                        row_data = df.iloc[row_idx].to_dict()
                        row_data["classification"] = "UNSURE"
                        row_data["reason"] = f"Batch failed: {e}"
                        all_results.append(row_data)

            progress_bar.progress((batch_idx + 1) / total_batches)

            # Auto-save after each batch
            save_results(
                selected_client,
                "cleaning",
                {"results": all_results, "original_data": df.to_dict(orient="records")},
            )

            # Brief pause between batches
            if batch_idx < total_batches - 1:
                time.sleep(1)

        status.update(label=f"Done! Classified {len(all_results)} keywords.", state="complete")

    st.session_state.cleaning_results = all_results
    cost_tracker.save_log(selected_client)

# ── Results view ─────────────────────────────────────────────────

results = st.session_state.get("cleaning_results", [])
if not results:
    st.stop()

results_df = pd.DataFrame(results)
st.divider()
st.subheader("Results")

# Summary metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total", len(results_df))
col2.metric("Keep", len(results_df[results_df["classification"] == "KEEP"]))
col3.metric("Remove", len(results_df[results_df["classification"] == "REMOVE"]))
col4.metric("Unsure", len(results_df[results_df["classification"] == "UNSURE"]))

# Tabs for each category
tab_keep, tab_remove, tab_unsure, tab_all = st.tabs(["Keep", "Remove", "Unsure", "All"])

# Determine display columns — keyword + classification + reason + any original columns
display_cols = [keyword_col, "classification", "reason"]
for c in ["volume", "keyword difficulty", "kd", "intent"]:
    if c in results_df.columns and c not in display_cols:
        display_cols.append(c)

# Classification editor dropdown
classification_options = ["KEEP", "REMOVE", "UNSURE"]

with tab_keep:
    keep_df = results_df[results_df["classification"] == "KEEP"][display_cols].copy()
    if len(keep_df) > 0:
        edited_keep = st.data_editor(
            keep_df,
            column_config={
                "classification": st.column_config.SelectboxColumn(
                    "Classification", options=classification_options
                )
            },
            use_container_width=True,
            key="keep_editor",
        )
    else:
        st.info("No keywords classified as KEEP.")

with tab_remove:
    remove_df = results_df[results_df["classification"] == "REMOVE"][display_cols].copy()
    if len(remove_df) > 0:
        edited_remove = st.data_editor(
            remove_df,
            column_config={
                "classification": st.column_config.SelectboxColumn(
                    "Classification", options=classification_options
                )
            },
            use_container_width=True,
            key="remove_editor",
        )
    else:
        st.info("No keywords classified as REMOVE.")

with tab_unsure:
    unsure_df = results_df[results_df["classification"] == "UNSURE"][display_cols].copy()
    if len(unsure_df) > 0:
        edited_unsure = st.data_editor(
            unsure_df,
            column_config={
                "classification": st.column_config.SelectboxColumn(
                    "Classification", options=classification_options
                )
            },
            use_container_width=True,
            key="unsure_editor",
        )
    else:
        st.info("No keywords classified as UNSURE.")

with tab_all:
    st.dataframe(results_df[display_cols], use_container_width=True)

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
