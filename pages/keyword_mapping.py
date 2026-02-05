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
from utils.llm import cost_tracker, estimate_cost, map_keywords

st.header("Keyword Mapping")

# ── Client selection ─────────────────────────────────────────────

clients = list_clients()
if not clients:
    st.warning("No client profiles found. Go to **Client Setup** first.")
    st.stop()

selected_client = st.selectbox("Select Client", clients, key="mapping_client")
profile = load_client_profile(selected_client)
if not profile:
    st.error("Could not load client profile.")
    st.stop()

st.success(f"Client: **{profile.get('business_name', selected_client)}**")

# Check URL inventory
url_inventory = profile.get("url_inventory", [])
if not url_inventory:
    st.warning(
        "No URL inventory found for this client. "
        "Go to **Client Setup** and crawl the site first."
    )
    st.stop()

st.info(f"**{len(url_inventory)} URLs** available from client profile.")

# ── CSV upload ───────────────────────────────────────────────────

st.subheader("Upload Keywords CSV")
st.caption("Upload the cleaned keywords from Keyword Cleaning, or any CSV with a keyword column.")

uploaded = st.file_uploader("Choose CSV file", type=["csv"], key="mapping_csv")

# Optional second CSV
with st.expander("Optional: Upload additional raw research keywords"):
    uploaded_extra = st.file_uploader(
        "Additional keywords CSV", type=["csv"], key="mapping_extra_csv"
    )

if uploaded is None:
    # Check for saved results
    saved = load_latest_results(selected_client, "mapping")
    if saved:
        st.info("Found saved results from a previous session.")
        if st.button("Load Previous Results"):
            st.session_state.mapping_results = saved.get("results", [])
            st.rerun()
    st.stop()

# Parse CSV(s)
try:
    df = parse_keyword_csv(uploaded)
    if uploaded_extra:
        df_extra = parse_keyword_csv(uploaded_extra)
        df = pd.concat([df, df_extra], ignore_index=True)
except Exception as e:
    st.error(f"Failed to parse CSV: {e}")
    st.stop()

# Find keyword column
keyword_col = None
for col_name in ["keyword", "keywords", "query", "search query", "term"]:
    if col_name in df.columns:
        keyword_col = col_name
        break

if keyword_col is None:
    st.error(f"Could not find a keyword column. Found columns: {', '.join(df.columns)}")
    st.stop()

st.write(f"**{len(df)} keywords** loaded.")
st.dataframe(df.head(10), use_container_width=True)

# ── Cost estimate ────────────────────────────────────────────────

est = estimate_cost(len(df), "mapping")
model_short = est["model"].split("/")[-1]
st.info(
    f"**Estimate** ({model_short}): {est['batches']} batches, ~{est['est_minutes']} min, "
    f"~${est['est_cost_usd']:.2f} LLM cost"
)

# ── Batch processing ─────────────────────────────────────────────

BATCH_SIZE = 100

if st.button("Map Keywords", type="primary"):
    all_results = []

    progress_bar = st.progress(0)

    with st.status("Mapping keywords to URLs...", expanded=True) as status:
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
                if "intent" in df.columns:
                    kw["intent"] = row.get("intent", "")
                keywords.append(kw)

            try:
                batch_results = map_keywords(profile, keywords, url_inventory)

                # Merge with original row data
                for i, result in enumerate(batch_results):
                    row_idx = start + i
                    if row_idx < len(df):
                        row_data = df.iloc[row_idx].to_dict()
                        row_data["mapped_url"] = result.get("url", "")
                        row_data["confidence"] = result.get("confidence", 0)
                        row_data["search_intent"] = result.get("intent", "")
                        row_data["recommendation"] = (
                            "New Page" if result.get("url") == "NEW_PAGE"
                            else "Blog Post" if result.get("url") == "BLOG_POST"
                            else "Existing URL"
                        )
                        row_data["notes"] = result.get("notes", "")
                        all_results.append(row_data)

            except Exception as e:
                st.error(f"Batch {batch_idx + 1} failed: {e}")
                for i in range(len(batch_df)):
                    row_idx = start + i
                    if row_idx < len(df):
                        row_data = df.iloc[row_idx].to_dict()
                        row_data["mapped_url"] = ""
                        row_data["confidence"] = 0
                        row_data["search_intent"] = ""
                        row_data["recommendation"] = "Error"
                        row_data["notes"] = f"Batch failed: {e}"
                        all_results.append(row_data)

            progress_bar.progress((batch_idx + 1) / total_batches)

            # Auto-save after each batch
            save_results(selected_client, "mapping", {"results": all_results})

            if batch_idx < total_batches - 1:
                time.sleep(1)

        status.update(label=f"Done! Mapped {len(all_results)} keywords.", state="complete")

    st.session_state.mapping_results = all_results
    cost_tracker.save_log(selected_client)

# ── Results view ─────────────────────────────────────────────────

results = st.session_state.get("mapping_results", [])
if not results:
    st.stop()

results_df = pd.DataFrame(results)
st.divider()
st.subheader("Results")

# Summary metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total", len(results_df))
col2.metric("Existing URL", len(results_df[results_df["recommendation"] == "Existing URL"]))
col3.metric("New Page", len(results_df[results_df["recommendation"] == "New Page"]))
col4.metric("Blog Post", len(results_df[results_df["recommendation"] == "Blog Post"]))

# Display columns
display_cols = [keyword_col, "mapped_url", "confidence", "search_intent", "recommendation", "notes"]
for c in ["volume", "intent"]:
    if c in results_df.columns and c not in display_cols:
        display_cols.append(c)
# Only keep columns that actually exist
display_cols = [c for c in display_cols if c in results_df.columns]

# Filter tabs
tab_existing, tab_new, tab_blog, tab_all = st.tabs(
    ["Existing URL", "New Page", "Blog Post", "All"]
)

with tab_existing:
    filtered = results_df[results_df["recommendation"] == "Existing URL"][display_cols]
    if len(filtered) > 0:
        st.data_editor(filtered, use_container_width=True, key="map_existing")
    else:
        st.info("No keywords mapped to existing URLs.")

with tab_new:
    filtered = results_df[results_df["recommendation"] == "New Page"][display_cols]
    if len(filtered) > 0:
        st.data_editor(filtered, use_container_width=True, key="map_new")
    else:
        st.info("No keywords recommended for new pages.")

with tab_blog:
    filtered = results_df[results_df["recommendation"] == "Blog Post"][display_cols]
    if len(filtered) > 0:
        st.data_editor(filtered, use_container_width=True, key="map_blog")
    else:
        st.info("No keywords recommended for blog posts.")

with tab_all:
    st.dataframe(results_df[display_cols], use_container_width=True)

# ── Export ────────────────────────────────────────────────────────

st.divider()
st.subheader("Export")

st.download_button(
    "Download Mapping Results (CSV)",
    data=export_csv(results_df),
    file_name=f"{selected_client}_keyword_mapping.csv",
    mime="text/csv",
)
