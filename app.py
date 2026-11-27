"""BDC Transition Agent Suite - router (Streamlit). SYNTHETIC data, DEMO mode only.

Two entries:
  * Agent Suite (default): a two-level agent cockpit (Home -> Delta journey | Agents | Architecture & operations), v0.13: five stages, three agents.
  * Old demo: the v0.12 reporting analyzer, clubbed into one page (?view=old-demo, legacy ?page=<slug> links also open it).
The suite renders its own shell bar, so the Streamlit sidebar is not used.
"""
import streamlit as st

st.set_page_config(page_title="BDC Transition Agent Suite", page_icon="\U0001F9ED", layout="wide", initial_sidebar_state="collapsed",
                   menu_items={"Get help": None, "Report a bug": None,
                               "About": "Independent assessment prototype, not affiliated with SAP. Synthetic data only."})

OLD_SLUGS = {"vision", "ar-aging", "architecture", "evidence", "methodology"}
ss = st.session_state
if "nav_view" not in ss:
    qp = st.query_params
    ss["nav_view"] = "old" if (qp.get("view") == "old-demo" or qp.get("page", "") in OLD_SLUGS) else "home"

if ss["nav_view"] == "old":
    import old_demo
    old_demo.render()
else:
    for _k in ("view", "page"):
        if _k in st.query_params:
            del st.query_params[_k]
    import v013_page
    v013_page.render()
