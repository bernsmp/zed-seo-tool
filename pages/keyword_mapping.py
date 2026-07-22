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
from utils.incidents import report_incident
from utils.llm import cost_tracker, estimate_cost, format_llm_error, map_keywords

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

active_client = st.session_state.get("active_client")
default_index = clients.index(active_client) if active_client in clients else 0
selected_client = st.selectbox("Select Client", clients, index=default_index, key="mapping_client")

if st.session_state.get("_mapping_active_client") != selected_client:
    for key in [
        "mapping_results",
        "mapping_meta",
        "_mapping_pasted_df",
    ]:
        st.session_state.pop(key, None)
    st.session_state._mapping_active_client = selected_client
    st.session_state.mapping_results_client = selected_client

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

if (
    st.session_state.get("mapping_results_client") != selected_client
    or "mapping_results" not in st.session_state
):
    saved = load_latest_results(selected_client, "mapping")
    if saved and saved.get("results"):
        st.session_state.mapping_results = saved["results"]
        st.session_state.mapping_meta = saved.get("meta", {})
    else:
        st.session_state.mapping_results = []
        st.session_state.mapping_meta = {}
    st.session_state.mapping_results_client = selected_client

# ── Keyword input ────────────────────────────────────────────────

st.subheader("Add Keywords")
input_tab_csv, input_tab_paste = st.tabs(["Upload CSV", "Paste Keywords"])

df = None

with input_tab_csv:
    st.caption("Upload the cleaned keywords from Keyword Cleaning, or any CSV with a keyword column.")
    uploaded = st.file_uploader("Choose CSV file", type=["csv"], key=f"mapping_csv_{selected_client}")

    # Optional second CSV
    with st.expander("Optional: Upload additional raw research keywords"):
        uploaded_extra = st.file_uploader(
            "Additional keywords CSV", type=["csv"], key=f"mapping_extra_csv_{selected_client}"
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
        key=f"mapping_paste_{selected_client}",
        placeholder="spine surgery near me\nbest orthopedic surgeon\nmedical marketing agency",
    )
    if pasted.strip() and st.button("Use These Keywords", key=f"use_pasted_mapping_{selected_client}"):
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

    current_meta = st.session_state.get("mapping_meta", {})
    current_results = st.session_state.get("mapping_results", [])
    legacy_partial_checkpoint = (
        current_results
        and not current_meta
        and len(current_results) < len(df)
    )
    partial_checkpoint = (
        current_meta
        and current_meta.get("client_slug") == selected_client
        and not current_meta.get("completed", True)
    )
    button_label = "Map Keywords"
    if partial_checkpoint:
        processed = current_meta.get("processed_batches")
        total = current_meta.get("total_batches")
        if isinstance(processed, int) and isinstance(total, int) and processed < total:
            button_label = f"Resume Mapping from Batch {processed + 1}"
        else:
            button_label = "Resume Mapping"
    elif legacy_partial_checkpoint:
        next_batch = (len(current_results) // BATCH_SIZE) + 1
        button_label = f"Resume Mapping from Batch {next_batch}"

    if st.button(button_label, type="primary", key=f"map_keywords_{selected_client}"):
        total_batches = max(1, (len(df) + BATCH_SIZE - 1) // BATCH_SIZE)
        existing_meta = st.session_state.get("mapping_meta", {})
        existing_results = st.session_state.get("mapping_results", [])
        processed_batches = existing_meta.get("processed_batches")
        checkpoint_matches_source = (
            existing_results
            and existing_meta.get("client_slug") == selected_client
            and not existing_meta.get("completed", True)
            and existing_meta.get("source_keyword_count") == len(df)
            and existing_meta.get("total_batches") == total_batches
            and existing_meta.get("batch_size", BATCH_SIZE) == BATCH_SIZE
            and isinstance(processed_batches, int)
            and 0 <= processed_batches <= total_batches
        )
        legacy_checkpoint_matches_source = (
            existing_results
            and not existing_meta
            and len(existing_results) < len(df)
        )

        if checkpoint_matches_source:
            all_results = list(existing_results)
            start_batch_idx = processed_batches
            if start_batch_idx < total_batches:
                st.info(f"Resuming from batch {start_batch_idx + 1} of {total_batches}.")
            else:
                st.info("All batches were already checkpointed.")
        elif legacy_checkpoint_matches_source:
            start_batch_idx = min(len(existing_results) // BATCH_SIZE, total_batches)
            all_results = list(existing_results[: start_batch_idx * BATCH_SIZE])
            st.info(f"Resuming from batch {start_batch_idx + 1} of {total_batches}.")
        else:
            all_results = []
            start_batch_idx = 0
            if partial_checkpoint or legacy_partial_checkpoint:
                st.warning(
                    "The saved mapping checkpoint does not match the keyword source currently loaded. "
                    "Starting from batch 1."
                )

        st.session_state.mapping_results = list(all_results)
        st.session_state.mapping_meta = {
            "client_slug": selected_client,
            "client_business_name": profile.get("business_name", selected_client),
            "source_keyword_count": len(df),
            "processed_batches": start_batch_idx,
            "total_batches": total_batches,
            "batch_size": BATCH_SIZE,
            "completed": False,
        }
        st.session_state.mapping_results_client = selected_client

        progress_bar = st.progress(0)
        progress_bar.progress(start_batch_idx / total_batches)

        stopped_early = False

        with st.status("Mapping keywords to URLs...", expanded=True) as status:
            batch_status = st.empty()
            if start_batch_idx >= total_batches:
                batch_status.success(f"All {total_batches} batches were already checkpointed.")

            for batch_idx in range(start_batch_idx, total_batches):
                start = batch_idx * BATCH_SIZE
                end = min(start + BATCH_SIZE, len(df))
                batch_df = df.iloc[start:end]

                batch_status.write(
                    f"Batch {batch_idx + 1}/{total_batches} "
                    f"({start + 1}-{end}) | {len(all_results):,} results saved"
                )

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
                    error_message = format_llm_error(e)
                    st.error(f"Batch {batch_idx + 1} failed: {error_message}")
                    checkpoint_meta = {
                        "client_slug": selected_client,
                        "client_business_name": profile.get("business_name", selected_client),
                        "source_keyword_count": len(df),
                        "processed_batches": batch_idx,
                        "total_batches": total_batches,
                        "batch_size": BATCH_SIZE,
                        "completed": False,
                        "failed_batch": batch_idx + 1,
                        "last_error": error_message,
                    }
                    save_results(
                        selected_client,
                        "mapping",
                        {"results": list(all_results), "meta": checkpoint_meta},
                    )
                    incident = report_incident(
                        client_slug=selected_client,
                        job_type="keyword_mapping",
                        failed_batch=batch_idx + 1,
                        processed_batches=batch_idx,
                        total_batches=total_batches,
                        saved_result_count=len(all_results),
                        error_message=error_message,
                    )
                    checkpoint_meta["incident_id"] = incident["incident_id"]
                    st.session_state.mapping_results = list(all_results)
                    st.session_state.mapping_meta = checkpoint_meta
                    if incident["remote_saved"]:
                        st.info(
                            "Your progress is safe, and this error was sent to support. "
                            f"Reference {incident['incident_id'][:8]}."
                        )
                    else:
                        st.warning(
                            "Your progress is safe. The support report couldn't be sent, "
                            "so please share the error shown above."
                        )
                    status.update(
                        label=(
                            f"Stopped at batch {batch_idx + 1}. "
                            f"Results through batch {batch_idx} were saved."
                        ),
                        state="error",
                    )
                    stopped_early = True
                    break

                progress_bar.progress((batch_idx + 1) / total_batches)

                checkpoint_meta = {
                    "client_slug": selected_client,
                    "client_business_name": profile.get("business_name", selected_client),
                    "source_keyword_count": len(df),
                    "processed_batches": batch_idx + 1,
                    "total_batches": total_batches,
                    "batch_size": BATCH_SIZE,
                    "completed": False,
                }

                # Auto-save after each batch
                save_results(selected_client, "mapping", {"results": list(all_results), "meta": checkpoint_meta})
                st.session_state.mapping_results = list(all_results)
                st.session_state.mapping_meta = checkpoint_meta

                if batch_idx < total_batches - 1:
                    time.sleep(1)

            if stopped_early:
                processed_batches = st.session_state.get("mapping_meta", {}).get(
                    "processed_batches",
                    start_batch_idx,
                )
                batch_status.warning(
                    f"Stopped after {processed_batches} of {total_batches} batches. "
                    "Fix the API issue, then use the resume button."
                )
            else:
                final_meta = {
                    **st.session_state.get("mapping_meta", {}),
                    "processed_batches": total_batches,
                    "completed": True,
                }
                save_results(selected_client, "mapping", {"results": list(all_results), "meta": final_meta})
                st.session_state.mapping_meta = final_meta
                status.update(label=f"Done! Mapped {len(all_results)} keywords.", state="complete")

        st.session_state.mapping_results = list(all_results)
        cost_tracker.save_log(selected_client)

# ── Results view ─────────────────────────────────────────────────

results = st.session_state.get("mapping_results", [])
if not results:
    st.stop()

results_df = pd.DataFrame(results)
meta = st.session_state.get("mapping_meta", {})
if meta and meta.get("client_slug") == selected_client and not meta.get("completed", True):
    st.warning(
        "Showing a partial mapping checkpoint for "
        f"**{meta.get('client_business_name', selected_client)}**: "
        f"batch {meta.get('processed_batches', '?')}/{meta.get('total_batches', '?')} saved. "
        "Load the same keyword source, then use the resume button to continue from the next batch."
    )

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
    st.session_state.mapping_meta = {}
    if "_mapping_pasted_df" in st.session_state:
        del st.session_state._mapping_pasted_df
    st.rerun()
