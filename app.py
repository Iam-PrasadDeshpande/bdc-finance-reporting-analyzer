"""BDC Finance Reporting Transition Analyzer - public site router (Streamlit).

Five outcome-oriented sections; "Vision & Approach" is the default page. Deep links: ?page=<slug>.
Public pages use only public-safe content (public_pages, ar_aging_demo). Internal pages (the private SAP-content PoC and
the analyzer workbench) load only locally when BDC_WORKBENCH=1 and the internal module is present; it is never shipped
in the public build.
"""
import importlib.util
import os

import streamlit as st

from public_home import PUBLIC_SECTIONS, render_vision_home

INTERNAL = os.environ.get("BDC_WORKBENCH") == "1" and importlib.util.find_spec("internal_routes") is not None
if INTERNAL:
    import internal_routes
SLUGS = {"Vision & Approach": "vision", "AR Aging Scenario": "ar-aging", "Architecture": "architecture",
         "Evidence & Limitations": "evidence", "Methodology": "methodology"}
BY_SLUG = {v: k for k, v in SLUGS.items()}
HOLD = "Real Finance assessment: HOLD / INSUFFICIENT_EVIDENCE"
TRADEMARK = ("SAP, SAP S/4HANA, SAP Business Data Cloud, SAP Datasphere and other SAP products and services mentioned are "
             "trademarks or registered trademarks of SAP SE (or an SAP affiliate company) in Germany and other countries. "
             "This site is not sponsored, endorsed or affiliated with SAP SE.")
SYNTHETIC_NOTE = ("All AR Aging figures on this site are SYNTHETIC. SYNTHETIC_PASS means two calculations agree on generated data "
                  "under the same definition; it is not a customer Finance reconciliation and says nothing about compatibility.")

st.set_page_config(page_title="BDC Finance Reporting Transition Analyzer", page_icon="📊", layout="wide",
                   menu_items={"Get help": None, "Report a bug": None,
                               "About": "Independent assessment prototype, not affiliated with SAP."})
st.markdown("""<style>
.block-container{padding-top:2.2rem;max-width:1180px}
h1,h2,h3{letter-spacing:-.02em}
.bdc-page-title{font-size:clamp(1.6rem,2.6vw,2.3rem);font-weight:800;color:#122c3c;margin:0 0 .3rem}
.bdc-page-lead{color:#4b6475;font-size:1.02rem;line-height:1.6;max-width:860px;margin-bottom:1rem}
</style>""", unsafe_allow_html=True)

# Navigation state: CTA requests first, then a deep link on first load, default Vision & Approach.
if "_bdc_requested_page" in st.session_state:
    st.session_state["bdc_public_page"] = st.session_state.pop("_bdc_requested_page")
elif "bdc_public_page" not in st.session_state:
    st.session_state["bdc_public_page"] = BY_SLUG.get(st.query_params.get("page", ""), PUBLIC_SECTIONS[0])

st.sidebar.markdown("### BDC Finance Reporting Transition Analyzer")
section = st.sidebar.radio("Explore", PUBLIC_SECTIONS, key="bdc_public_page")
st.sidebar.caption("Independent prototype, not affiliated with SAP. " + HOLD + ".")
if section == PUBLIC_SECTIONS[0]:
    if "page" in st.query_params:
        del st.query_params["page"]
else:
    st.query_params["page"] = SLUGS[section]


def page_header(title: str, lead: str) -> None:
    st.markdown(f'<div class="bdc-page-title">{title}</div><div class="bdc-page-lead">{lead}</div>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def public_summary() -> dict:
    import ar_aging_demo
    return ar_aging_demo.summary()


if section == "Vision & Approach":
    target = render_vision_home(internal_routes.home_summary() if INTERNAL else public_summary())
    if target:
        st.session_state["_bdc_requested_page"] = target
        st.rerun()

elif section == "AR Aging Scenario":
    page_header("AR Aging Scenario", "How the analyzer compares an S/4HANA report definition with a candidate BDC definition, "
                "reconciles the results and quantifies the Finance decisions that change them.")
    if INTERNAL:
        internal_routes.ar_aging()
    else:
        import public_pages
        st.error("SYNTHETIC DATA - method demonstration only. Not customer figures and not SAP-delivered content. "
                 "Finance transition: HOLD - INSUFFICIENT_EVIDENCE.")
        tabs = st.tabs(["Run demonstration", "Decision points", "About this demonstration"])
        with tabs[0]:
            public_pages.render_demo()
        with tabs[1]:
            public_pages.render_decision_points()
        with tabs[2]:
            import pathlib
            about = (pathlib.Path(__file__).parent / "public_content/ar_aging_scenario.md").read_text(encoding="utf-8")
            st.markdown(about)
            st.download_button("Download demonstration summary (Markdown)", about, "ar_aging_demonstration.md", mime="text/markdown")

elif section == "Architecture":
    page_header("Architecture", "Where the Finance definition lives today, where SAP Business Data Cloud could take it, and how "
                "the analyzer compares the two.")
    if INTERNAL:
        internal_routes.architecture()
    else:
        import public_pages
        public_pages.render_architecture()
    st.markdown("#### How the analyzer is built")
    c1, c2, c3 = st.columns(3)
    c1.markdown("**Metadata intake**\n- Read-only CDS/DDL and lineage intake\n- Data-product contract (CSN) ingestion\n"
                "- Public catalog capture with completeness audit")
    c2.markdown("**Assessment engines**\n- Semantic comparison by dimension (grain, ledger, currency, key date, buckets)\n"
                "- Evidence classification (documented, observed, inferred, missing)\n- Reuse / extend / customer-managed decision")
    c3.markdown("**Reconciliation**\n- Independent result sets with identical business context\n"
                "- Owner-approved tolerances\n- Synthetic data can reach SYNTHETIC_PASS only")

elif section == "Evidence & Limitations":
    page_header("Evidence & Limitations", "What has been demonstrated, what it is based on, and what is still missing before "
                "any customer recommendation.")
    c1, c2 = st.columns(2)
    c1.success("AR Aging: SYNTHETIC_PASS on generated data (method demonstration and internal proof of concept)")
    c2.error(HOLD)
    st.markdown("#### Evidence register")
    st.table([
        {"area": "S/4HANA 2023 AR aging query and cube", "what exists": "SAP public documentation: query reads the cube; key date; configurable intervals",
         "class": "SAP documented reference", "limitation": "Not the customer's system; customer report and definitions not read"},
        {"area": "BDC Finance catalog", "what exists": "Public SAP Business Accelerator Hub listing of Finance data products",
         "class": "Public listing", "limitation": "Names and versions only; no schemas"},
        {"area": "Finance data products and SAP-delivered analytical content", "what exists": "Reviewed read-only in an SAP trial tenant",
         "class": "Trial metadata (not published)", "limitation": "Not the customer tenant; details withheld pending SAP publication clearance"},
        {"area": "Internal AR aging proof of concept", "what exists": "Synthetic comparison against a re-implementation of SAP-delivered content: SYNTHETIC_PASS",
         "class": "Internal, synthetic", "limitation": "Not published; parts inferred; not verified against customer data"},
        {"area": "Public AR aging demonstration", "what exists": "Project-authored rules on generated data (this site)",
         "class": "Synthetic method demonstration", "limitation": "Does not represent SAP content or any customer"},
        {"area": "Technical discovery", "what exists": "Read-only CDS-to-table lineage on an ABAP trial system",
         "class": "Live trial metadata", "limitation": "Not an S/4HANA Finance system"},
        {"area": "Customer S/4HANA PCE 2023 SP01", "what exists": "None", "class": "-", "limitation": "Requires authorized read-only discovery"},
        {"area": "Customer runtime figures", "what exists": "None", "class": "-", "limitation": "Requires aggregated extracts from both sides"},
        {"area": "Finance-owner requirements", "what exists": "15 concepts drafted; none owner-approved", "class": "Draft", "limitation": "Owner decisions pending"},
    ])
    st.markdown("#### Limitations")
    st.markdown("- " + SYNTHETIC_NOTE + "\n"
                "- Product availability, entitlement and release compatibility for S/4HANA PCE 2023 SP01 are not evidenced.\n"
                "- Exact data-product schemas (CSN) have not been obtained for the Finance products in scope.\n"
                "- Field-name presence is never treated as business coverage.\n"
                "- No customer, tenant or authentication data is used or displayed on this site.")
    st.markdown("#### What would change the HOLD")
    st.markdown("1. Finance-owner decisions on ledger, currency, due date, buckets, clearing and special G/L.\n"
                "2. Authorized read-only metadata from the customer S/4HANA system.\n"
                "3. Product availability in the customer BDC tenant.\n"
                "4. Independent aggregated runtime extracts from S/4HANA and BDC for the same key date, reconciled within "
                "owner-approved tolerances.")
    st.markdown("#### Public sources")
    st.markdown("- SAP Help Portal, SAP S/4HANA 2023: *G/L Perspective of AR Aging Grid* query and cube "
                "([link](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/f296651f454c4284ade361292c633d69/bd558b1c30144565986f8c683a8516aa.html))\n"
                "- SAP Business Accelerator Hub, data products ([link](https://api.sap.com/dataproducts))")
    if INTERNAL:
        internal_routes.workbench_tools("Evidence & Limitations")

elif section == "Methodology":
    page_header("Methodology", "Seven steps from the existing Finance report to a defensible transition decision, with evidence "
                "gates between them.")
    st.table([
        {"step": "1. Discover", "question": "Which report does Finance actually use?", "output": "Report, query, CDS and table lineage",
         "gate": "Read-only, authorized source metadata"},
        {"step": "2. Understand", "question": "What does it really compute?", "output": "Business rules, configuration and custom logic",
         "gate": "Finance-owner confirmed requirements"},
        {"step": "3. Identify BDC products", "question": "Which SAP-managed products and content could serve it?",
         "output": "Candidate data products and Datasphere content", "gate": "Complete catalog capture; product identity verified"},
        {"step": "4. Map semantics", "question": "Do grain, ledger, dates, currency and buckets match?", "output": "Dimension-by-dimension comparison",
         "gate": "Exact product contract"},
        {"step": "5. Validate", "question": "Do edge cases behave the same?", "output": "Controlled scenarios (partial payments, credits, past key dates)",
         "gate": "Synthetic data clearly labelled"},
        {"step": "6. Reconcile", "question": "Do real results agree?", "output": "KPI reconciliation per measure and bucket",
         "gate": "Independent runtime extracts; identical context; owner tolerances"},
        {"step": "7. Recommend", "question": "Which route is justified?", "output": "One of the four outcomes below",
         "gate": "Traceable evidence for every criterion"},
    ])
    st.markdown("#### Possible outcomes")
    st.markdown("- **A. Reuse SAP-delivered BDC content** when products and delivered content reproduce the report's meaning and results.\n"
                "- **B. Extend SAP Datasphere modeling** when the products are right but calculations or attributes need extension.\n"
                "- **C. Build a customer-managed data product** when SAP-managed products cannot carry the required data, justified by evidence.\n"
                "- **D. Retain the existing report** when evidence or capabilities are insufficient for a safe transition.")
    st.markdown("#### Evidence classes")
    st.markdown("- **SAP documented reference**: public SAP documentation; never proof of a customer system.\n"
                "- **Public CSN sample**: published examples; never the current product contract.\n"
                "- **Exact product contract**: verified product schema with identity, version and hash.\n"
                "- **Live SAP metadata**: read-only metadata from a named system (trial or customer).\n"
                "- **Customer runtime evidence**: approved aggregated figures from the customer landscape.")
    st.markdown("#### Reconciliation rules")
    st.markdown("- Both sides must be independent datasets with identical company code, ledger, currency, key date, aging basis, "
                "filters and sign convention.\n- Tolerances are approved by the Finance owner before the run.\n"
                "- Synthetic data can reach SYNTHETIC_PASS only; PASS requires customer runtime extracts on both sides.")
    if INTERNAL:
        internal_routes.workbench_tools("Methodology")

st.divider()
st.caption("Independent assessment prototype, not affiliated with SAP. No SAP connection, customer data or authentication on this site. "
           + HOLD + ".")
st.caption(TRADEMARK)
