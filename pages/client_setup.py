import streamlit as st
from utils.data import (
    slugify,
    save_client_profile,
    load_client_profile,
    list_clients,
)
from utils.crawler import crawl_site
from utils.llm import generate_client_profile

st.markdown("""
<div class="page-hero">
    <span class="step-badge">Step 1 of 4</span>
    <h1>Client Setup</h1>
    <p>Enter a client's domain and we'll crawl their site to build an SEO profile — services, locations, specialties, and a full URL inventory.</p>
</div>
""", unsafe_allow_html=True)

# ── How it works guide ───────────────────────────────────────────

with st.expander("How does this work?", expanded=False):
    st.markdown("""
    <div class="guide-step">
        <span class="step-num">1</span>
        <span class="step-title">Enter client name & domain</span>
        <div class="step-desc">Give the client a name and enter their website domain (e.g. <strong>example.com</strong>). This is used to crawl their site and build a profile.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">2</span>
        <span class="step-title">Crawl the site</span>
        <div class="step-desc">Click "Crawl Site & Generate Profile" to pull the client's sitemap, extract page content, and build a URL inventory. The AI then analyzes the pages to identify services, locations, and specialties.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">3</span>
        <span class="step-title">Review & edit the profile</span>
        <div class="step-desc">The AI-generated profile appears below. Review every field — add missing services, fix locations, remove anything wrong. You can also add <strong>negative keywords</strong> (competitor names, irrelevant terms) to improve cleaning accuracy.</div>
    </div>
    <div class="guide-step">
        <span class="step-num">4</span>
        <span class="step-title">Save & continue</span>
        <div class="step-desc">Hit Save to store the profile. Then head to <strong>Keyword Cleaning</strong> (Step 2) to start filtering keywords against this profile.</div>
    </div>
    """, unsafe_allow_html=True)

# ── Load existing profile ────────────────────────────────────────

clients = list_clients()
if clients:
    selected = st.selectbox("Select client to edit, or create new", ["-- New Client --"] + clients)
    if selected != "-- New Client --":
        profile = load_client_profile(selected)
        if profile:
            st.session_state.client_profile = profile
            st.session_state.client_slug = selected
else:
    selected = "-- New Client --"

st.divider()

# ── Client name & domain ────────────────────────────────────────

profile = st.session_state.get("client_profile", {})

st.subheader("Client Info")

col1, col2 = st.columns(2)
with col1:
    client_name = st.text_input(
        "Client Name",
        value=profile.get("business_name", ""),
    )
with col2:
    domain = st.text_input(
        "Domain (e.g. example.com)",
        value=profile.get("domain", ""),
    )

# ── Crawl site ───────────────────────────────────────────────────

if domain and st.button("Crawl Site & Generate Profile", type="primary"):
    with st.status("Crawling site...", expanded=True) as status:
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(current, total):
            if total > 0:
                progress_bar.progress(current / total)
                status_text.text(f"Extracting page {current}/{total}...")

        pages = crawl_site(domain, max_pages=50, delay=1.0, progress_callback=update_progress)

        if not pages:
            st.markdown("""
            <div class="info-callout">
                No pages found from the crawl. This can happen if the site blocks crawlers or has no sitemap. You can still fill in the profile manually below.
            </div>
            """, unsafe_allow_html=True)
            st.session_state.crawled_pages = []
        else:
            st.write(f"Crawled {len(pages)} pages. Generating profile...")
            st.session_state.crawled_pages = pages

            try:
                profile = generate_client_profile(domain, pages)
                profile["domain"] = domain
                if client_name:
                    profile["business_name"] = client_name
                # Store URL inventory from crawl
                profile["url_inventory"] = [
                    {"url": p["url"], "title": p.get("title", ""), "summary": p.get("content", "")[:200]}
                    for p in pages
                ]
                st.session_state.client_profile = profile
                status.update(label=f"Done! Crawled {len(pages)} pages.", state="complete")
            except Exception as e:
                st.error(f"LLM profile generation failed: {e}")
                status.update(label="Crawl complete, profile generation failed.", state="error")

# ── Editable profile form ────────────────────────────────────────

# Re-read profile in case crawl just updated it
profile = st.session_state.get("client_profile", {})

if profile or client_name:
    st.divider()
    st.subheader("Profile Details")
    st.caption("Review and edit every field — the AI uses this profile to classify keywords in Step 2.")

    business_name = st.text_input(
        "Business Name",
        value=profile.get("business_name", client_name or ""),
        key="edit_biz_name",
    )
    edit_domain = st.text_input(
        "Domain",
        value=profile.get("domain", domain or ""),
        key="edit_domain",
    )

    services = st.text_area(
        "Services (one per line)",
        value="\n".join(profile.get("services", [])),
        key="edit_services",
        help="List all services the client offers. These are used to determine which keywords are relevant.",
    )
    locations = st.text_area(
        "Locations Served (one per line)",
        value="\n".join(profile.get("locations", [])),
        key="edit_locations",
        help="Cities, states, or regions the client serves. Keywords for other locations will be flagged for removal.",
    )
    specialties = st.text_area(
        "Specialties (one per line)",
        value="\n".join(profile.get("specialties", [])),
        key="edit_specialties",
        help="Specific areas of expertise, conditions treated, or niche focus areas.",
    )
    topics = st.text_area(
        "Key Topics (one per line)",
        value="\n".join(profile.get("topics", [])),
        key="edit_topics",
        help="Core topics the business is known for — think subject areas, not goals. E.g. 'dental implants', 'cosmetic dentistry', 'teeth whitening'.",
    )

    st.divider()
    st.subheader("Negative Keywords")
    st.caption("Terms to always REMOVE during keyword cleaning — competitor names, wrong locations, irrelevant specialties.")
    negative_keywords = st.text_area(
        "Negative Keywords (one per line)",
        value="\n".join(profile.get("negative_keywords", [])),
        key="edit_negatives",
        help="Any keyword containing these terms will be automatically flagged for removal during cleaning.",
    )

    st.divider()
    st.subheader("Negative Categories")
    st.caption("Broader categories the AI should remove — e.g. 'Competitor brands', 'DIY home remedies', 'Unrelated medical specialties'.")
    negative_categories = st.text_area(
        "Negative Categories (one per line)",
        value="\n".join(profile.get("negative_categories", [])),
        key="edit_neg_categories",
        help="The AI will interpret these as rules during classification. Use for patterns too broad for individual keywords.",
    )

    # ── Save ─────────────────────────────────────────────────────

    if st.button("Save Profile", type="primary"):
        def _split_lines(text):
            return [line.strip() for line in text.strip().split("\n") if line.strip()]

        slug = slugify(business_name or edit_domain)
        updated_profile = {
            "business_name": business_name,
            "domain": edit_domain,
            "services": _split_lines(services),
            "locations": _split_lines(locations),
            "specialties": _split_lines(specialties),
            "topics": _split_lines(topics),
            "negative_keywords": _split_lines(negative_keywords),
            "negative_categories": _split_lines(negative_categories),
            "url_inventory": profile.get("url_inventory", []),
        }
        save_client_profile(slug, updated_profile)
        st.session_state.client_profile = updated_profile
        st.session_state.client_slug = slug

        # Refresh sidebar client list
        st.session_state.clients_list = list_clients()
        if slug not in st.session_state.clients_list:
            st.session_state.clients_list.append(slug)
        st.session_state.active_client = slug

        st.success(f"Profile saved as **{slug}**")

    # ── Show URL inventory ───────────────────────────────────────

    url_inv = profile.get("url_inventory", [])
    if url_inv:
        with st.expander(f"URL Inventory ({len(url_inv)} pages)"):
            st.caption("These URLs are used in Keyword Mapping (Step 3) to match keywords to existing pages.")
            for page in url_inv:
                st.write(f"**{page.get('title', 'Untitled')}** — {page['url']}")

    # ── Next step callout ────────────────────────────────────────

    st.markdown("""
    <div class="info-callout">
        <strong>Next step:</strong> Once your profile is saved, head to <strong>Keyword Cleaning</strong> (Step 2) to upload keywords and start filtering them against this profile.
    </div>
    """, unsafe_allow_html=True)
