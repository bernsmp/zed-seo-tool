import base64
from pathlib import Path

import streamlit as st

from utils.data import list_clients
from utils.llm import _model, cost_tracker

st.set_page_config(
    page_title="Trackable Med · SEO Tool",
    page_icon="🔍",
    layout="wide",
)

# ── Brand CSS ────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');

/* ── Global ──────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* ── Sidebar ─────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1B2B5E 0%, #2D398E 40%, #266BA2 100%);
}
section[data-testid="stSidebar"] * {
    color: #E8F0FE !important;
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stCaption {
    color: rgba(232, 240, 254, 0.65) !important;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.12) !important;
}
section[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 8px;
}
section[data-testid="stSidebar"] [data-testid="stMetricValue"] {
    color: #26A8E0 !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
}

/* Sidebar nav links */
section[data-testid="stSidebar"] nav a {
    border-radius: 8px !important;
    padding: 0.5rem 0.75rem !important;
    transition: background 0.2s ease !important;
}
section[data-testid="stSidebar"] nav a:hover {
    background: rgba(255,255,255,0.08) !important;
}
section[data-testid="stSidebar"] nav a[aria-selected="true"] {
    background: rgba(38, 168, 224, 0.2) !important;
    border-left: 3px solid #26A8E0 !important;
}

/* ── Main content ────────────────────────────── */
h1 {
    color: #1B2B5E !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
}
h2, h3 {
    color: #2D398E !important;
    font-weight: 600 !important;
}

/* Primary buttons */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #26A8E0 0%, #2D398E 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.5rem 1.5rem !important;
    transition: opacity 0.2s ease, transform 0.1s ease !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}

/* Secondary buttons */
.stDownloadButton > button {
    border: 1.5px solid #26A8E0 !important;
    color: #2D398E !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    background: white !important;
}
.stDownloadButton > button:hover {
    background: #EFF4F9 !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0 !important;
    border-bottom: 2px solid #E2E8F0 !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0 !important;
    padding: 0.5rem 1.25rem !important;
    font-weight: 500 !important;
}
.stTabs [aria-selected="true"] {
    border-bottom: 3px solid #26A8E0 !important;
    color: #2D398E !important;
    font-weight: 600 !important;
}

/* Metrics */
[data-testid="stMetricValue"] {
    color: #1B2B5E !important;
    font-weight: 700 !important;
}

/* Info/Warning/Success boxes */
.stAlert {
    border-radius: 8px !important;
}

/* File uploader */
[data-testid="stFileUploader"] {
    border-radius: 10px !important;
}
[data-testid="stFileUploader"] section {
    border: 2px dashed rgba(38, 168, 224, 0.3) !important;
    border-radius: 10px !important;
    background: rgba(38, 168, 224, 0.03) !important;
}

/* Progress bar */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #26A8E0, #2D398E) !important;
}

/* Text inputs */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    border-radius: 8px !important;
    border: 1.5px solid #D1D9E6 !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #26A8E0 !important;
    box-shadow: 0 0 0 2px rgba(38, 168, 224, 0.15) !important;
}

/* Data editor */
[data-testid="stDataFrame"] {
    border-radius: 10px !important;
    overflow: hidden !important;
}

/* Expander */
.streamlit-expanderHeader {
    font-weight: 500 !important;
    color: #2D398E !important;
}

/* Hide deploy button and main menu */
.stDeployButton, [data-testid="stMainMenu"] { display: none !important; }
header[data-testid="stHeader"] .stDeployButton { display: none !important; }

/* Hide anchor link icons on headers */
a.header-anchor, .stMarkdown a[href^="#"],
h1 a, h2 a, h3 a, h4 a,
[data-testid="stHeadingWithActionElements"] [data-testid="stHeaderActionElements"] {
    display: none !important;
}

/* Page hero header */
.page-hero {
    background: linear-gradient(135deg, #EFF4F9 0%, #E0EBF5 100%);
    border-left: 4px solid #26A8E0;
    border-radius: 0 12px 12px 0;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
}
.page-hero .step-badge {
    display: inline-block;
    background: linear-gradient(135deg, #26A8E0 0%, #2D398E 100%);
    color: white;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 0.25rem 0.75rem;
    border-radius: 20px;
    margin-bottom: 0.5rem;
}
.page-hero h1 {
    font-size: 2rem !important;
    margin: 0.25rem 0 0.5rem 0 !important;
    padding: 0 !important;
    line-height: 1.2 !important;
}
.page-hero p {
    color: #4A5568 !important;
    font-size: 1rem;
    margin: 0 !important;
    line-height: 1.5;
}

/* Subtle page dividers */
hr {
    border-color: #E2E8F0 !important;
}

/* ── QC Summary Card ────────────────────────── */
.qc-card {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 1.5rem 2rem;
    margin: 1rem 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.qc-card.qc-good {
    border-left: 4px solid #38A169;
}
.qc-card.qc-fair {
    border-left: 4px solid #D69E2E;
}
.qc-card.qc-needs-review {
    border-left: 4px solid #E53E3E;
}
.qc-card .qc-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
}
.qc-card .qc-score {
    font-size: 2rem;
    font-weight: 700;
    line-height: 1;
}
.qc-card .qc-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #718096;
    font-weight: 600;
}
.qc-card .qc-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #1B2B5E;
}
.qc-card .qc-body {
    color: #4A5568;
    font-size: 0.95rem;
    line-height: 1.6;
}
.qc-card .qc-tip {
    background: #EBF8FF;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-top: 0.75rem;
    font-size: 0.9rem;
    color: #2B6CB0;
}
.qc-card .qc-flag {
    background: #FFFBEB;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    margin-top: 0.5rem;
    font-size: 0.85rem;
    color: #975A16;
    border-left: 3px solid #D69E2E;
}

/* ── Confidence bar ─────────────────────────── */
.confidence-bar {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
}
.confidence-bar .bar {
    width: 60px;
    height: 6px;
    background: #E2E8F0;
    border-radius: 3px;
    overflow: hidden;
}
.confidence-bar .bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
}

/* ── How-to guide cards ─────────────────────── */
.guide-step {
    background: white;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
    transition: box-shadow 0.2s ease;
}
.guide-step:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.guide-step .step-num {
    display: inline-block;
    background: linear-gradient(135deg, #26A8E0 0%, #2D398E 100%);
    color: white;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    text-align: center;
    line-height: 24px;
    font-size: 0.75rem;
    font-weight: 700;
    margin-right: 0.5rem;
}
.guide-step .step-title {
    font-weight: 600;
    color: #1B2B5E;
    font-size: 0.95rem;
}
.guide-step .step-desc {
    color: #718096;
    font-size: 0.85rem;
    margin-top: 0.25rem;
    margin-left: 2rem;
}

/* ── Info callout ───────────────────────────── */
.info-callout {
    background: linear-gradient(135deg, #EBF8FF 0%, #E6F7FF 100%);
    border-left: 3px solid #26A8E0;
    border-radius: 0 8px 8px 0;
    padding: 1rem 1.25rem;
    margin: 0.75rem 0;
    font-size: 0.9rem;
    color: #2C5282;
    line-height: 1.5;
}
</style>
""", unsafe_allow_html=True)

# ── Pages ────────────────────────────────────────────────────────

client_setup = st.Page("pages/client_setup.py", title="Client Setup", icon="👤", default=True)
keyword_cleaning = st.Page("pages/keyword_cleaning.py", title="Keyword Cleaning", icon="🧹")
keyword_mapping = st.Page("pages/keyword_mapping.py", title="Keyword Mapping", icon="🗺️")
content_briefs = st.Page("pages/content_briefs.py", title="Content Briefs", icon="📝")
how_it_works = st.Page("pages/how_it_works.py", title="How It Works", icon="📖")

pg = st.navigation({
    "Workflow": [client_setup, keyword_cleaning, keyword_mapping, content_briefs],
    "Resources": [how_it_works],
})

# Logo above nav (st.logo renders at the top of the sidebar)
logo_path = Path(__file__).parent / "assets" / "logo-white.svg"
symbol_path = Path(__file__).parent / "assets" / "logo-symbol.svg"
if logo_path.exists():
    st.logo(str(logo_path), size="large", icon_image=str(symbol_path))

# Load client list from disk on startup
if "clients_list" not in st.session_state:
    st.session_state.clients_list = list_clients()

# ── Sidebar ──────────────────────────────────────────────────────

with st.sidebar:
    st.caption("SEO KEYWORD TOOL")
    st.divider()

    if st.session_state.clients_list:
        selected = st.selectbox(
            "Active Client",
            st.session_state.clients_list,
            index=(
                st.session_state.clients_list.index(st.session_state.active_client)
                if st.session_state.get("active_client") in st.session_state.clients_list
                else 0
            ),
        )
        st.session_state.active_client = selected
    else:
        st.markdown(
            '<p style="color:rgba(232,240,254,0.5);font-size:0.85rem;">'
            "No clients yet — start with Client Setup.</p>",
            unsafe_allow_html=True,
        )

    # Cost monitor
    st.divider()
    model_short = _model().split("/")[-1]
    st.caption(f"MODEL: {model_short}")
    summary = cost_tracker.summary()
    if summary["total_calls"] > 0:
        st.metric("Session Cost", f"${summary['total_cost_usd']:.4f}")
        st.caption(
            f"{summary['total_calls']} calls · "
            f"{summary['total_input_tokens']:,} in · "
            f"{summary['total_output_tokens']:,} out"
        )

pg.run()
