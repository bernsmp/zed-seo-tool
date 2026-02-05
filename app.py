import streamlit as st

from utils.data import list_clients
from utils.llm import cost_tracker, _model

st.set_page_config(
    page_title="SEO Keyword Tool",
    page_icon="🔍",
    layout="wide",
)

# Pages
client_setup = st.Page("pages/client_setup.py", title="Client Setup", icon="👤")
keyword_cleaning = st.Page("pages/keyword_cleaning.py", title="Keyword Cleaning", icon="🧹")
keyword_mapping = st.Page("pages/keyword_mapping.py", title="Keyword Mapping", icon="🗺️")

pg = st.navigation([client_setup, keyword_cleaning, keyword_mapping])

# Load client list from disk on startup
if "clients_list" not in st.session_state:
    st.session_state.clients_list = list_clients()

# Sidebar
with st.sidebar:
    st.title("SEO Keyword Tool")
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
        st.info("No clients yet. Start with Client Setup.")

    # Cost monitor
    st.divider()
    st.caption(f"Model: `{_model().split('/')[-1]}`")
    summary = cost_tracker.summary()
    if summary["total_calls"] > 0:
        st.metric("Session Cost", f"${summary['total_cost_usd']:.4f}")
        st.caption(
            f"{summary['total_calls']} calls · "
            f"{summary['total_input_tokens']:,} in · "
            f"{summary['total_output_tokens']:,} out"
        )

pg.run()
