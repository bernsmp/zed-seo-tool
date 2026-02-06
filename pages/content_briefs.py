import time

import pandas as pd
import streamlit as st

from utils.data import (
    export_csv,
    list_clients,
    load_client_profile,
    load_latest_results,
    save_results,
)
from utils.llm import cluster_keywords, cost_tracker, estimate_cost, generate_content_brief

st.markdown("""
<div class="page-hero">
    <span class="step-badge">Step 4 of 4</span>
    <h1>Content Briefs</h1>
    <p>Generate detailed, writer-ready content briefs for keywords that need <strong>new pages</strong> or <strong>blog posts</strong>. Each brief includes a title, outline, audience, SEO requirements, and internal linking recommendations.</p>
</div>
""", unsafe_allow_html=True)

# ── How it works guide ───────────────────────────────────────────

with st.expander("How does this work?", expanded=False):
    st.markdown("""
    <div class="guide-step">
        <span class="step-num">1</span>
        <span class="step-title">Select your client</span>
        <div class="step-desc">Choose the client profile from Step 1. The AI uses the client profile and URL inventory to generate contextually relevant briefs.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">2</span>
        <span class="step-title">Load mapping results</span>
        <div class="step-desc">Auto-loads keywords flagged as <strong>New Page</strong> or <strong>Blog Post</strong> from Step 3. These are the content opportunities the AI identified.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">3</span>
        <span class="step-title">AI clusters & generates briefs</span>
        <div class="step-desc">The AI groups related keywords into clusters, then creates one detailed brief per cluster. Each brief is writer-ready with a title, outline, audience targeting, SEO requirements, and internal linking recommendations.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">4</span>
        <span class="step-title">Review & copy</span>
        <div class="step-desc">Expand each brief card to review the content. Copy individual briefs to your clipboard or export all briefs to CSV for your content team.</div>
    </div>
    """, unsafe_allow_html=True)

# ── Client selection ─────────────────────────────────────────────

clients = list_clients()
if not clients:
    st.markdown("""
    <div class="info-callout">
        No client profiles found yet. Head to <strong>Client Setup</strong> to create one — you'll need a client profile before generating content briefs.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

selected_client = st.selectbox("Select Client", clients, key="briefs_client")
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
        No URL inventory found for this client. Go to <strong>Client Setup</strong> and crawl the site first — the AI needs the client's pages to recommend internal links.
    </div>
    """, unsafe_allow_html=True)

# ── Load mapping results ─────────────────────────────────────────

mapping_data = load_latest_results(selected_client, "mapping")
if not mapping_data or not mapping_data.get("results"):
    st.markdown("""
    <div class="info-callout">
        No keyword mapping results found. Complete <strong>Step 3 (Keyword Mapping)</strong> first to identify which keywords need new content.
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Filter to only New Page or Blog Post keywords
all_mapping_results = mapping_data.get("results", [])
brief_keywords = [
    kw for kw in all_mapping_results
    if kw.get("recommendation") in ["New Page", "Blog Post"]
]

if not brief_keywords:
    st.markdown("""
    <div class="info-callout">
        No keywords flagged for new content. All keywords were mapped to existing pages. If you want to generate briefs, go back to <strong>Step 3 (Keyword Mapping)</strong> and ensure some keywords are marked as "New Page" or "Blog Post".
    </div>
    """, unsafe_allow_html=True)
    st.stop()

st.write(f"**{len(brief_keywords)} keywords** need new content (from Step 3 mapping).")

# Preview table
preview_df = pd.DataFrame(brief_keywords).head(10)
keyword_col_preview = "keyword"
for col_name in ["keyword", "keywords", "query", "search query", "term"]:
    if col_name in preview_df.columns:
        keyword_col_preview = col_name
        break

preview_cols = [keyword_col_preview, "recommendation"]
if "volume" in preview_df.columns:
    preview_cols.append("volume")
if "search_intent" in preview_df.columns:
    preview_cols.append("search_intent")

st.dataframe(preview_df[preview_cols], use_container_width=True)

# ── Auto-load saved results if they exist ────────────────────────

if "brief_results" not in st.session_state or not st.session_state.brief_results:
    saved = load_latest_results(selected_client, "briefs")
    if saved and saved.get("briefs"):
        st.session_state.brief_results = saved["briefs"]
        if saved.get("clusters"):
            st.session_state.brief_clusters = saved["clusters"]

# ── Processing ───────────────────────────────────────────────────

# Find keyword column in brief_keywords
keyword_col = "keyword"
if brief_keywords:
    for col_name in ["keyword", "keywords", "query", "search query", "term"]:
        if col_name in brief_keywords[0]:
            keyword_col = col_name
            break

# Cost estimate
if "brief_clusters" in st.session_state and st.session_state.brief_clusters:
    est = estimate_cost(len(st.session_state.brief_clusters), "briefs")
else:
    # Estimate based on keywords (rough cluster estimate: keywords / 5)
    est_clusters = max(1, len(brief_keywords) // 5)
    est = estimate_cost(est_clusters, "briefs")

model_short = est["model"].split("/")[-1]
st.markdown(f"""
<div class="info-callout">
    <strong>Estimate</strong> ({model_short}): ~{est['batches']} brief{'s' if est['batches'] > 1 else ''}, ~{est['est_minutes']} min, ~${est['est_cost_usd']:.2f} LLM cost
</div>
""", unsafe_allow_html=True)

if st.button("Generate Content Briefs", type="primary"):
    # Step 1: Cluster keywords
    with st.status("Clustering related keywords...", expanded=True) as status:
        try:
            clusters = cluster_keywords(brief_keywords)
            st.session_state.brief_clusters = clusters
            st.write(f"Created {len(clusters)} keyword clusters.")
            status.update(label=f"Clustered into {len(clusters)} groups.", state="complete")
        except Exception as e:
            st.error(f"Clustering failed: {e}")
            st.stop()

    # Step 2: Generate briefs for each cluster
    all_briefs = []
    progress_bar = st.progress(0)

    with st.status("Generating content briefs...", expanded=True) as status:
        for i, cluster in enumerate(st.session_state.brief_clusters):
            st.write(f"Brief {i + 1}/{len(st.session_state.brief_clusters)}: {cluster.get('primary_keyword', 'N/A')}...")

            try:
                brief = generate_content_brief(profile, cluster, url_inventory)
                all_briefs.append(brief)

                # Auto-save after each brief
                save_results(
                    selected_client,
                    "briefs",
                    {"clusters": st.session_state.brief_clusters, "briefs": all_briefs},
                )

            except Exception as e:
                st.error(f"Brief {i + 1} failed: {e}")
                all_briefs.append({
                    "title": f"Brief {i + 1} (Failed)",
                    "overview": {"primary_keyword": cluster.get("primary_keyword", "N/A")},
                    "error": str(e),
                })

            progress_bar.progress((i + 1) / len(st.session_state.brief_clusters))

            if i < len(st.session_state.brief_clusters) - 1:
                time.sleep(1)

        status.update(label=f"Done! Generated {len(all_briefs)} content briefs.", state="complete")

    st.session_state.brief_results = all_briefs
    cost_tracker.save_log(selected_client)

# ── Results view ─────────────────────────────────────────────────

briefs = st.session_state.get("brief_results", [])
if not briefs:
    st.stop()

st.divider()
st.subheader("Results")

# Summary metrics
total_briefs = len(briefs)
service_page_count = len([b for b in briefs if "service" in b.get("overview", {}).get("content_type", "").lower()])
blog_post_count = len([b for b in briefs if "blog" in b.get("overview", {}).get("content_type", "").lower()])

col1, col2, col3 = st.columns(3)
col1.metric("Total Briefs", total_briefs)
col2.metric("Service Pages", service_page_count)
col3.metric("Blog Posts", blog_post_count)

# Brief cards
for i, brief in enumerate(briefs):
    if brief.get("error"):
        with st.expander(f"**{brief.get('title', f'Brief {i+1}')}** — Error", expanded=False):
            st.error(f"Failed to generate brief: {brief['error']}")
        continue

    overview = brief.get("overview", {})
    title = brief.get("title", overview.get("working_title", f"Brief {i+1}"))
    content_type = overview.get("content_type", "blog_post")
    type_label = "Service Page" if "service" in content_type else "Blog Post"

    with st.expander(f"**{title}** — {type_label}", expanded=(i == 0)):
        # Overview section
        st.markdown(f"**Primary Keyword:** {overview.get('primary_keyword', 'N/A')}")
        st.markdown(f"**Word Count:** {overview.get('word_count', 'N/A')} | **Goal:** {overview.get('goal', 'N/A')}")

        st.divider()

        # Audience
        audience = brief.get("audience", {})
        st.markdown("#### Audience")
        st.markdown(f"**Who:** {audience.get('who', 'N/A')}")
        st.markdown(f"**Problem:** {audience.get('problem', 'N/A')}")
        st.markdown(f"**Journey Stage:** {audience.get('journey_stage', 'N/A')}")

        st.divider()

        # Content Direction
        direction = brief.get("direction", {})
        st.markdown("#### Content Direction")
        st.markdown(f"**Unique Angle:** {direction.get('unique_angle', 'N/A')}")

        st.markdown("**Suggested Outline:**")
        for item in direction.get("outline", []):
            st.markdown(f"- **{item.get('heading', '')}** — {item.get('description', '')}")

        st.markdown("**Questions to Answer:**")
        for q in direction.get("questions", []):
            st.markdown(f"- {q}")

        st.markdown(f"**Tone:** {direction.get('tone', 'N/A')}")

        st.divider()

        # SEO Requirements
        seo = brief.get("seo", {})
        st.markdown("#### SEO Requirements")
        st.markdown(f"**Keyword Placement:** {seo.get('keyword_placement', 'N/A')}")

        secondary = seo.get("secondary_keywords", [])
        if secondary:
            st.markdown(f"**Secondary Keywords:** {', '.join(secondary)}")

        internal_links = seo.get("internal_links", [])
        if internal_links:
            st.markdown("**Internal Links:**")
            for link in internal_links:
                st.markdown(f"- [{link.get('anchor_text', link.get('url', ''))}]({link.get('url', '')}) — anchor: *\"{link.get('anchor_text', '')}\"*")

        st.markdown(f"**Meta Title:** {seo.get('meta_title', 'N/A')}")
        st.markdown(f"**Meta Description:** {seo.get('meta_description', 'N/A')}")

        st.divider()

        # CTA
        st.markdown("#### Call to Action")
        st.markdown(brief.get("cta", "N/A"))

        st.divider()

        # Copy-to-clipboard text area
        brief_text = f"""# {title}

**Content Type:** {type_label}
**Primary Keyword:** {overview.get('primary_keyword', 'N/A')}
**Word Count:** {overview.get('word_count', 'N/A')}
**Goal:** {overview.get('goal', 'N/A')}

## Audience
- **Who:** {audience.get('who', 'N/A')}
- **Problem:** {audience.get('problem', 'N/A')}
- **Journey Stage:** {audience.get('journey_stage', 'N/A')}

## Content Direction
**Unique Angle:** {direction.get('unique_angle', 'N/A')}

**Suggested Outline:**
{chr(10).join(f"- {item.get('heading', '')}: {item.get('description', '')}" for item in direction.get('outline', []))}

**Questions to Answer:**
{chr(10).join(f"- {q}" for q in direction.get('questions', []))}

**Tone:** {direction.get('tone', 'N/A')}

## SEO Requirements
**Keyword Placement:** {seo.get('keyword_placement', 'N/A')}
**Secondary Keywords:** {', '.join(secondary)}

**Internal Links:**
{chr(10).join(f"- {link.get('url', '')}: {link.get('anchor_text', '')}" for link in internal_links)}

**Meta Title:** {seo.get('meta_title', 'N/A')}
**Meta Description:** {seo.get('meta_description', 'N/A')}

## Call to Action
{brief.get('cta', 'N/A')}
"""
        st.text_area("Copy Brief", brief_text, height=200, key=f"brief_text_{i}")

# ── Export section ───────────────────────────────────────────────

st.divider()
st.subheader("Export")

# Flatten briefs for CSV export
export_rows = []
for brief in briefs:
    if brief.get("error"):
        continue

    overview = brief.get("overview", {})
    direction = brief.get("direction", {})
    seo = brief.get("seo", {})
    audience = brief.get("audience", {})

    outline_text = " | ".join(
        f"{item.get('heading', '')}: {item.get('description', '')}"
        for item in direction.get("outline", [])
    )

    export_rows.append({
        "title": brief.get("title", overview.get("working_title", "")),
        "primary_keyword": overview.get("primary_keyword", ""),
        "content_type": overview.get("content_type", ""),
        "word_count": overview.get("word_count", ""),
        "goal": overview.get("goal", ""),
        "audience": audience.get("who", ""),
        "problem": audience.get("problem", ""),
        "unique_angle": direction.get("unique_angle", ""),
        "outline": outline_text,
        "secondary_keywords": ", ".join(seo.get("secondary_keywords", [])),
        "meta_title": seo.get("meta_title", ""),
        "meta_description": seo.get("meta_description", ""),
        "cta": brief.get("cta", ""),
    })

export_df = pd.DataFrame(export_rows)

st.download_button(
    "Download All Briefs (CSV)",
    data=export_csv(export_df),
    file_name=f"{selected_client}_content_briefs.csv",
    mime="text/csv",
)

st.markdown("""
<div class="info-callout">
    <strong>How to use these briefs:</strong> Share each brief with your writer or content team. The outline, keywords, and internal links give them everything they need to create SEO-optimized content without back-and-forth.
</div>
""", unsafe_allow_html=True)

# Clear results button
if st.button("Clear Results & Start Over"):
    st.session_state.brief_results = []
    st.session_state.brief_clusters = []
    st.rerun()
