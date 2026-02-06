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

st.markdown("""
<div class="page-hero">
    <span class="step-badge">Step 3 of 4</span>
    <h1>Keyword Mapping</h1>
    <p>Assign every keyword to a specific page on the client's website. The output is a <strong>clear action plan</strong>: which existing pages to optimize, which new pages to create, and which blog posts to write.</p>
</div>
""", unsafe_allow_html=True)

# ── How it works guide ───────────────────────────────────────────

with st.expander("How does this work?", expanded=False):
    st.markdown("""
    <div class="guide-step">
        <span class="step-num">1</span>
        <span class="step-title">Select your client</span>
        <div class="step-desc">Choose the client profile from Step 1. The AI uses the URL inventory (from the site crawl) to find the best page match for each keyword.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">2</span>
        <span class="step-title">Add your cleaned keywords</span>
        <div class="step-desc">Upload the CSV you exported from Keyword Cleaning (Step 2), or paste keywords manually. Ideally these are the <strong>KEEP</strong> keywords from your cleaned list — whether they were pulled from SEMRush or uploaded as CSV.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">3</span>
        <span class="step-title">AI assigns each keyword to a page</span>
        <div class="step-desc">For each keyword, the AI decides: Does the client already have a page that should rank for this? If yes, it assigns the keyword to that URL. If not, it flags the keyword as a <strong>New Page</strong> (the client needs to create a service/landing page) or <strong>Blog Post</strong> (an informational article opportunity).</div>
    </div>
    <div class="guide-step">
        <span class="step-num">4</span>
        <span class="step-title">Get your action plan</span>
        <div class="step-desc">The output is a spreadsheet your team can act on immediately:
            <br>• <strong>Existing URL</strong> keywords → optimize those pages (update titles, headings, content to target these terms)
            <br>• <strong>New Page</strong> keywords → create dedicated service/landing pages for these high-intent searches
            <br>• <strong>Blog Post</strong> keywords → write content that answers these questions and drives organic traffic
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Client selection ─────────────────────────────────────────────

clients = list_clients()
if not clients:
    st.markdown("""
    <div class="info-callout">
        No client profiles found yet. Head to <strong>Client Setup</strong> to create one — you'll need a client profile with a URL inventory before mapping keywords.
    </div>
    """, unsafe_allow_html=True)
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
    st.markdown("""
    <div class="info-callout">
        No URL inventory found for this client. Go to <strong>Client Setup</strong> and crawl the site first — the AI needs the client's pages to map keywords against.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

st.caption(f"{len(url_inventory)} URLs available from client profile.")

# ── Auto-load saved results if they exist ────────────────────────

if "mapping_results" not in st.session_state or not st.session_state.mapping_results:
    saved = load_latest_results(selected_client, "mapping")
    if saved and saved.get("results"):
        st.session_state.mapping_results = saved["results"]

# ── Keyword input ────────────────────────────────────────────────

st.subheader("Add Keywords")
input_tab_csv, input_tab_paste = st.tabs(["Upload CSV", "Paste Keywords"])

df = None

with input_tab_csv:
    st.caption("Upload the cleaned keywords from Keyword Cleaning, or any CSV with a keyword column.")
    uploaded = st.file_uploader("Choose CSV file", type=["csv"], key="mapping_csv")

    # Optional second CSV
    with st.expander("Optional: Upload additional raw research keywords"):
        uploaded_extra = st.file_uploader(
            "Additional keywords CSV", type=["csv"], key="mapping_extra_csv"
        )

    if uploaded is not None:
        try:
            df = parse_keyword_csv(uploaded)
            if uploaded_extra:
                df_extra = parse_keyword_csv(uploaded_extra)
                df = pd.concat([df, df_extra], ignore_index=True)
        except Exception as e:
            st.error(f"Failed to parse CSV: {e}")

with input_tab_paste:
    st.caption("No CSV? Just paste your keywords below, one per line.")
    pasted = st.text_area(
        "Paste keywords (one per line)",
        height=200,
        key="mapping_paste",
        placeholder="spine surgery near me\nbest orthopedic surgeon\nmedical marketing agency",
    )
    if pasted.strip() and st.button("Use These Keywords", key="use_pasted_mapping"):
        lines = [line.strip() for line in pasted.strip().split("\n") if line.strip()]
        df = pd.DataFrame({"keyword": lines})
        st.session_state._mapping_pasted_df = df

    # Persist pasted keywords across reruns
    if "_mapping_pasted_df" in st.session_state:
        df = st.session_state._mapping_pasted_df

if df is not None and len(df) > 0:
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

    # Cost estimate
    est = estimate_cost(len(df), "mapping")
    model_short = est["model"].split("/")[-1]
    st.markdown(f"""
    <div class="info-callout">
        <strong>Estimate</strong> ({model_short}): {est['batches']} batch{'es' if est['batches'] > 1 else ''}, ~{est['est_minutes']} min, ~${est['est_cost_usd']:.2f} LLM cost
    </div>
    """, unsafe_allow_html=True)

    # ── Batch processing ─────────────────────────────────────────

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

# Ensure confidence column exists
if "confidence" not in results_df.columns:
    results_df["confidence"] = 50

st.divider()
st.subheader("Results")

# Summary metrics
existing_count = len(results_df[results_df["recommendation"] == "Existing URL"])
new_page_count = len(results_df[results_df["recommendation"] == "New Page"])
blog_count = len(results_df[results_df["recommendation"] == "Blog Post"])
avg_conf = results_df["confidence"].mean()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total", len(results_df))
col2.metric("Existing URL", existing_count)
col3.metric("New Page", new_page_count)
col4.metric("Blog Post", blog_count)
col5.metric("Avg Confidence", f"{avg_conf:.0f}%")

# Find keyword column in results
keyword_col_result = "keyword"
for col_name in ["keyword", "keywords", "query", "search query", "term"]:
    if col_name in results_df.columns:
        keyword_col_result = col_name
        break

# Display columns
display_cols = [keyword_col_result, "mapped_url", "confidence", "search_intent", "recommendation", "notes"]
for c in ["volume", "intent"]:
    if c in results_df.columns and c not in display_cols:
        display_cols.append(c)
# Only keep columns that actually exist
display_cols = [c for c in display_cols if c in results_df.columns]

# Column config with confidence bar
column_config = {
    "confidence": st.column_config.ProgressColumn(
        "Confidence", min_value=0, max_value=100, format="%d%%"
    ),
}

# Filter tabs
tab_existing, tab_new, tab_blog, tab_all = st.tabs(
    ["Existing URL", "New Page", "Blog Post", "All"]
)

with tab_existing:
    filtered = results_df[results_df["recommendation"] == "Existing URL"][display_cols]
    if len(filtered) > 0:
        st.caption(f"{len(filtered)} keywords matched to existing pages — optimize these pages by updating their titles, headings, and content to target these terms.")
        st.data_editor(
            filtered.sort_values("confidence", ascending=True),
            column_config=column_config,
            use_container_width=True,
            key="map_existing",
        )
    else:
        st.info("No keywords mapped to existing URLs.")

with tab_new:
    filtered = results_df[results_df["recommendation"] == "New Page"][display_cols]
    if len(filtered) > 0:
        st.caption(f"{len(filtered)} keywords need a new service or landing page — people are searching for these but the client has no page targeting them. Each is a content gap and a growth opportunity.")
        st.data_editor(
            filtered.sort_values("confidence", ascending=True),
            column_config=column_config,
            use_container_width=True,
            key="map_new",
        )
    else:
        st.info("No keywords recommended for new pages.")

with tab_blog:
    filtered = results_df[results_df["recommendation"] == "Blog Post"][display_cols]
    if len(filtered) > 0:
        st.caption(f"{len(filtered)} keywords are informational — people are asking questions the client can answer. Each is a blog post or resource page that drives organic traffic and builds authority.")
        st.data_editor(
            filtered.sort_values("confidence", ascending=True),
            column_config=column_config,
            use_container_width=True,
            key="map_blog",
        )
    else:
        st.info("No keywords recommended for blog posts.")

with tab_all:
    st.caption(f"All {len(results_df)} keywords. Click column headers to sort.")
    st.dataframe(
        results_df[display_cols].sort_values("confidence", ascending=True),
        column_config=column_config,
        use_container_width=True,
    )

# ── Export ────────────────────────────────────────────────────────

st.divider()
st.subheader("Export")

col_export1, col_export2 = st.columns(2)
with col_export1:
    st.download_button(
        "Download All Mappings (CSV)",
        data=export_csv(results_df),
        file_name=f"{selected_client}_keyword_mapping.csv",
        mime="text/csv",
    )
with col_export2:
    new_content = results_df[results_df["recommendation"].isin(["New Page", "Blog Post"])]
    st.download_button(
        "Download New Content Only (CSV)",
        data=export_csv(new_content),
        file_name=f"{selected_client}_new_content_opportunities.csv",
        mime="text/csv",
    )

st.markdown("""
<div class="info-callout">
    <strong>What's next?</strong> Hand the <strong>Existing URL</strong> list to your SEO team for on-page optimization. Use the <strong>New Page</strong> and <strong>Blog Post</strong> lists to plan your content calendar — or generate AI content briefs for each one in Step 4.
</div>
""", unsafe_allow_html=True)

# Clear results button
if st.button("Clear Results & Start Over"):
    st.session_state.mapping_results = []
    if "_mapping_pasted_df" in st.session_state:
        del st.session_state._mapping_pasted_df
    st.rerun()
