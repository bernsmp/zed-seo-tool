"""
SOW Generator — Step-by-step Statement of Work builder for TrackableMed sales reps.
Transcript → AI extraction → rep confirmation → DOCX + PM Brief.
"""

from datetime import date

import streamlit as st

from utils.sow import (
    SERVICE_TYPES,
    REPS,
    build_pm_brief,
    build_sow_docx,
    extract_from_transcript,
    generate_sow_content,
)

# ── Page header ──────────────────────────────────────────────────

st.markdown("""
<div class="page-hero">
    <span class="step-badge">Sales Ops</span>
    <h1>SOW Generator</h1>
    <p>Paste a call transcript, confirm the details, and get a client-ready Statement of Work
    plus a PM brief for Camila — in under 2 minutes.</p>
</div>
""", unsafe_allow_html=True)

# ── Session state init ───────────────────────────────────────────

if "sow_step" not in st.session_state:
    st.session_state.sow_step = 1
if "sow_extracted" not in st.session_state:
    st.session_state.sow_extracted = {}
if "sow_content" not in st.session_state:
    st.session_state.sow_content = {}
if "sow_docx_bytes" not in st.session_state:
    st.session_state.sow_docx_bytes = None
if "sow_pm_brief" not in st.session_state:
    st.session_state.sow_pm_brief = ""

# ── Step indicator ───────────────────────────────────────────────

step = st.session_state.sow_step

col1, col2, col3 = st.columns(3)
step_styles = {
    "active": "background:linear-gradient(135deg,#26A8E0 0%,#2D398E 100%);color:white;border-radius:8px;padding:0.6rem 1rem;text-align:center;font-weight:600;",
    "done": "background:#EFF4F9;color:#2D398E;border-radius:8px;padding:0.6rem 1rem;text-align:center;font-weight:500;border:1.5px solid #26A8E0;",
    "pending": "background:#F7FAFC;color:#A0AEC0;border-radius:8px;padding:0.6rem 1rem;text-align:center;font-weight:400;border:1px solid #E2E8F0;",
}

def _step_style(n):
    if n < step:
        return step_styles["done"]
    if n == step:
        return step_styles["active"]
    return step_styles["pending"]

with col1:
    st.markdown(f'<div style="{_step_style(1)}">1 · Paste Transcript</div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div style="{_step_style(2)}">2 · Review & Pricing</div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div style="{_step_style(3)}">3 · Download</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# STEP 1 — Input
# ════════════════════════════════════════════════════════════════

if step == 1:
    with st.form("sow_step1"):
        st.subheader("Call Details")

        c1, c2 = st.columns([2, 1])
        with c1:
            rep_name = st.radio(
                "Rep generating this SOW",
                REPS,
                horizontal=True,
                help="Controls the 'From' field. Zed always signs — this is just the rep who ran the call.",
            )
        with c2:
            sow_date = st.date_input("SOW Date", value=date.today())

        st.markdown("---")
        st.subheader("Call Transcript")
        transcript = st.text_area(
            "Paste the full transcript here",
            height=350,
            placeholder="Paste the Granola / Fathom / Otter transcript. The AI will extract client name, service type, goals, and any budget signals mentioned.",
        )

        submitted = st.form_submit_button("Extract from Transcript →", type="primary", use_container_width=True)

    if submitted:
        if not transcript.strip():
            st.error("Transcript is required. Paste the call transcript above.")
        else:
            with st.spinner("Extracting key details from transcript…"):
                extracted = extract_from_transcript(transcript)

            st.session_state.sow_extracted = extracted
            st.session_state.sow_rep_name = rep_name
            st.session_state.sow_date = sow_date.strftime("%B %d, %Y")
            st.session_state.sow_transcript = transcript
            st.session_state.sow_step = 2
            st.rerun()


# ════════════════════════════════════════════════════════════════
# STEP 2 — Review & Confirm
# ════════════════════════════════════════════════════════════════

elif step == 2:
    extracted = st.session_state.sow_extracted
    conf = extracted.get("service_type_confidence", 0)
    conf_color = "#38A169" if conf >= 80 else "#D69E2E" if conf >= 50 else "#E53E3E"

    st.markdown(f"""
    <div class="info-callout">
        <strong>AI extraction complete.</strong> Review the fields below — correct anything that's wrong or unclear,
        then fill in pricing. The AI detected service type with
        <span style="color:{conf_color};font-weight:600;">{conf}% confidence</span>:
        {extracted.get("service_type_reasoning", "")}
    </div>
    """, unsafe_allow_html=True)

    with st.form("sow_step2"):

        # ── Client details ────────────────────────────────────────
        st.subheader("Client Details")
        c1, c2 = st.columns(2)
        with c1:
            client_name = st.text_input(
                "Client / Practice Name",
                value=extracted.get("client_name") or "",
            )
            practice_specialty = st.text_input(
                "Practice Specialty",
                value=extracted.get("practice_specialty") or "",
                help="e.g. ENT, Urology, Pain Management, Orthopedics",
            )
        with c2:
            client_contact = st.text_input(
                "Requested By (client contact name)",
                value=extracted.get("client_contact") or "",
            )
            client_goals = st.text_area(
                "Client Goals",
                value=extracted.get("client_goals") or "",
                height=100,
            )

        # ── Service type ──────────────────────────────────────────
        st.markdown("---")
        st.subheader("Service Type")

        service_options = list(SERVICE_TYPES.keys())
        service_labels = list(SERVICE_TYPES.values())
        detected = extracted.get("service_type", "seo_web")
        default_idx = service_options.index(detected) if detected in service_options else 0

        service_type = st.radio(
            "Confirm service type",
            service_options,
            format_func=lambda k: SERVICE_TYPES[k],
            index=default_idx,
            horizontal=True,
        )

        # Context fields
        services_mentioned = st.text_input(
            "Services / platforms mentioned in call",
            value=", ".join(extracted.get("services_mentioned") or []),
            help="Edit as needed — this feeds the scope section",
        )
        notes = st.text_area(
            "Additional context for SOW",
            value=extracted.get("notes") or "",
            height=80,
            help="Anything else relevant that didn't fit above",
        )

        # ── Pricing ───────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Pricing")
        st.caption("Always fill this manually — pricing doesn't come from the transcript.")

        pricing_items = []

        if service_type == "seo_web":
            c1, c2 = st.columns(2)
            with c1:
                monthly = st.text_input("Monthly Recurring", placeholder="$1,175/mo")
            with c2:
                setup = st.text_input("One-Time Setup Fee (optional)", placeholder="Leave blank if none")

            if monthly:
                pricing_items.append({"item": "Monthly SEO & Website Management", "cost": monthly, "total": monthly})
            if setup:
                pricing_items.append({"item": "One-Time Setup Fee", "cost": setup, "total": setup})

        elif service_type == "digital_ads":
            c1, c2, c3 = st.columns(3)
            with c1:
                build_cost = st.text_input("Asset Build (one-time)", placeholder="$2,500")
            with c2:
                ad_budget = st.text_input("Monthly Ad Budget", placeholder="$2,500/mo")
            with c3:
                mgmt_fee = st.text_input("Monthly Management Fee", placeholder="$1,500/mo")

            show_discount = st.toggle("Show discounted pricing (strikethrough)?")
            if show_discount:
                c1, c2 = st.columns(2)
                with c1:
                    orig_build = st.text_input("Original build price (will show as strikethrough)", placeholder="$5,000")
                with c2:
                    orig_mgmt = st.text_input("Original mgmt price (will show as strikethrough)", placeholder="$3,000/mo")

            if build_cost:
                label = f"Asset Build (Reg. {orig_build})" if show_discount and orig_build else "Asset Build"
                pricing_items.append({"item": label, "cost": build_cost, "total": build_cost})
            if ad_budget:
                pricing_items.append({"item": "Monthly Advertising Budget", "cost": ad_budget, "total": ad_budget})
            if mgmt_fee:
                label = f"Monthly Management (Reg. {orig_mgmt})" if show_discount and orig_mgmt else "Monthly Management"
                pricing_items.append({"item": label, "cost": mgmt_fee, "total": mgmt_fee})

        elif service_type == "practice_consulting":
            c1, c2 = st.columns(2)
            with c1:
                diagnostic = st.text_input("One-Time Practice Assessment", placeholder="$3,450")
                show_guarantee = st.toggle("Include satisfaction guarantee?")
            with c2:
                consulting = st.text_input("Monthly Consulting", placeholder="$1,985/mo (promo)")
                standard_rate = st.text_input("Future Standard Rate (optional)", placeholder="$3,970/mo")

            if diagnostic:
                item_name = "Practice Assessment (100% satisfaction guarantee)" if show_guarantee else "Practice Assessment"
                pricing_items.append({"item": item_name, "cost": diagnostic, "total": diagnostic})
            if consulting:
                pricing_items.append({"item": "Monthly Consulting (Promotional Rate)", "cost": consulting, "total": consulting})
            if standard_rate:
                pricing_items.append({"item": "Standard Rate (after promotional period)", "cost": standard_rate, "total": standard_rate})

        payment_terms = st.selectbox(
            "Payment Terms",
            [
                "Invoiced Monthly – net 15 days on invoice",
                "Net 15 days on invoice",
                "Due at signing",
                "50% at signing, 50% at launch",
            ],
        )

        st.markdown("---")
        submitted = st.form_submit_button("Generate SOW →", type="primary", use_container_width=True)

    # Back button outside form
    if st.button("← Back to Step 1"):
        st.session_state.sow_step = 1
        st.rerun()

    if submitted:
        if not client_name.strip():
            st.error("Client name is required.")
        elif not pricing_items:
            st.error("Add at least one pricing line before generating.")
        else:
            confirmed_fields = {
                "rep_name": st.session_state.get("sow_rep_name", "Erik Trattler"),
                "sow_date": st.session_state.get("sow_date", date.today().strftime("%B %d, %Y")),
                "client_name": client_name.strip(),
                "client_contact": client_contact.strip(),
                "practice_specialty": practice_specialty.strip(),
                "service_type": service_type,
                "services_mentioned": [s.strip() for s in services_mentioned.split(",") if s.strip()],
                "client_goals": client_goals.strip(),
                "notes": notes.strip(),
                "pricing_items": pricing_items,
                "payment_terms": payment_terms,
            }

            with st.spinner("Generating SOW content…"):
                sow_content = generate_sow_content(confirmed_fields)

            with st.spinner("Building DOCX…"):
                docx_bytes = build_sow_docx(confirmed_fields, sow_content)
                pm_brief = build_pm_brief(confirmed_fields, sow_content)

            st.session_state.sow_confirmed_fields = confirmed_fields
            st.session_state.sow_content = sow_content
            st.session_state.sow_docx_bytes = docx_bytes
            st.session_state.sow_pm_brief = pm_brief
            st.session_state.sow_step = 3
            st.rerun()


# ════════════════════════════════════════════════════════════════
# STEP 3 — Download
# ════════════════════════════════════════════════════════════════

elif step == 3:
    fields = st.session_state.get("sow_confirmed_fields", {})
    content = st.session_state.sow_content
    docx_bytes = st.session_state.sow_docx_bytes
    pm_brief = st.session_state.sow_pm_brief

    client_name = fields.get("client_name", "Client")
    job_name = content.get("job_name", "SOW")
    service_label = SERVICE_TYPES.get(fields.get("service_type", "seo_web"), "")

    st.success(f"SOW ready — **{client_name}** · {service_label}")

    # ── SOW summary card ──────────────────────────────────────────
    st.markdown(f"""
    <div class="qc-card qc-good">
        <div class="qc-header">
            <div>
                <div class="qc-label">Statement of Work</div>
                <div class="qc-title">{job_name}</div>
            </div>
        </div>
        <div class="qc-body">
            <strong>Client:</strong> {client_name}<br>
            <strong>Contact:</strong> {fields.get("client_contact", "—")}<br>
            <strong>Rep:</strong> {fields.get("rep_name", "—")}<br>
            <strong>Date:</strong> {fields.get("sow_date", "—")}<br>
            <strong>Pricing:</strong> {" · ".join(i["cost"] for i in fields.get("pricing_items", []))}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Scope preview ─────────────────────────────────────────────
    with st.expander("Preview scope sections", expanded=False):
        for item in content.get("scope_items", []):
            st.markdown(f"**{item.get('heading', '')}**")
            for point in item.get("points", []):
                st.markdown(f"• {point}")
            st.markdown("")

    with st.expander("Preview summary", expanded=False):
        st.markdown(content.get("summary", ""))

    # ── Downloads ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Download")

    c1, c2 = st.columns(2)
    with c1:
        safe_name = client_name.replace(" ", "_").replace("/", "-")
        filename = f"TrackableMed_SOW_{safe_name}.docx"
        st.download_button(
            label="⬇  Download SOW (.docx)",
            data=docx_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            type="primary",
        )
        st.caption("Client-ready. Open in Word, review, then send.")

    with c2:
        st.download_button(
            label="⬇  Download PM Brief (.txt)",
            data=pm_brief.encode("utf-8"),
            file_name=f"PM_Brief_{safe_name}.txt",
            mime="text/plain",
            use_container_width=True,
        )
        st.caption("Forward to Camila for Wrike task setup.")

    # ── PM brief inline ───────────────────────────────────────────
    st.markdown("---")
    st.subheader("PM Brief")
    st.caption("Copy and send directly to Camila, or use the download above.")
    st.text_area(
        "PM Brief",
        value=pm_brief,
        height=300,
        label_visibility="collapsed",
    )

    # ── Reset ─────────────────────────────────────────────────────
    st.markdown("---")
    if st.button("Start New SOW", use_container_width=True):
        for key in [
            "sow_step", "sow_extracted", "sow_content",
            "sow_docx_bytes", "sow_pm_brief", "sow_confirmed_fields",
            "sow_rep_name", "sow_date", "sow_transcript",
        ]:
            st.session_state.pop(key, None)
        st.rerun()
