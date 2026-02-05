import streamlit as st
from utils.data import (
    slugify,
    save_client_profile,
    load_client_profile,
    list_clients,
)
from utils.crawler import crawl_site
from utils.llm import generate_client_profile

st.header("Client Setup")
st.write("Build a structured client profile by crawling their website.")

# ── Load existing profile ────────────────────────────────────────

clients = list_clients()
if clients:
    st.subheader("Load Existing Profile")
    selected = st.selectbox("Select client", ["-- New Client --"] + clients)
    if selected != "-- New Client --":
        profile = load_client_profile(selected)
        if profile:
            st.session_state.client_profile = profile
            st.session_state.client_slug = selected
            st.success(f"Loaded profile for **{profile.get('business_name', selected)}**")

st.divider()

# ── New client setup ─────────────────────────────────────────────

st.subheader("Create / Edit Profile")

col1, col2 = st.columns(2)
with col1:
    client_name = st.text_input(
        "Client Name",
        value=st.session_state.get("client_profile", {}).get("business_name", ""),
    )
with col2:
    domain = st.text_input(
        "Domain (e.g. example.com)",
        value=st.session_state.get("client_profile", {}).get("domain", ""),
    )

# ── Crawl site ───────────────────────────────────────────────────

if domain and st.button("Crawl Site & Generate Profile"):
    with st.status("Crawling site...", expanded=True) as status:
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(current, total):
            if total > 0:
                progress_bar.progress(current / total)
                status_text.text(f"Extracting page {current}/{total}...")

        pages = crawl_site(domain, max_pages=50, delay=1.0, progress_callback=update_progress)

        if not pages:
            st.warning("No pages found. You can fill in the profile manually below.")
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

profile = st.session_state.get("client_profile", {})

if profile or client_name:
    st.divider()
    st.subheader("Profile Details")
    st.caption("Edit any field, then click Save.")

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
    )
    locations = st.text_area(
        "Locations Served (one per line)",
        value="\n".join(profile.get("locations", [])),
        key="edit_locations",
    )
    specialties = st.text_area(
        "Specialties (one per line)",
        value="\n".join(profile.get("specialties", [])),
        key="edit_specialties",
    )
    topics = st.text_area(
        "Key Topics (one per line)",
        value="\n".join(profile.get("topics", [])),
        key="edit_topics",
    )

    st.divider()
    st.subheader("Negative Keywords")
    st.caption("Terms to always REMOVE during keyword cleaning (competitor names, wrong locations, etc.).")
    negative_keywords = st.text_area(
        "Negative Keywords (one per line)",
        value="\n".join(profile.get("negative_keywords", [])),
        key="edit_negatives",
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
            for page in url_inv:
                st.write(f"**{page.get('title', 'Untitled')}** — {page['url']}")
