"""BDC Transition Agent Suite - router (Streamlit). SYNTHETIC data, DEMO mode only.

Two entries:
  * Agent Suite (default): a two-level agent cockpit (Home -> Delta journey | Agents | Architecture & operations), v0.13: five stages, three agents.
  * Old demo: the v0.12 reporting analyzer, clubbed into one page (?view=old-demo, legacy ?page=<slug> links also open it).
The suite renders its own shell bar, so the Streamlit sidebar is not used.
"""
import streamlit as st

st.set_page_config(page_title="BDC Transition Agent Suite", page_icon="\U0001F9ED", layout="wide", initial_sidebar_state="auto",
                   menu_items={"Get help": None, "Report a bug": None,
                               "About": "Independent assessment prototype, not affiliated with SAP. Synthetic data only."})

import logging
import uuid

OLD_SLUGS = {"vision", "ar-aging", "architecture", "evidence", "methodology"}
ss = st.session_state
if "nav_view" not in ss:
    qp = st.query_params
    if qp.get("view") == "old-demo" or qp.get("page", "") in OLD_SLUGS:
        ss["nav_view"] = "old"
    else:
        import v013_page
        ss["nav_view"] = "home"
        if qp.get("space") in v013_page.SPACE_BY_SLUG:  # deep link: ?space=delta-journey&stage=2
            ss["nav_view"] = "space"
            ss["tabs_space"] = v013_page.SPACE_BY_SLUG[qp.get("space")]
            if qp.get("stage") in ("1", "2", "3", "4", "5"):
                ss["tabs_stage"] = v013_page.STAGE_LABELS[int(qp.get("stage")) - 1]

try:
    if ss["nav_view"] == "old":
        import old_demo
        old_demo.render()
    else:
        for _k in ("view", "page"):
            if _k in st.query_params:
                del st.query_params[_k]
        import v013_page
        v013_page.render()
except Exception:  # noqa: BLE001 - a support-friendly failure: fixed message, error id, details in the app log only
    _eid = uuid.uuid4().hex[:8]
    logging.getLogger("bdc").exception("render failed, error id %s", _eid)
    st.error(f"Something went wrong while rendering this page (error id {_eid}). Reload the page or reopen it from Home; "
             "quote the error id when you report it. No data was changed: this app is read-only and synthetic.")
