"""BDC Transition Agent Suite (v0.13) - Streamlit cockpit. SYNTHETIC data only, DEMO mode only.

The story is the delta: what the customer changed in standard SAP, how it was found, how it is solved and how the result is proven.
Five stages, three agents (see bdcwb.delta):
  1 Find the delta  2 Solution the delta   -> S/4HANA agent
  3 Datasphere activities                   -> BDC & Datasphere agent
  4 Compare and reconcile  5 End-to-end result -> Utility agent
Two-level topology: Home (ask the agents) -> spaces: Delta journey | Agents | Architecture & operations.
Everything shown derives from the persisted/cached result set produced by bdcwb.run; no figure is hardcoded.
Navigation changes only happen in callbacks (never by writing a widget's session key after it was instantiated).
"""
from __future__ import annotations

import json
import re

import streamlit as st

import suite_theme as T
from bdcwb import adapters, agents, arch, arch_diagrams as AD, delta, importer, landscape, lookup, ontology, sap_hub, status
from bdcwb.run import run_all

STAGES = delta.STAGES
STAGE_LABELS = [f"{s['id']} {s['name']}" for s in STAGES]
SCEN = {"A": "A - single S/4HANA system", "B": "B - multi-system with Central Finance"}
SPACES = ["Delta journey", "Find", "Ontology", "Agents", "Architecture & operations"]
START = ["All (objects and data products)", "S/4HANA object", "Data product"]
ONTO_VIEWS = ["How data flows", "How components are wired", "Concept model"]
HOME_TABS = ["How it works", "Delta journey", "Agents & architecture"]
AGENT_TABS = ["Ask the agents", "Agent catalog", "Technical options"]
ARCH_TABS = ["Live run", "Complete architecture", "Adapters", "Tool hosting", "Agent hosting", "Registry", "Selection criteria", "Decision brief", "Diagrams"]
RELEASE = "0.13.11"
FIND_DIRS = ["Process → data products", "Data product → processes", "SAP-published Finance catalog"]
SPACE_SLUGS = {"Delta journey": "delta-journey", "Find": "find", "Ontology": "ontology", "Agents": "agents", "Architecture & operations": "architecture"}
SPACE_BY_SLUG = {v: k for k, v in SPACE_SLUGS.items()}
INTENT_STAGE = {"ontology": 0, "product": 1, "delta": 1, "discovery": 1, "solution": 2, "datasphere": 3, "rules": 3, "recon": 4, "validation": 4, "full": 5, "readiness": 5, "write": 5}
AGENT_EXAMPLE = {"s4": 0, "bdc": 4, "utility": 5}
_KEEP = object()


@st.cache_data(show_spinner="Running the synthetic pipeline (Scenario A and B)...")
def load() -> dict:
    return run_all()


def diagram(html: str) -> None:
    st.markdown(html, unsafe_allow_html=True)


def _dep_graph(s: dict) -> str:
    d = s["dependencies"]
    nodes = [{"id": k, "label": k.split(":")[-1], "sub": f"{v.get('system', '')} - {v.get('type', '')}".strip(" -"), "kind": ("UNRESOLVED" if not v.get("resolved") else v.get("type", ""))}
             for k, v in d["nodes"].items()]
    return AD.layered_svg(nodes, [(e["from"], e["to"]) for e in d["edges"]], "Dependency graph", {"UNRESOLVED": "dg-box dg-bad", "QUERY": "dg-box dg-sel", "CUBE": "dg-box dg-sel"}, 190)[0]


def _concept_graph(fam: str) -> str:
    cs = [c for c in arch.concepts() if fam in ("all", c["family"]) or c["family"] == "shared"]
    ids = {c["id"] for c in cs}
    return AD.layered_svg([{"id": c["id"], "label": c["label"], "sub": c["kind"], "kind": c["kind"]} for c in cs],
                          [(a, b) for a, _, b in arch.relations() if a in ids and b in ids], "Concept model", {}, 190)[0]


def table(rows, max_height: int = 420) -> None:
    st.markdown(T.html_table(rows, max_height), unsafe_allow_html=True)


def badge(text: str, warn: bool = False) -> str:
    return T.badge(text, "warn" if warn else "")


def _agent(agent_id: str) -> dict:
    return next(a for a in agents.AGENTS if a["id"] == agent_id)


# ---------------------------------------------------------------------------------------------------- navigation
def _go(view: str = "space", space: str | None = None, stage: int | None = None, agents_tab: str | None = None, arch_tab: str | None = None,
        home_tab: str | None = None, find_dir: str | None = None) -> None:
    ss = st.session_state
    ss["nav_view"] = view
    if find_dir:
        ss["find_dir"] = find_dir
    if space:
        ss["tabs_space"] = space
    if stage:
        ss["tabs_stage"] = STAGE_LABELS[stage - 1]
    if agents_tab:
        ss["tabs_agents"] = agents_tab
    if arch_tab:
        ss["tabs_arch"] = arch_tab
    if home_tab:
        ss["tabs_home"] = home_tab


def _step(n: int) -> None:
    """Previous / next stage inside the journey."""
    cur = int(st.session_state.get("tabs_stage", STAGE_LABELS[0]).split()[0])
    st.session_state["tabs_stage"] = STAGE_LABELS[min(5, max(1, cur + n)) - 1]


def _effective(request: str, selected: str) -> tuple[str, str]:
    m = re.search(r"\bscenario\s+([AB])\b", request, re.I)
    if m:
        return m.group(1).upper(), "taken from the request"
    return selected, "from the selector"


def _run_plan() -> None:
    ss = st.session_state
    q = ss.get("ag_q_input", agents.EXAMPLES[0])
    scn, src = _effective(q, ss.get("ag_scn", "A"))
    ss["ag_run"] = agents.run_request(q, load(), scn)
    ss["ag_run_scn"] = (scn, src)
    _go("space", space="Agents", agents_tab="Ask the agents")


def _pick(example: str) -> None:
    st.session_state["ag_q_input"] = example
    _run_plan()


def _save_theme() -> None:
    st.session_state["theme_saved"] = st.session_state.get("ag_theme", T.DEFAULT_THEME)


def _select_agent(agent_id: str | None) -> None:
    st.session_state["ag_sel"] = agent_id


# ---------------------------------------------------------------------------------------------------- shell
def shell(mode: str) -> None:
    """Top shell bar. mode: home | space | old."""
    ss = st.session_state
    title = {"home": "My Home", "space": "BDC Transition Agent Cockpit", "old": "Old demo - v0.12 reporting analyzer"}[mode]
    crumb = {"home": "BDC transition agent suite / local demo", "space": "Home / BDC / agent cockpit", "old": "Home / old demo"}[mode]
    widths = {"home": [.5, 1.3, 3.6, 2.0, 1.5, 2.9, 2.0], "space": [.5, 1.3, 3.7, .1, 1.5, 2.6, 2.0, 3.0, 2.0], "old": [.5, 1.3, 5.3, 2.4]}[mode]
    with st.container(key="shell"):
        c = st.columns(widths, vertical_alignment="center")
        c[0].button("", icon=":material/home:", key="nav_home", on_click=_go, kwargs={"view": "home"}, help="My Home")
        with c[1].popover("Menu", icon=":material/apps:"):
            st.caption("BDC TRANSITION WORKSPACE")
            st.button("My Home", key="m_home", icon=":material/home:", on_click=_go, kwargs={"view": "home"}, width="stretch")
            for n, icon in ((1, "travel_explore"), (2, "construction"), (3, "hub"), (4, "balance"), (5, "flag")):
                st.button(f"{n} {STAGES[n - 1]['name']}", key=f"m_stage{n}", icon=f":material/{icon}:", on_click=_go,
                          kwargs={"view": "space", "space": "Delta journey", "stage": n}, width="stretch")
            st.button("Find: process to data product", key="m_find", icon=":material/manage_search:", on_click=_go,
                      kwargs={"view": "space", "space": "Find"}, width="stretch")
            st.button("Ontology: how data flows", key="m_onto", icon=":material/account_tree:", on_click=_go,
                      kwargs={"view": "space", "space": "Ontology"}, width="stretch")
            st.button("Ask the BDC agents", key="m_ask", icon=":material/smart_toy:", on_click=_go,
                      kwargs={"view": "space", "space": "Agents", "agents_tab": "Ask the agents"}, width="stretch")
            st.button("Live architecture", key="m_live", icon=":material/lan:", on_click=_go,
                      kwargs={"view": "space", "space": "Architecture & operations", "arch_tab": "Live run"}, width="stretch")
            st.button("Complete architecture", key="m_arch", icon=":material/schema:", on_click=_go,
                      kwargs={"view": "space", "space": "Architecture & operations", "arch_tab": "Complete architecture"}, width="stretch")
            st.divider()
            st.button("Old demo (v0.12 pages)", key="m_old", icon=":material/history:", on_click=_go, kwargs={"view": "old"}, width="stretch")
        c[2].markdown(f'<div class="ag-brand"><div class="ag-logo">B</div><div><div class="ag-crumb">{T.esc(crumb)}</div>'
                      f'<div class="ag-title">{T.esc(title)}</div></div></div>', unsafe_allow_html=True)
        if mode == "old":
            c[3].button("Open the Agent Suite", key="old_to_suite", type="primary", on_click=_go, kwargs={"view": "home"}, width="stretch")
            return
        saved = ss.get("theme_saved", T.DEFAULT_THEME)
        # c[3] is an empty spacer column that pushes the controls to the right edge; c[4] is the always-visible link to the old demo
        c[4].button("Old demo", icon=":material/history:", key="shell_old", on_click=_go, kwargs={"view": "old"}, help="The v0.12 analyzer pages, clubbed on one page")
        c[5].selectbox("Theme", list(T.THEMES), index=list(T.THEMES).index(saved) if saved in T.THEMES else 0, key="ag_theme", on_change=_save_theme)
        c[6].markdown(T.badge("SYNTHETIC - LOCAL DEMO"), unsafe_allow_html=True)
        if mode == "space":
            c[7].selectbox("Scenario", list(SCEN), format_func=lambda k_: SCEN[k_], key="ag_scn")
            c[8].checkbox("Technical details", key="ag_tech")


def render() -> None:
    res = load()
    ss = st.session_state
    view = ss.get("nav_view", "home")
    view = view if view in ("home", "space") else "home"
    ss["nav_view"] = view
    st.markdown(T.css(ss.get("theme_saved", T.DEFAULT_THEME)), unsafe_allow_html=True)
    shell(view)
    with st.container(key="page_body"):
        if view == "home":
            for k in ("space", "stage"):
                if k in st.query_params:
                    del st.query_params[k]
            _home(res)
        else:
            scn = ss.get("ag_scn", "A")
            s = res["scenarios"][scn]
            tech = bool(ss.get("ag_tech"))
            st.radio("Space", SPACES, horizontal=True, key="tabs_space", label_visibility="collapsed")
            st.query_params["space"] = SPACE_SLUGS[ss["tabs_space"]]
            if ss["tabs_space"] != "Delta journey" and "stage" in st.query_params:
                del st.query_params["stage"]
            _status_strip(res)
            {"Delta journey": _journey, "Find": _find, "Ontology": _ontology, "Agents": _agents, "Architecture & operations": _architecture}[ss["tabs_space"]](res, s, scn, tech)
        st.markdown(T.legal_html(), unsafe_allow_html=True)
    ev = status.load_evidence()
    st.markdown(T.footer(f" &middot; v{RELEASE} &middot; evidence recorded {T.esc(ev.get('recorded', 'n/a'))}"), unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------------- shared widgets
def _status_strip(res: dict) -> None:
    """Synthetic and live status stay separate and always visible."""
    x = res["status"]
    st.markdown('<div style="margin:.9rem 0 .2rem">' + T.badge("SYNTHETIC DATA - DEMO MODE - NO SAP CONNECTION", "ok") + " "
                + T.badge("LIVE SAP VALIDATION: " + x["LIVE_SAP_VALIDATION"], "warn") + " " + T.badge("LIVE BDC VALIDATION: " + x["LIVE_BDC_VALIDATION"], "warn") + " "
                + T.badge("FINANCE VALIDATION: " + x["FINANCE_VALIDATION"], "warn") + " "
                + T.badge("PUBLICATION AUTHORIZATION (live evidence): " + x["PUBLICATION_AUTHORIZATION"], "warn") + "</div>", unsafe_allow_html=True)


def _scn_select() -> None:
    st.selectbox("Scenario", list(SCEN), format_func=lambda k: SCEN[k], key="ag_scn")


def _ask_box(prefix: str) -> None:
    """Request row, example chips and routing line. Same widget parameters on Home and in the Agents space (state continuity)."""
    ss = st.session_state
    ss.setdefault("ag_q_input", agents.EXAMPLES[0])
    home = prefix == "h"
    cols = st.columns([1.6, 5, 1.2] if home else [5, 1.2], vertical_alignment="bottom")
    if home:
        with cols[0]:
            _scn_select()
    cols[-2].text_input("Your request", key="ag_q_input", label_visibility="collapsed")
    cols[-1].button("Run plan →", key="runplan" if home else "runplan2", type="primary", on_click=_run_plan, width="stretch")
    with st.container(key="chips" if home else "chips_ask"):
        chips = st.columns(len(agents.EXAMPLES))
        for i, ex in enumerate(agents.EXAMPLES):
            chips[i].button(ex, key=f"ex{i}" if home else f"ax{i}", on_click=_pick, args=(ex,))
    scn, src = _effective(ss["ag_q_input"], ss.get("ag_scn", "A"))
    ag = _agent(agents.route(ss["ag_q_input"])["agent"])
    agree = "selector and request agree" if scn == ss.get("ag_scn", "A") else "the request overrides the selector"
    st.markdown(f'<span class="ag-note">Effective scenario: <b>{scn}</b> &nbsp;{agree} &nbsp;</span><span class="ag-pill">Routed to the {T.esc(ag["name"])}</span>', unsafe_allow_html=True)


def _stage_kpis(res: dict, scn: str) -> list[str]:
    j = delta.journey(res, scn)
    d = j["delta"]
    rt = d["routes"]
    ext = sum(v for k, v in rt.items() if k.startswith("Extend"))
    new = sum(v for k, v in rt.items() if k.startswith("New backend"))
    dsp = sum(v for k, v in rt.items() if k.startswith("Solve in Datasphere"))
    return [f"{d['objects']} SAP objects compared; {d['no_delta']} no delta; {d['customizations']} customization(s)",
            f"{ext} extend the product; {new} new CDS view + customer-managed model; {dsp} solved in Datasphere",
            f"{len(j['plan']['replication_flows'])} replication flows; {len(j['plan']['harmonization']) + len(j['plan']['transformation'])} views; simulation {j['plan']['simulation']['sql']}",
            f"Levels: " + ", ".join(f"{k} {v}" for k, v in j["recon"].items() if v != "-") + f"; defects detected {j['defects']}",
            f"Gates {j['gates']} pass; live SAP / BDC / Finance validation HOLD"]


def _stage_cards(res: dict, scn: str, prefix: str) -> None:
    kp = _stage_kpis(res, scn)
    cols = st.columns(5)
    for i, stg in enumerate(STAGES):
        with cols[i]:
            with st.container(key=f"tile_{prefix}_s{stg['id']}"):
                st.markdown(f'<div class="ag-kicker">Stage {stg["id"]} &middot; {T.esc(_agent(stg["agent"])["name"])}</div>'
                            f'<h4 style="margin:.1rem 0 .25rem;font-size:1rem">{T.esc(stg["name"])}</h4>'
                            f'<div class="ag-note" style="min-height:3.6em">{T.esc(kp[i])}</div>', unsafe_allow_html=True)
                st.button("Open →", key=f"open_{prefix}_s{stg['id']}", on_click=_go, kwargs={"view": "space", "space": "Delta journey", "stage": stg["id"]})


# ---------------------------------------------------------------------------------------------------- Level 1: Home
def _home(res: dict) -> None:
    with st.container(key="home_body"):
        st.markdown('<div class="ag-kicker">BDC transition / the delta</div><div class="ag-h1">Ask the transition agents</div>'
                    '<div class="ag-lead">What did the customer change in standard SAP, how was it found, and what is the next step? Three agents answer from the '
                    'synthetic evidence; they compare the customer\'s SAP objects with the data products SAP delivers. The orchestrator plans, each agent calls typed tools, and people approve; nothing is written to SAP. The demo planner is deterministic so every answer is reproducible; an LLM planner plugs in behind the same validated tool contract, and read-only system adapters supply live evidence once access is authorized. Start from an S/4HANA object or from a data product.</div>',
                    unsafe_allow_html=True)
        _ask_box("h")
        e1, e2 = st.columns(2)
        e1.button("Process → data products: which products serve a business process?", key="h_find_pp", icon=":material/manage_search:", on_click=_go,
                  kwargs={"view": "space", "space": "Find", "find_dir": FIND_DIRS[0]}, width="stretch")
        e2.button("Data product → processes and backend delta: what changes if I use this product?", key="h_find_dp", icon=":material/swap_horiz:", on_click=_go,
                  kwargs={"view": "space", "space": "Find", "find_dir": FIND_DIRS[1]}, width="stretch")
        st.radio("Home tabs", HOME_TABS, horizontal=True, key="tabs_home", label_visibility="collapsed")
        tab = st.session_state["tabs_home"]
        scn = st.session_state.get("ag_scn", "A")
        if tab == "How it works":
            st.markdown(T.flow([(f"{s['id']} {s['name']}", _agent(s["agent"])["name"], s["question"]) for s in STAGES], selected=0), unsafe_allow_html=True)
            cols = st.columns(3)
            for col, a in zip(cols, agents.catalog_view()):
                col.markdown(T.card(f"{a['icon']} {a['name']}", f"Stages {', '.join(str(x) for x in a['stages'])}. {a['blurb']}"), unsafe_allow_html=True)
            st.markdown('<div class="ag-dashed"><b>Run it on your laptop</b><br><span class="ag-note">The code is public and synthetic-only. Python is needed.</span><br>'
                        '<code>git clone https://github.com/Iam-PrasadDeshpande/bdc-finance-reporting-analyzer</code><br>'
                        '<code>pip install -r requirements.txt &amp;&amp; streamlit run app.py</code></div>', unsafe_allow_html=True)
        elif tab == "Delta journey":
            _stage_cards(res, scn, "home")
        else:
            cols = st.columns(3)
            for col, a in zip(cols, agents.catalog_view()):
                col.markdown(T.card(f"{a['icon']} {a['name']}", f"{a['tool_count']} typed tools. Stages {', '.join(str(x) for x in a['stages'])}. {a['blurb']}"), unsafe_allow_html=True)
            b = st.columns(4)
            b[0].button("Ask the agents →", key="h_ask", on_click=_go, kwargs={"view": "space", "space": "Agents", "agents_tab": "Ask the agents"}, width="stretch")
            b[1].button("Agent catalog →", key="h_cat", on_click=_go, kwargs={"view": "space", "space": "Agents", "agents_tab": "Agent catalog"}, width="stretch")
            b[2].button("Live architecture →", key="h_live", on_click=_go,
                        kwargs={"view": "space", "space": "Architecture & operations", "arch_tab": "Live run"}, width="stretch")
            b[3].button("Complete architecture →", key="h_arch", on_click=_go,
                        kwargs={"view": "space", "space": "Architecture & operations", "arch_tab": "Complete architecture"}, width="stretch")
        _status_strip(res)
        o1, o2 = st.columns([6, 2], vertical_alignment="center")
        o1.markdown('<span class="ag-note">Looking for the earlier v0.12 analyzer (Vision &amp; Approach, AR Aging, Architecture, Evidence, Methodology)? '
                    'It is kept, unchanged, as one page.</span>', unsafe_allow_html=True)
        o2.button("Open the Old demo →", key="home_old", on_click=_go, kwargs={"view": "old"}, width="stretch")



# ---------------------------------------------------------------------------------------------------- Find: process <-> data product
def _fit_badge(fit: str) -> str:
    return T.badge(lookup.FIT[fit], "" if fit in ("COVERED_AS_IS",) else "warn")


def _find(res, s, scn, tech):
    ss = st.session_state
    st.markdown("##### Find the data products for a process, or the processes behind a data product")
    st.caption("The first two directions read the same delta register and catalog as the Delta journey, so the answers always agree with it. " + lookup.BADGE +
               ". The third shows what SAP itself publishes for Finance. " + sap_hub.BADGE + ".")
    st.radio("Direction", FIND_DIRS, horizontal=True, key="find_dir", label_visibility="collapsed")
    if ss["find_dir"] == FIND_DIRS[0]:
        _find_process(res, scn)
    elif ss["find_dir"] == FIND_DIRS[1]:
        _find_product(res, scn)
    else:
        _find_hub(res, scn)


def _find_process(res, scn):
    names = {k: v["name"] for k, v in lookup.PROCESSES.items()}
    st.selectbox("Business process", list(names), format_func=lambda k: names[k], key="find_proc")
    st.text_input("...or describe the process in your own words", key="find_proc_text", placeholder="for example: GR/IR, accounts payable, order to cash",
                  help="Matched against the process taxonomy only. A process that is not in it is reported as not found, never guessed.")
    typed = (st.session_state.get("find_proc_text") or "").strip()
    r = lookup.process_to_products(res, scn, typed or names[st.session_state["find_proc"]])
    if not r["found"]:
        st.warning(r["summary"])
        return
    c = r["counts"]
    m = st.columns(4)
    m[0].metric("Steps", len(r["steps"]))
    m[1].metric("Objects in scope", sum(c.values()))
    m[2].metric("SAP data products involved", len(r["products"]))
    m[3].metric("Need a delta or have no product", c["COVERED_WITH_DELTA"] + c["CANDIDATE_ONLY"] + c["NOT_ESTABLISHED"] + c["NO_PRODUCT"])
    st.markdown(_fit_badge(r["verdict"]) + f" &nbsp; <span class='ag-note'>{T.esc(r['name'])}, scenario {T.esc(scn)}</span>", unsafe_allow_html=True)
    st.markdown("##### Data products that serve this process")
    table([{"data product": p["product"], "evidence": p["evidence"], "serves steps": ", ".join(p["steps"]), "objects": p["objects"], "with a delta": p["with_delta"],
            "activation": p["activation"], "entitlement": p["entitlement"]} for p in r["products"]] or [{"data product": "none"}], 300)
    st.markdown("##### Step by step: product, fit and delta")
    table([{"step": x["step"], "object": x["object"], "system": x["system"], "data product / entity": (x["product"] + " / " + x["entity"]) if x["product"] != "-" else "-",
            "fit": lookup.FIT[x["fit"]], "delta": x["delta"], "solution": x["solution"]} for st_ in r["steps"] for x in st_["rows"]], 520)
    _hub_for_process(r["process"])
    st.caption("Fit: 'Not established' means the catalog does not declare that domain complete, so a missing product is not proof that SAP delivers none. "
               "'Candidate' means the product is unverified. Open the Delta journey to solve, plan, reconcile and see readiness.")
    b = st.columns(3)
    b[0].button("Open 1 Find the delta →", key="find_to_s1", on_click=_go, kwargs={"view": "space", "space": "Delta journey", "stage": 1}, width="stretch")
    b[1].button("Open 2 Solution the delta →", key="find_to_s2", on_click=_go, kwargs={"view": "space", "space": "Delta journey", "stage": 2}, width="stretch")
    b[2].button("Open the Ontology →", key="find_to_onto", on_click=_go, kwargs={"view": "space", "space": "Ontology"}, width="stretch")


def _hub_for_process(pid):
    h = sap_hub.for_process(pid)
    with st.expander(f"What SAP publishes for this process ({len(h['tagged'])} tagged products)", expanded=False):
        st.caption(h["note"] + " " + sap_hub.BADGE + ".")
        table([{"step": s["step"], "SAP-published products": ", ".join(f"{p['name']} v{p['version']}" for p in s["products"]) or "none in the snapshot"} for s in h["steps"]], 320)
        if h["unpublished_steps"]:
            st.caption("No SAP-published product carries the objects of: " + ", ".join(h["unpublished_steps"]) + ". That is a gap in the published list, not proof that SAP delivers nothing.")
        if h["tagged"]:
            st.caption("Tagged " + h["tag"] + ": " + ", ".join(p["name"] for p in h["tagged"][:40]) + (" ..." if len(h["tagged"]) > 40 else ""))


def _hub_for_product(pid):
    e = sap_hub.equivalents(pid)
    with st.expander("SAP-published equivalent", expanded=bool(e["products"])):
        if not e["products"]:
            st.caption(e["note"])
            return
        st.caption(e["note"] + "SAP's own process tags for it: " + (", ".join(e["processes"]) or "none") + ". " + sap_hub.BADGE + ".")
        table([{"SAP data product": p["name"], "version": p["version"], "ORD ID": p["ord_id"], "component": p["component"], "editions": ", ".join(p["editions"]),
                "S/4 object": ", ".join(p["s4_objects"]) or "-"} for p in e["products"]], 260)


def _find_hub(res, scn):
    s = sap_hub.stats()
    st.markdown(T.badge(sap_hub.BADGE, "warn"), unsafe_allow_html=True)
    m = st.columns(4)
    m[0].metric("Products on the SAP hub", s["hub_total"])
    m[1].metric("Tagged Finance", s["finance"])
    m[2].metric("With an S/4 business object", s["with_s4_object"])
    m[3].metric("SAP components responsible", s["components"])
    st.caption("Process tags SAP puts on Finance products: " + ", ".join(f"{k} {v}" for k, v in s["process_tags"].items()) + f"; {s['untagged']} carry no process tag. "
               "SAP states no 'Order to Cash' or AR/AP aging product for Finance in this list.")
    c = st.columns([2, 2, 3, 2])
    c[0].selectbox("SAP process tag", ["All", *sap_hub.PROCESS_TAGS, "(no process tag)"], key="find_hub_proc")
    c[1].selectbox("Application area (SAP component)", ["All", *sap_hub.areas()], key="find_hub_area")
    c[2].text_input("Search name, id, component or object", key="find_hub_text", placeholder="for example: journal, FI-GL, CompanyCode")
    c[3].checkbox("Include adjacent (not tagged Finance)", key="find_hub_adj", help="Procurement products SAP lists next to the Finance products, such as Purchase Order.")
    ss = st.session_state
    rows = sap_hub.browse(ss["find_hub_proc"], ss["find_hub_area"], ss["find_hub_text"], bool(ss.get("find_hub_adj")))
    st.markdown(f"##### {len(rows)} SAP data product(s)")
    table([{"data product": p["name"], "version": p["version"], "component": p["component"], "process tags": ", ".join(p["processes"]) or "-",
            "editions": ", ".join(p["editions"]) or "-", "S/4 object": ", ".join(p["s4_objects"][:3]) or "-", "ODM object": ", ".join(p["odm_objects"][:2]) or "-",
            "category": p["category"]} for p in rows] or [{"data product": "none match the filters"}], 380)
    if not rows:
        return
    names = [p["name"] for p in rows]
    if ss.get("find_hub_sel") not in names:
        ss["find_hub_sel"] = names[0]
    st.selectbox("Open one product", names, key="find_hub_sel")
    d = sap_hub.detail(res, scn, ss["find_hub_sel"])
    p = d["product"]
    st.markdown("##### " + T.esc(p["name"]) + " - published facts")
    table([{"ORD ID": p["ord_id"], "version": p["version"], "state": p["state"], "last modified": p["modified"], "component": p["component"], "category": p["category"],
            "editions": ", ".join(p["editions"]) or "-", "process tags": ", ".join(p["processes"]) or "-"}], 200)
    st.markdown("##### Backend standard anchor")
    table([{"S/4HANA business objects": ", ".join(p["s4_objects"]) or "none stated", "ODM business objects (cross-product model)": ", ".join(p["odm_objects"]) or "none stated"}], 200)
    st.markdown(f"##### Our delta register against this product (scenario {T.esc(scn)})")
    if d["rows"]:
        table([{"object": r["object"], "system": r["system"], "SAP object": r["sap_object"], "our catalog product": r["our product"], "delta": r["delta"],
                "solution": r["solution"], "customization": "yes" if r["customization"] else "-"} for r in d["rows"]], 380)
    else:
        st.info("No object in the synthetic scenario maps to this product, so there is nothing to compare yet. Fields, CDS views and lineage are not published, so a comparison "
                "with backend standard needs the customer's own inventory (import it in Delta journey, stage 1).")
    st.caption(d["summary"] + " SAP does not publish field lists on the hub, so differences are at object level; field-level differences come from the customer's inventory.")
    b = st.columns(2)
    b[0].button("Open 1 Find the delta →", key="findh_to_s1", on_click=_go, kwargs={"view": "space", "space": "Delta journey", "stage": 1}, width="stretch")
    b[1].button("Open 2 Solution the delta →", key="findh_to_s2", on_click=_go, kwargs={"view": "space", "space": "Delta journey", "stage": 2}, width="stretch")


def _find_product(res, scn):
    cat = {p["product_id"]: p["name"] for p in res["scenarios"][scn]["catalog"]["products"]}
    st.selectbox("SAP-delivered data product", list(cat), format_func=lambda k: f"{k} - {cat[k]}", key="find_prod")
    r = lookup.product_to_processes(res, scn, st.session_state["find_prod"])
    if not r["found"]:
        st.warning(r["summary"])
        return
    stt = r["state"]
    m = st.columns(4)
    m[0].metric("Processes served", len(r["processes"]))
    m[1].metric("Objects mapped", len(r["backend"]))
    m[2].metric("Objects that differ", sum(1 for b in r["backend"] if b["delta"] != "NO_DELTA"))
    m[3].metric("Customizations", sum(1 for b in r["backend"] if b["customization"]))
    st.markdown(T.badge(r["status"].replace("_", " "), "" if r["status"] == "COVERS_AS_IS" else "warn") + " &nbsp; " + T.badge(r["evidence"], "warn" if r["evidence"] != "SYNTHETIC_FIXTURE" else "") +
                f" &nbsp; <span class='ag-note'>{T.esc(r['name'])}, scenario {T.esc(scn)}</span>", unsafe_allow_html=True)
    st.markdown("##### Processes this product serves")
    table([{"process": x["name"], "steps": ", ".join(x["steps"]), "objects served": x["share"], "with a delta": x["with_delta"],
            "other products the process needs": ", ".join(x["other_products_needed"]) or "-"} for x in r["processes"]] or [{"process": "none in the taxonomy"}], 320)
    st.markdown("##### What differs in the backend if you use this product")
    table([{"object": b["object"], "system": b["system"], "SAP object": b["sap_object"], "product entity": b["entity"], "delta": b["delta"], "solution": b["solution"],
            "customization": "yes" if b["customization"] else "-"} for b in r["backend"]], 420)
    _hub_for_product(r["product"])
    st.markdown("##### Product state and extension options")
    table([{"activation": stt["activation"], "entitlement": stt["entitlement"], "installation": stt["installation"], "supported releases": ", ".join(stt["releases"]),
            "key-user extension": "yes" if stt["key_user_extension"] else "no", "developer extension": "yes" if stt["developer_extension"] else "no",
            "data-product extension": "yes" if stt["data_product_extension"] else "no"}], 200)
    st.caption("State values are synthetic. Whether a real product is activated or entitled in a tenant needs read-only access this build does not have. Nothing here activates or changes anything.")
    b = st.columns(3)
    b[0].button("Open 1 Find the delta →", key="findp_to_s1", on_click=_go, kwargs={"view": "space", "space": "Delta journey", "stage": 1}, width="stretch")
    b[1].button("Open 2 Solution the delta →", key="findp_to_s2", on_click=_go, kwargs={"view": "space", "space": "Delta journey", "stage": 2}, width="stretch")
    b[2].button("Open the Ontology →", key="findp_to_onto", on_click=_go, kwargs={"view": "space", "space": "Ontology"}, width="stretch")


# ---------------------------------------------------------------------------------------------------- Level 2: Agents space
def _agents(res, s, scn, tech):
    st.radio("Agents", AGENT_TABS, horizontal=True, key="tabs_agents", label_visibility="collapsed")
    tab = st.session_state["tabs_agents"]
    if tab == "Ask the agents":
        _ask_tab(res, tech)
    elif tab == "Agent catalog":
        _catalog_tab()
    else:
        _technical_tab(res, scn)


def _ask_tab(res, tech):
    ss = st.session_state
    with st.container(border=True):
        left, right = st.columns([2, 5])
        left.markdown('<div class="ag-kicker">Three agents &middot; orchestrated with MCP-style tool calls</div><h3 style="margin:.2rem 0 .4rem">Agent launchpad</h3><div style="margin:.1rem 0 .5rem">' + T.badge("AGENTIC DESIGN - DEMO PLANNER IS DETERMINISTIC, ADAPTERS NOT CONNECTED") + '</div>'
                      '<div class="ag-note">Ask about the delta in plain words, or pick an agent below to see what it does. The orchestrator plans and calls the agents\' typed tools; '
                      'the technical detail (orchestration graph, tool calls, execution options, tool catalog) is in Technical options.</div>', unsafe_allow_html=True)
        with right:
            _ask_box("a")
    r = ss.get("ag_run")
    if r:
        ag = _agent(r["route"]["agent"])
        scn_used, src = ss.get("ag_run_scn", ("A", "from the selector"))
        st.markdown(f'<span class="ag-pill">Handled by the {T.esc(ag["name"])}</span>', unsafe_allow_html=True)
        if r["refusal"]:
            st.markdown(f'<div class="ag-status warn"><b>{T.esc(ag["name"])}</b> &nbsp;Request refused - draft only.</div>', unsafe_allow_html=True)
            st.warning(r["refusal"])
        else:
            st.markdown(f'<div class="ag-status"><b>{T.esc(ag["name"])}</b> &nbsp;Plan complete.</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="ag-note">Your request: <b>&ldquo;{T.esc(r["request"])}&rdquo;</b></div><div class="ag-note" style="margin:.35rem 0 .6rem">'
                    f'Plan scenario: <b>{T.esc(scn_used)}</b> &middot; {T.esc(src)}</div>', unsafe_allow_html=True)
        if r.get("notice"):
            st.info(r["notice"])
        found = " ".join(t["summary"].rstrip(".") + "." for t in r["trace"][:3])
        used = sorted({t["agent"] for t in r["trace"]})
        st.markdown(f'<div class="ag-panel"><div class="ag-kicker">What the agents found</div>{T.esc(found)}<br>'
                    f'<b>The orchestrator planned {len(r["trace"])} tool call(s) across {len(used)} agent(s):</b> {T.esc(", ".join(used))}. '
                    f'No SAP write was made; a person decides on any proposal.</div>', unsafe_allow_html=True)
        stage = INTENT_STAGE.get(r["route"]["intent"], 1)
        st.markdown('<div class="ag-panel" style="margin-bottom:.3rem"><div class="ag-kicker">Full output of this run</div></div>', unsafe_allow_html=True)
        b1, b2, _ = st.columns([2.6, 2.4, 4])
        if stage == 0:
            b1.button("Open the Ontology →", key="open_app", type="primary", on_click=_go, kwargs={"view": "space", "space": "Ontology"}, width="stretch")
        else:
            b1.button(f"Open stage {stage}: {STAGES[stage - 1]['name']} →", key="open_app", type="primary", on_click=_go,
                      kwargs={"view": "space", "space": "Delta journey", "stage": stage}, width="stretch")
        b2.button("Open the detailed trace →", key="open_trace", on_click=_go, kwargs={"view": "space", "space": "Agents", "agents_tab": "Technical options"}, width="stretch")
        table([{"#": t["step"], "agent": t["agent"], "tool": t["tool"], "authority": t["authority"], "status": t["status"], "result": t["summary"]} for t in r["trace"]], 760)
        st.markdown('<div class="ag-note"><b>Layers reached:</b> ' + " &rarr; ".join(T.esc(x) for x in r["layers_reached"]) + "</div>", unsafe_allow_html=True)
        if r["approvals_needed"]:
            st.info("Approvals needed from people (nothing proceeds without them): " + "; ".join(r["approvals_needed"]))
        if tech:
            with st.expander("Execution trace (technical)"):
                st.json([{k: v for k, v in t.items() if k != "data"} for t in r["trace"]])
    _agent_tiles()


def _agent_tiles():
    ss = st.session_state
    sel = ss.get("ag_sel")
    cv = agents.catalog_view()
    if sel:
        a = next((x for x in cv if x["id"] == sel), None)
        if a:
            tools = [t for t in agents.tool_catalog() if t["agent"] == a["name"]]
            st.markdown(f'<div class="ag-panel"><div class="ag-kicker">{T.esc(a["authority_label"])} &middot; stages {", ".join(str(x) for x in a["stages"])}</div>'
                        f'<h3 style="margin:.1rem 0 .3rem">{T.esc(a["name"])}</h3>{T.esc(a["blurb"])}</div>', unsafe_allow_html=True)
            table([{"tool": t["tool"], "authority": t["authority"], "layer": t["layer"], "description": t["description"]} for t in tools], 420)
            c1, c2, _ = st.columns([2.4, 1.2, 5])
            c1.button("Try a request for this agent →", key="agent_try", on_click=_pick, args=(agents.EXAMPLES[AGENT_EXAMPLE[a["id"]]],), width="stretch")
            c2.button("Close", key="agent_close", on_click=_select_agent, args=(None,), width="stretch")
    st.markdown('<div class="ag-kicker" style="margin:1rem 0 .35rem">The three agents</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    for col, a in zip(cols, cv):
        with col:
            with st.container(key=f"tile_ag_{a['id']}"):
                st.markdown(f'<div class="ag-kicker">{T.esc(a["icon"])} Stages {", ".join(str(x) for x in a["stages"])}</div><h4 style="margin:.1rem 0 .25rem;font-size:1.05rem">{T.esc(a["name"])}</h4>'
                            f'<div class="ag-note" style="min-height:5.2em">{T.esc(a["blurb"])}</div>'
                            f'<span class="ag-tag">{T.esc(a["authority_label"])}</span><span class="ag-tag">{a["tool_count"]} tool(s)</span>', unsafe_allow_html=True)
                st.button("What does it do? →", key=f"sel_{a['id']}", on_click=_select_agent, args=(a["id"],))


def _catalog_tab():
    cv = agents.catalog_view()
    st.markdown(f'<div class="ag-note">{len(cv)} agents and {len(agents.TOOLS)} typed tools. Authority classes: read &middot; read (simulated) &middot; read + local draft &middot; draft only. '
                'No agent can write to SAP, activate, transport, deploy or publish.</div>', unsafe_allow_html=True)
    pick = st.radio("Agent", ["All"] + [a["name"] for a in cv], horizontal=True, key="ag_fam")
    rows = []
    for a in cv:
        if pick in ("All", a["name"]):
            rows += [{"agent": a["name"], "stage": ", ".join(a["stage_names"]) or "all stages", "tool": t["tool"], "authority": t["authority"], "does": t["description"]}
                     for t in agents.tool_catalog() if t["agent"] == a["name"]]
    table(rows, 600)


def _technical_tab(res, scn):
    ss = st.session_state
    r = ss.get("ag_run") or agents.run_request(agents.EXAMPLES[0], res, scn)
    st.markdown('<div class="ag-kicker">Orchestration graph (last run)</div>', unsafe_allow_html=True)
    ev = arch.live_events(r)
    diagram(AD.sequence_svg(ev, len(ev))[0])
    st.markdown('<div class="ag-kicker" style="margin-top:.8rem">MCP-style tool calls (last run)</div>', unsafe_allow_html=True)
    table([{"#": t["step"], "agent": t["agent"], "tool": t["tool"], "authority": t["authority"], "args": t["args"], "status": t["status"]} for t in r["trace"]], 300)
    st.markdown('<div class="ag-kicker" style="margin-top:.8rem">Execution options</div>', unsafe_allow_html=True)
    s = res["scenarios"][scn]
    rows = []
    for mode, plan in s["plan"].items():
        counts: dict[str, int] = {}
        for p in plan:
            counts[p["state"]] = counts.get(p["state"], 0) + 1
        rows.append({"mode": mode, "steps": len(plan), "states": counts, "meaning": {"DEMO": "Synthetic only (default).", "CONNECTED_READ_ONLY": "Authorized reads only; no interface configured, so reads are BLOCKED.",
                                                                                    "CONTROLLED_EXECUTION": "Needs explicit authorization and a verified executor; none exists in this build."}[mode]})
    table(rows, 240)
    st.markdown('<div class="ag-kicker" style="margin-top:.8rem">Planner contract (where an LLM planner plugs in)</div>', unsafe_allow_html=True)
    st.caption(f"Active planner: {agents.PLANNERS[agents.ACTIVE_PLANNER].name}. No LLM is configured or called.")
    table([{"part": k, "rule": v} for k, v in agents.PLANNER_CONTRACT], 320)
    st.markdown('<div class="ag-kicker" style="margin-top:.8rem">Tool catalog (MCP-style, typed)</div>', unsafe_allow_html=True)
    table(agents.tool_catalog(), 460)


# ---------------------------------------------------------------------------------------------------- Level 2: Delta journey
def _journey(res, s, scn, tech):
    ss = st.session_state
    st.radio("Stage", STAGE_LABELS, horizontal=True, key="tabs_stage", label_visibility="collapsed")
    n = int(ss["tabs_stage"].split()[0])
    st.query_params["stage"] = str(n)
    stg = STAGES[n - 1]
    lead, sup = _agent(stg["agent"]), _agent(stg["support"])
    kp = _stage_kpis(res, scn)[n - 1]
    st.markdown(f'<div class="ag-panel"><div class="ag-kicker">Stage {n} of 5 &middot; Lead: {T.esc(lead["name"])} &middot; Supported by: {T.esc(sup["name"])} &middot; Scenario {T.esc(scn)}</div>'
                f'<h2 style="margin:.1rem 0 .3rem">{T.esc(stg["name"])}</h2><div>{T.esc(stg["question"])}</div></div>', unsafe_allow_html=True)
    c1, c2 = st.columns([3, 2])
    c1.markdown('<div class="ag-kicker">How it is done</div>' + "<ol style='margin:.3rem 0 .6rem 1.1rem;padding:0;font-size:.86rem;line-height:1.5'>" +
                "".join(f"<li>{T.esc(x)}</li>" for x in stg["how"]) + "</ol>", unsafe_allow_html=True)
    c2.markdown(f'<div class="ag-kicker">What you get</div><div style="font-size:.86rem;margin:.3rem 0">{T.esc(stg["output"])}</div>'
                f'<div class="ag-kicker" style="margin-top:.6rem">This scenario</div><div style="font-size:.86rem;margin:.3rem 0"><b>{T.esc(kp)}</b></div>', unsafe_allow_html=True)
    {1: _stage1, 2: _stage2, 3: _stage3, 4: _stage4, 5: _stage5}[n](res, s, scn, tech)
    b1, b2, _ = st.columns([1.4, 1.4, 6])
    if n > 1:
        b1.button(f"← Stage {n - 1}", key="stage_prev", on_click=_step, args=(-1,), width="stretch")
    if n < 5:
        b2.button(f"Stage {n + 1} →", key="stage_next", on_click=_step, args=(1,), width="stretch", type="primary")


def _more(title: str):
    return st.expander(title)


def _stage1(res, s, scn, tech):
    rows = delta.register(s)
    sm = delta.summary(s)
    m = st.columns(5)
    m[0].metric("SAP objects compared", sm["objects"])
    m[1].metric("No delta", sm["no_delta"])
    m[2].metric("Customizations in standard SAP", sm["customizations"])
    m[3].metric("Business-rule differences", sm["rule_differences"])
    m[4].metric("Product coverage gaps", sm["coverage_gaps"])
    st.radio("Start from", START, horizontal=True, key="ag_start")
    st.caption("Start from an S/4HANA object to see what the customer changed and which delivered product covers it; start from a data product when reporting is built on data products "
               "and you want to drive one product through solution, Datasphere, reconciliation and readiness. 'All' shows both.")
    start = st.session_state["ag_start"]
    if start != START[2]:
        _delta_by_object(rows)
    if start != START[1]:
        _delta_by_product(res, scn)
    if st.toggle("Run the delta on your own exports (import-assisted, no connection needed)", key="ag_show_import"):
        _import_panel()
    with st.expander("What the delta types mean"):
        table([{"delta": k, "label": v[0], "meaning": v[1]} for k, v in delta.DELTA_TYPES.items()], 380)
    with st.expander("Customizations found (custom fields, customer objects, custom logic)"):
        _customizations(s, tech)
    # heavy detail views load on request: a collapsed expander still renders all of its tables in the browser
    if st.toggle("Show the comparison with the SAP data products (16 dimensions) and the catalog", key="ag_show_compare"):
        _a6(res, s, tech)
        st.markdown("**SAP data-product catalog (synthetic snapshot)**")
        _a5(res, s, tech)
    if st.toggle("Show SAP objects, systems and dependencies", key="ag_show_objects"):
        _a2(res, s, tech)
        _a3(res, s, tech)
        _a4(res, s, tech)


def _use_import_example() -> None:
    st.session_state["imp_use_example"] = True


def _import_panel() -> None:
    st.markdown("##### Delta from your own exports")
    st.caption("The same delta engine, on two files you supply instead of the synthetic fixtures: an extension inventory (what your S/4HANA objects contain, custom fields flagged) and a "
               "data-product catalog export (what SAP delivers). Files are read in memory, compared and discarded; nothing is connected, stored or written. Imported evidence stays "
               "CUSTOMER_PROVIDED, and catalog completeness is UNKNOWN unless your file declares it. Besides missing fields it finds extensions the product carries in a degraded form "
               "(wrong type, empty business name, lost currency or unit reference).")
    c = st.columns(2)
    c[0].download_button("Download example inventory (JSON)", json.dumps(importer.EXAMPLE_INVENTORY, indent=1), "example_inventory.json", "application/json", key="imp_dl_inv", width="stretch")
    c[1].download_button("Download example catalog export (JSON)", json.dumps(importer.EXAMPLE_CATALOG, indent=1), "example_catalog.json", "application/json", key="imp_dl_cat", width="stretch")
    f1 = st.file_uploader("Extension inventory (JSON, schema bdc-delta-inventory/1)", type=["json"], key="imp_inv")
    f2 = st.file_uploader("Data-product catalog export (JSON, schema bdc-delta-catalog/1)", type=["json"], key="imp_cat")
    st.button("Use the synthetic example files", key="imp_ex", on_click=_use_import_example)
    if f1 is not None and f2 is not None:
        out = _cached_import(f1.getvalue(), f2.getvalue())
    elif st.session_state.get("imp_use_example"):
        out = importer.run(importer.EXAMPLE_INVENTORY, importer.EXAMPLE_CATALOG, example=True)
    else:
        st.info("Upload both files, or use the synthetic example files to see the format and the result.")
        return
    if not out["ok"]:
        st.error("The files were not accepted. Nothing was compared.")
        table([{"problem": e} for e in out["errors"][:40]], 300)
        return
    sm = out["summary"]
    m = st.columns(3)
    m[0].metric("Objects compared", sm["objects"])
    m[1].metric("With customizations", sm["with_customization"])
    m[2].metric("Degraded in the product", sm["with_fidelity_findings"])
    table([{"object": r["object"], "delivered product": r["product"], "delta": r["delta"], "customization": r["customization"],
            "degraded in the product": "; ".join(r["fidelity"]) or "-", "how it was found": r["how_found"], "next step": r["route"], "evidence": r["evidence"]} for r in out["rows"]], 520)
    st.caption(out["note"])


def _delta_by_object(rows):
    st.markdown("##### Delta register (from the S/4HANA object)")
    st.caption("One row per SAP object, compared with the data product SAP delivers. A customization is a customer field or object found by the checks listed under "
               "'Customizations found'; a coverage gap is where the delivered product itself is narrower than the SAP object. Detection is limited to those checks.")
    flt = st.selectbox("Show", ["All rows", "Customizations only", "Any delta (hide 'no delta')", "No delta"], key="ag_delta_filter")
    keep = {"All rows": lambda r: True, "Customizations only": lambda r: r["kind"] == "Customization", "Any delta (hide 'no delta')": lambda r: r["delta_type"] != "NO_DELTA",
            "No delta": lambda r: r["delta_type"] == "NO_DELTA"}[flt]
    shown = [r for r in rows if keep(r)]
    table([{"SAP object": r["label"], "system": r["system"], "SAP-delivered data product": r["product"], "delta": r["delta_type"], "customization": r["customization"],
            "how it was found": r["how_found"], "next step": r["route"]} for r in shown], 560)
    if shown:
        opts = [f"{r['label']} - {r['sap_object']}" for r in shown]
        pick = st.selectbox("Open one delta", opts, key="ag_delta_pick")
        r = shown[opts.index(pick)] if pick in opts else shown[0]
        st.markdown(f'<div class="ag-panel"><div class="ag-kicker">{T.esc(r["kind"])} &middot; {T.esc(delta.DELTA_TYPES[r["delta_type"]][0])}</div>'
                    f'<h3 style="margin:.1rem 0 .3rem">{T.esc(r["label"])} <span class="ag-note">{T.esc(r["sap_object"])}</span></h3>'
                    f'<b>What it is:</b> {T.esc(delta.DELTA_TYPES[r["delta_type"]][1])}<br><b>Compared with:</b> {T.esc(r["product"])} (catalog state {T.esc(r["catalog_state"])}; coverage {T.esc(r["coverage"])})<br>'
                    f'<b>How it was found:</b> {T.esc(r["how_found"])}<br>' + (f'<b>Also:</b> {T.esc("; ".join(r["notes"]))}<br>' if r["notes"] else "") +
                    f'<b>Next step:</b> {T.esc(r["route"])} - {T.esc(r["next_step"])}' + (f'<br><b>Approvals:</b> {T.esc(", ".join(r["approvals"]))}' if r["approvals"] else "") + '</div>', unsafe_allow_html=True)


def _delta_by_product(res, scn):
    pv = ontology.product_view(res, scn)
    prods = pv["products"]
    st.markdown("##### Delta by data product (start from the SAP-delivered product)")
    st.caption("Reporting is built on data products, so this view starts there: for each delivered product, which customer objects map to it, what differs, and how far it is from an "
               "authorized deployment request. Evidence class is shown because a product that is not verified cannot be relied on.")
    table([{"data product": pid, "name": p["name"], "version": p["version"], "evidence class": p["evidence"], "status": p["status"], "objects mapped": p["counts"]["objects"],
            "no delta": p["counts"]["no_delta"], "customizations": p["counts"]["customizations"], "rule differences": p["counts"]["rule_differences"],
            "coverage gaps": p["counts"]["coverage_gaps"], "solution routes": p["stage2"], "readiness": p["readiness"]} for pid, p in prods.items()], 460)
    if pv["unmapped"]:
        st.markdown(f"**{len(pv['unmapped'])} object(s) have no delivered product, or one that is not verified** - they cannot be driven from a product:")
        table([{"SAP object": r["label"], "system": r["system"], "delta": r["delta_type"], "next step": r["route"]} for r in pv["unmapped"]], 300)
    pid = st.selectbox("Drive one data product through the journey", list(prods), key="ag_prod_pick", format_func=lambda k: f"{k} - {prods[k]['name']}")
    _product_journey(prods[pid])


def _product_journey(p):
    st.markdown(T.flow([("1 Find the delta", p["stage1"], f"entities used: {', '.join(p['entities_used']) or 'none'}; unused: {', '.join(p['entities_unused']) or 'none'}"),
                        ("2 Solution", p["stage2"], ("creates: " + "; ".join(x.split(" (")[0] for x in p["created"][:3])) if p["created"] else "nothing new is created"),
                        ("3 Datasphere", f"acquisition: {p['stage3']}", f"views: {', '.join(p['views']) or 'none'}; lands in: {', '.join(p['targets']) or '-'}"),
                        ("4 Compare and reconcile", f"analytic models: {', '.join(p['models']) or 'none'}", f"scenario-level reconciliation: {', '.join(p['proof']) or 'not yet'}"),
                        ("5 Result", p["readiness"].replace("_", " "), p["next"])], selected=4), unsafe_allow_html=True)
    table([{"SAP object": r["label"], "system": r["system"], "entity": r["product"].split(" / ")[-1], "delta": r["delta_type"], "customization": r["customization"], "next step": r["route"]}
           for r in p["objects"]] or [{"SAP object": "none mapped"}], 300)
    st.caption("Deployment itself needs a separate, explicit authorization and a verified executor; neither exists in this build. Readiness here means the synthetic evidence is complete for an authorization request.")


def _customizations(s, tech):
    c = delta.customizations(s)
    st.markdown("**How customizations are found:** custom fields are fields marked custom in the discovered object metadata; customer objects are objects in the customer namespace in the "
                "report's dependency chain; custom logic is detected by a lexical scan of source (category A normalised, B needs review, C explicit rules).")
    st.markdown("**Custom fields on standard objects**")
    table(c["fields"] or [{"object": "none"}], 220)
    st.markdown("**Customer-created objects**")
    table(c["objects"] or [{"object": "none"}], 200)
    st.markdown("**What is detected, and what is not**")
    st.markdown("Detected:\n" + "\n".join(f"- {x}" for x in delta.DETECTION_SCOPE["detected"]) + "\n\nNot detected (needs authorized read-only metadata and review):\n" + "\n".join(f"- {x}" for x in delta.DETECTION_SCOPE["not_detected"]))
    st.markdown(f"**Custom-logic markers:** {len(c['logic_A'])} normalised item(s) (category A), {len(c['logic_B'])} marker(s) needing review (category B: {c['logic_B_kinds']}), "
                f"{len(c['logic_C'])} explicit rule(s) (category C). {c['note']}")


def _stage2(res, s, scn, tech):
    rows = [r for r in delta.register(s) if r["decision"] != "-"]
    sm = delta.summary(s)
    lin = {x["requirement"]: x for x in ontology.build(res, scn)["lineage"]}
    st.markdown(T.flow([("Extend the SAP product", "key-user or data-product extension", "Only when the missing fields are eligible custom attributes and the product supports extension."),
                        ("Create a new backend CDS view + customer-managed data model", "extraction view, product contract, Datasphere target", "When the structure differs (key, grain, relationships, extraction) or no SAP product exists. Generated as templates."),
                        ("Solve in Datasphere", "approved rule or enrichment", "When the data is right but the meaning or authorization needs a rule.")], selected=1), unsafe_allow_html=True)
    cols = st.columns(max(1, len(sm["routes"])))
    for col, (route, n) in zip(cols, sorted(sm["routes"].items(), key=lambda kv: -kv[1])):
        col.markdown(T.card(route, f"{n} object(s)"), unsafe_allow_html=True)
    st.markdown("##### Solution per delta and what gets created")
    table([{"SAP object": r["label"], "delta": r["delta_type"], "solution route": r["route"],
            "what gets created": "; ".join(x.split(" (")[0] for x in lin[r["requirement"]]["creates"][:3]) + (f" (+{len(lin[r['requirement']]['creates']) - 3} more)" if len(lin[r["requirement"]]["creates"]) > 3 else ""),
            "approvals needed": ", ".join(r["approvals"]) or "-"} for r in rows if r["requirement"] in lin], 560)
    st.caption("Extending is one route among several. A new backend CDS view and customer-managed data model is created when the delta is structural. "
               "Everything generated is a template: never activated, never transported.")
    with st.expander("Generated files of a new backend CDS view and customer-managed data model"):
        _a8(res, s, tech)
    with st.expander("Decision detail, implementation steps and blocked requests"):
        _a7(res, s, tech)


def _stage3(res, s, scn, tech):
    p = delta.dsp_plan(s)
    sem, sim = p["semantic"], p["simulation"]
    m = st.columns(5)
    m[0].metric("Replication flows", len(p["replication_flows"]))
    m[1].metric("Harmonization views", len(p["harmonization"]))
    m[2].metric("Transformation views", len(p["transformation"]))
    m[3].metric("Facts / dimensions", f"{len(sem['facts'])} / {len(sem['dimensions'])}")
    m[4].metric("Analytic models", len(sem["analytic_models"]))
    st.markdown("##### Replication flows and acquisition")
    st.caption("Acquisition types: " + ", ".join(f"{k} {v}" for k, v in sorted(p["acq_types"].items())) + ". Replication flows are planned for customer-managed products; none is deployed.")
    table([{k: v for k, v in a.items() if k in ("requirement", "type", "replication_flow", "note")} for a in p["replication_flows"]] or [{"requirement": "none"}], 260)
    st.markdown("##### Harmonization and transformation")
    table([{"view": v["view"], "adds": v.get("adds", "")} for v in p["harmonization"]] + [{"view": v["view"], "adds": "transformation"} for v in p["transformation"]], 300)
    st.markdown("##### Semantic model")
    table([{"fact": f["name"], "grain": f["grain"], "measures": ", ".join(f["measures"]), "dimensions": ", ".join(f["dims"])} for f in sem["facts"]], 300)
    st.markdown("##### Offline simulation (nothing is deployed to Datasphere)")
    st.markdown(f"Grain check **{sim['grain']}** &middot; SQL functional check **{sim['sql']}** ({sim['mode']})", unsafe_allow_html=True)
    fo = sim["fan_out"]
    st.warning(f"Fan-out guard: a naive fact-to-fact join would report PO value {fo['naive_join_po_value']:,.2f} instead of {fo['correct_po_value']:,.2f}.")
    with st.expander("Business rules (AI can propose, never approve)"):
        _a9(res, s, tech)
    if st.toggle("Show all five Datasphere model layers", key="ag_show_layers"):
        _a10(res, s, tech)


def _stage4(res, s, scn, tech):
    st.markdown("##### Technical comparison (metadata level, offline)")
    _a12(res, s, tech)
    st.markdown("##### Data-level comparison (reconciliation of results)")
    _a13(res, s, tech)


def _stage5(res, s, scn, tech):
    j = delta.journey(res, scn)
    d = j["delta"]
    st.markdown("##### End-to-end result (synthetic)")
    table([{"stage": "1 Find the delta", "result": f"{d['objects']} SAP objects compared with SAP-delivered products; {d['no_delta']} no delta; {d['customizations']} customization(s); {d['rule_differences']} rule difference(s); {d['coverage_gaps']} coverage gap(s)"},
           {"stage": "2 Solution the delta", "result": "; ".join(f"{k}: {v}" for k, v in sorted(d["routes"].items(), key=lambda kv: -kv[1])) + f"; {j['packages']} customer-managed package template(s) generated"},
           {"stage": "3 Datasphere activities", "result": f"{len(j['plan']['replication_flows'])} replication flow(s), {len(j['plan']['harmonization']) + len(j['plan']['transformation'])} views, offline simulation {j['plan']['simulation']['sql']}"},
           {"stage": "4 Compare and reconcile", "result": ", ".join(f"{k} {v}" for k, v in j["recon"].items() if v != "-") + f"; golden transaction {j['golden_rows']}; injected defects detected {j['defects']}"},
           {"stage": "5 Gates and status", "result": f"{j['gates']} gates pass ({j['release']}); live SAP, BDC and Finance validation HOLD"}], 360)
    st.markdown("##### Next steps (need people and access this build does not have)")
    st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(j["next_steps"], 1)))
    st.info("Synthetic success shows the method works and can explain the delta to the SAP team. It is not evidence about any real system.")
    st.button("Open the Ontology: how data flows and how the components are wired →", key="stage5_onto", on_click=_go, kwargs={"view": "space", "space": "Ontology"})
    with st.expander("Execution plan by mode (writes stay blocked)"):
        _a11(res, s, tech)
    with st.expander("Status dimensions and acceptance gates G01-G15"):
        _a14(res, s, tech)


def _a2(res, s, tech):
    table([{"system": k, **v} for k, v in s["topology"]["systems"].items()])
    if s["topology"]["fi_authority"]:
        st.markdown("**FI source of truth per company code** (exactly one; source and replicated FI are never summed)")
        table([{"system|company code": k, "authoritative FI source": v} for k, v in s["topology"]["fi_authority"].items()])
    st.caption("Synthetic system identifiers. Logical system, client, release and duplicate document numbers across systems are part of the data.")


def _a3(res, s, tech):
    st.markdown("**Procure-to-Pay reference inventory (20 logical groups)** - discovery reference candidates; released CDS views and extraction mechanisms must come from source metadata.")
    table(s["inventory"])
    sysf = st.selectbox("System", ["(all)"] + list(s["topology"]["systems"]), key="ag_objsys")
    objs = [o for o in s["objects"] if sysf == "(all)" or o["system"] == sysf]
    st.caption(f"{len(objs)} discovered objects")
    table([{k: o[k] for k in ("id", "obj_type", "release", "api_state", "domain", "grain", "evidence")} | {"delta": o["extraction"]["delta"], "mechanism": o["extraction"]["mechanism"]} for o in objs], 520)


def _a4(res, s, tech):
    d = s["dependencies"]
    st.write(f"{len(d['nodes'])} nodes, {len(d['edges'])} edges; cycles: {len(d['cycles'])}; truncated: {d['truncated']}. Red nodes are **unresolved** (reported, never guessed).")
    if st.checkbox("Draw the dependency graph (renders in the browser; may take a moment)", key="ag_dep_graph"):
        diagram(_dep_graph(s))
    st.markdown("**Unresolved objects**")
    table(d["unresolved"] or [{"object": "none"}])


def _a5(res, s, tech):
    c = s["catalog"]
    st.write(f"Snapshot **{c['snapshot']}** (synthetic fixture). Domain completeness declared: {c['domain_completeness']}. A product missing from an accessible catalog is UNKNOWN unless completeness is established.")
    table([{k: p[k] for k in ("product_id", "name", "version", "evidence", "supported_releases", "activation", "entitlement", "installation", "consumption")} | {"entities": ", ".join(p["entities"])} for p in c["products"]], 520)
    st.caption("Published availability, tenant availability, entitlement, compatibility, activation, installation and consumption are distinct and never implied by each other.")


def _a6(res, s, tech):
    cov = s["coverage"]
    st.write(f"Field coverage over comparable requirements: **{cov['numerator']}/{cov['denominator']}** ({cov['percent']}%); unassessed items: {cov['unassessed']}. Not AI confidence.")
    table([{"requirement": a["requirement"], "object": a["label"], "primary gap": a["primary_gap"], "all gaps": ", ".join(g["class"] for g in a["gaps"]),
            "covered": a["coverage"]["numerator"], "comparable": a["coverage"]["denominator"], "unassessed": len(a["coverage"]["unassessed"]), "state": a["catalog_state"]} for a in s["analysis"]])
    rid = st.selectbox("Requirement detail", [a["requirement"] for a in s["analysis"]], key="ag_req")
    a = next(x for x in s["analysis"] if x["requirement"] == rid)
    for c in a["candidates"]:
        st.markdown(f"**Candidate {c['product']} / {c['entity']}**")
        table([{"dimension": k, "status": v["status"], "detail": json.dumps(v["detail"], default=str)[:160]} for k, v in c["dimensions"].items()], 520)
    if not a["candidates"]:
        st.info(a["gaps"][0]["detail"])


def _a7(res, s, tech):
    table([{"requirement": d["requirement"], "decision": d["decision"], "reason": d["reason"][:140], "secondary": ", ".join(d["secondary_findings"])} for d in s["decisions"]])
    d = st.selectbox("Decision detail", [d["requirement"] for d in s["decisions"]], key="ag_dec")
    x = next(i for i in s["decisions"] if i["requirement"] == d)
    st.markdown(f"**{x['decision']}** - {x['reason']}")
    st.write("Implementation steps:", x["implementation_steps"])
    st.write("Prerequisites:", x["prerequisites"], " Approvals:", x["approvals"], " Security:", x["security"])
    st.write("Validation:", x["validation"], " Alternative:", x["alternative"])
    st.markdown("**Blocked and not-eligible requests (negative cases)**")
    table(s["unsupported_requests"])


def _a8(res, s, tech):
    if not s["packages"]:
        st.info("No customer-managed decisions in this scenario.")
        return
    labels = [p["manifest"]["requirement"] for p in s["packages"]]
    sel = st.selectbox("Engineering package", labels, key="ag_pkg")
    p = next(x for x in s["packages"] if x["manifest"]["requirement"] == sel)
    m = p["manifest"]
    st.write(f"State **{m['state']}** · metadata **{m['metadata_label']}** · activated: {m['activated']} · published: {m['published']} · complex-join request: {m['complex_join_request']}")
    f = st.selectbox("File", list(p["files"]), key="ag_file")
    st.code(p["files"][f], language="sql" if f.endswith(".sql") else ("json" if f.endswith(".json") else None))
    if tech:
        st.json(m)


def _a9(res, s, tech):
    st.write("AI may **propose** a rule; it can never approve one. Approvals below are SYNTHETIC-scope fixtures and never count as live approval.")
    st.markdown(f"AI approval attempt refused: **{s['rules']['ai_approval_refused']}** · unresolved material rules before: **{s['metrics']['unresolved_business_rules_before']}** → after: **{s['metrics']['unresolved_business_rules_after']}**")
    st.markdown(f"Level 3 reconciliation **before** rule approval: `{s['recon']['l3_before_rules']['status']}` · **after**: `{s['recon']['levels']['L3']['status']}`")
    table([{"rule": r["rule_id"], "description": r["description"][:90], "category": r["category"], "status": r["status"], "scope": r["approval_scope"], "owner": r["owner"],
            "tests": f"{sum(1 for t in r['test_results'] if t['ok'])}/{len(r['examples'])}"} for r in s["rules"]["after"]])
    st.markdown("**Business logic discovery (A discoverable · B partial · C explicit)**")
    l = s["logic_discovery"]
    st.write(f"Category A normalised items: {len(l['category_A'])}; Category B markers needing review: {len(l['category_B'])}")
    if tech:
        st.json(l)


def _a10(res, s, tech):
    m = s["model"]
    for k, v in m["layers"].items():
        with st.expander(k.replace("_", " ").title(), expanded=k == "4_semantic"):
            if k == "4_semantic":
                table([{"fact": f["name"], "grain": f["grain"], "keys": ", ".join(f["keys"]), "measures": ", ".join(f["measures"]), "dimensions": ", ".join(f["dims"])} for f in v["facts"]])
                st.write("Dimensions:", v["dimensions"], " Bridges:", [b["name"] for b in v["bridges"]])
                st.write("Analytic models:", [a["name"] for a in v["analytic_models"]])
            elif k == "1_acquisition":
                table(v)
            else:
                table([{kk: vv for kk, vv in i.items() if kk != "sql"} for i in v] if isinstance(v, list) else [])
                if tech:
                    for i in v:
                        if isinstance(i, dict) and i.get("sql"):
                            st.code(i["sql"], language="sql")
    st.write(f"Grain check: **{s['grain']['status']}** · SQL functional check: **{s['sqlite']['status']}** ({s['sqlite']['mode']}) · deployed: {m['deployed']}")
    fo = s["sqlite"]["fan_out_demonstration"]
    st.warning(f"Fan-out guard: a naive fact-to-fact join would report PO value {fo['naive_join_po_value']:,.2f} instead of {fo['correct_po_value']:,.2f}.")
    if s["model"]["skipped_acquisition"]:
        st.caption(f"{len(s['model']['skipped_acquisition'])} requirements have no acquisition object until their decision is resolved.")


def _a11(res, s, tech):
    mode = st.radio("Execution mode", ["DEMO", "CONNECTED_READ_ONLY", "CONTROLLED_EXECUTION"], horizontal=True, key="ag_mode")
    st.caption({"DEMO": "Synthetic only (default).", "CONNECTED_READ_ONLY": "Authorized reads only; no interface configured in this build, so reads are BLOCKED.",
                "CONTROLLED_EXECUTION": "Requires explicit authorization and a verified executor; none exists in this build."}[mode])
    table([{"step": p["step"], "name": p["name"], "state": p["state"], "detail": p["detail"]} | ({"idempotency_key": p["idempotency_key"]} if tech else {}) for p in s["plan"][mode]], 520)
    st.caption("DEPLOYED and RUNTIME_VERIFIED are reserved for live evidence and cannot be reached by the synthetic flow.")


def _a12(res, s, tech):
    v = s["validation"]
    st.write(f"Offline status **{v['offline_status']}** · live status **{v['live_status']}**. {v['note']}")
    table(v["checks"], 520)


def _a13(res, s, tech):
    r = s["recon"]
    st.write(f"Overall (synthetic): **{r['overall']}**. SYNTHETIC_PASS means two independent calculations agree on generated data; it is not a customer Finance reconciliation.")
    st.markdown("**Golden transaction** - hand-authored expectations vs both calculation paths")
    table(r["golden"]["rows"])
    st.markdown("**Levels**")
    table([{"level": k, "name": v["name"] if "name" in v else "", "status": v["status"], "reason": v.get("reason", "")} for k, v in r["levels"].items() if v])
    st.markdown("**Injected defects (detection proof)**")
    table([{"defect": d["defect"], "detected": d["detected"], "detected by": ", ".join(d["detected_by"]), "L3 differences": d["l3_differences"]} for d in r["defect_matrix"]])
    if r["naive_double_count"]:
        nv = r["naive_double_count"]
        st.error(f"Duplicate-posting guard: summing source FI and replicated Central Finance FI gives **{nv['status']}** with {nv['differences_count']} differences; the single-source rule passes.")
    st.caption(f"Tolerance policy (synthetic fixture): {r['tolerance_policy']}")


def _a14(res, s, tech):
    st.markdown("**Status dimensions (independent)**")
    table([{"dimension": k, "status": v} for k, v in res["status"].items()])
    st.markdown("**Acceptance gates**")
    table([{"gate": g["id"], "name": g["name"], "status": g["status"], "evidence": g["evidence"]} for g in res["gates"]], 520)
    st.info(f"Overall: {res['overall_release']}. Synthetic success establishes engineering readiness for an architecture demonstration only. "
            "Live SAP, BDC and Finance validation remain HOLD until live evidence is collected and reviewed.")
    st.download_button("Download results (JSON)", json.dumps(res, default=str, indent=1), "bdc_v013_synthetic_results.json", mime="application/json")


# ---------------------------------------------------------------------------------------------------- Level 2: Ontology
def _ontology(res, s, scn, tech):
    st.radio("Ontology", ONTO_VIEWS, horizontal=True, key="tabs_onto", label_visibility="collapsed")
    view = st.session_state["tabs_onto"]
    o = ontology.build(res, scn)
    c = o["counts"]
    st.markdown(badge("SYNTHETIC ONTOLOGY - DERIVED FROM THE SCENARIO RUN, NOT TENANT-VERIFIED", True), unsafe_allow_html=True)
    m = st.columns(6)
    m[0].metric("SAP objects", c["objects"])
    m[1].metric("Reused", c["reused"])
    m[2].metric("Extended", c["extended"])
    m[3].metric("New view / product", c["created"])
    m[4].metric("Solved in Datasphere", c["datasphere"])
    m[5].metric("Unresolved", c["unresolved"])
    if view == "How data flows":
        _onto_flow(res, o, scn)
    elif view == "How components are wired":
        _onto_wired(o)
    else:
        _onto_concepts()


def _onto_flow(res, o, scn):
    c, rc = o["counts"], o["recon"]
    acq = Counter_(x["acq_type"] for x in o["lineage"] if x["acq_type"] != "-")
    diagram(AD.dataflow_svg(res, scn)[0])
    flt = st.selectbox("Show", ["All objects", "With a delta", "New backend view / customer-managed product", "Extended SAP product", "Solved in Datasphere", "Unresolved", "No delta"], key="ag_onto_filter")
    keep = {"All objects": lambda x: True, "With a delta": lambda x: x["delta_type"] != "NO_DELTA", "New backend view / customer-managed product": lambda x: x["decision"] == "CREATE_CUSTOMER_MANAGED_PRODUCT",
            "Extended SAP product": lambda x: x["decision"] in ("KEY_USER_EXTENSION", "DATA_PRODUCT_EXTENSION"), "Solved in Datasphere": lambda x: x["decision"] == "DATASPHERE_ENRICHMENT",
            "Unresolved": lambda x: x["decision"] in ("CATALOG_REVIEW_REQUIRED", "-"), "No delta": lambda x: x["delta_type"] == "NO_DELTA"}[flt]
    pids = sorted({x["product"].split(" / ")[0] for x in o["lineage"] if x["product"] != "none"})
    prod = st.selectbox("Data product", ["(all)"] + pids, key="ag_onto_prod")
    rows = [x for x in o["lineage"] if keep(x) and (prod == "(all)" or x["product"].startswith(prod))]
    st.caption("One row per SAP object, left to right: the object, its delta, what is reused / extended / created, how it is acquired, which views it passes through, where it lands in the "
               "semantic model, and which reconciliation levels prove it.")
    table([{"SAP object": f"{x['label']} ({x['system']})", "delta": x["delta_type"], "solution": x["route"], "what is created": "; ".join(a.split(" (")[0] for a in x["creates"][:2]),
            "acquired as": x["acquisition"], "harmonize": ", ".join(x["harmonize"]) or "-", "transform": ", ".join(x["transform"]) or "-", "lands in": x["target"],
            "analytic model": ", ".join(x["models"]) or "-", "covered by scenario-level reconciliation": ", ".join(x["proof"]) or "-"} for x in rows], 640)
    if rows:
        opts = [f"{x['label']} - {x['sap_object']}" for x in rows]
        pick = st.selectbox("Trace one object", opts, key="ag_onto_pick")
        x = rows[opts.index(pick)] if pick in opts else rows[0]
        steps = [("SAP object", f"{x['sap_object']}"), ("Delta", f"{x['delta']}" + (f" ({x['customization']})" if x["customization"] != "-" else "")), ("Compared with", x["product"]),
                 ("Solution", x["route"]), ("Created", "; ".join(a.split(" (")[0] for a in x["creates"])), ("Acquired as", x["acquisition"]),
                 ("Harmonized by", ", ".join(x["harmonize"]) or "-"), ("Transformed by", ", ".join(x["transform"]) or "-"), ("Lands in", x["target"]),
                 ("Exposed in", ", ".join(x["models"]) or "-"), ("Covered by scenario-level reconciliation", ", ".join(x["proof"]) or "not yet (unresolved)")]
        st.markdown('<div class="ag-panel"><div class="ag-kicker">Trace</div>' + "<br>".join(f"<b>{T.esc(k)}:</b> {T.esc(v)}" for k, v in steps) + "</div>", unsafe_allow_html=True)


def Counter_(it):
    d: dict[str, int] = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return d


def _onto_wired(o):
    st.markdown(f"**{o['nodes']} nodes and {len(o['edges'])} typed relations** connect the objects to the proof. Every relation is listed; none is inferred outside the scenario run.")
    table([{"relation": k, "count": o["by_relation"].get(k, 0), "from": v[0], "to": v[1]} for k, v in ontology.RELATIONS.items()], 360)
    rel = st.selectbox("List the edges of one relation", list(ontology.RELATIONS), key="ag_onto_rel")
    es = [e for e in o["edges"] if e["rel"] == rel]
    seen, uniq = set(), []
    for e in es:
        k = (e["from"], e["to"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    st.caption(f"{len(es)} edge(s), {len(uniq)} distinct")
    table([{"from": e["from"], "relation": e["rel"], "to": e["to"], "first seen in": e["ref"]} for e in uniq[:300]], 520)


def _onto_concepts():
    areas = sorted({c["family"] for c in arch.concepts()} - {"shared"})
    fam = st.radio("Concepts", ["all"] + areas, horizontal=True, key="ag_onto")
    cs = [c for c in arch.concepts() if fam in ("all", c["family"], ) or c["family"] == "shared"]
    st.write(f"{len(cs)} concepts and {len(arch.relations())} relations in the full model. Dashed = project concept; solid = SAP term (not source-checked). This is the suite's own model, not an SAP-published ontology.")
    if st.checkbox("Draw the concept graph (renders in the browser; may take a moment)", key="ag_onto_graph"):
        diagram(_concept_graph(fam))
    table([{k: c[k] for k in ("label", "kind", "family", "grounding", "desc")} for c in cs], 520)



# ---------------------------------------------------------------------------------------------------- Level 2: Architecture & operations
@st.cache_data(show_spinner=False, max_entries=8)
def _cached_import(inv_bytes: bytes, cat_bytes: bytes) -> dict:
    """Parse and run once per pair of files: widget interactions re-run the page and must not repeat the comparison."""
    inv, e1 = importer.parse(inv_bytes, "inventory")
    cat, e2 = importer.parse(cat_bytes, "catalog")
    return {"ok": False, "errors": e1 + e2, "rows": [], "summary": {}} if (e1 or e2) else importer.run(inv, cat)


def _run_architecture(res, scn):
    """Run the request in the box and show the whole trace (a replay slider left at 0 must not make a new run look empty)."""
    ss = st.session_state
    run = agents.run_request(ss.get("ag_liveq", ""), res, scn)
    ss["ag_live"] = run
    ss["ag_live_scn"] = scn
    ss["ag_step"] = len(arch.live_events(run))
    ss["ag_play"] = False


PLAY_SPEEDS = {"0.25x": 0.25, "0.5x": 0.5, "1x": 1.0, "2x": 2.0, "4x": 4.0}
PLAY_BASE_SECONDS = 1.5   # seconds per event at 1x


def _toggle_play(n):
    ss = st.session_state
    if ss.get("ag_play"):
        ss["ag_play"] = False
    else:
        if ss.get("ag_step", n) >= n:
            ss["ag_step"] = 0
        ss["ag_play"] = True


def _restart_play():
    st.session_state["ag_step"] = 0
    st.session_state["ag_play"] = True


def _architecture(res, s, scn, tech):
    st.radio("Architecture", ARCH_TABS, horizontal=True, key="tabs_arch", label_visibility="collapsed")
    tab = st.session_state["tabs_arch"]
    if tab != "Live run":
        st.session_state["ag_play"] = False      # leaving the tab stops playback; it must not resume by itself on return
    pref = " ".join(f"**{k}** {'preferred' if v['preferred'] else 'conditional, not approved'} ({v['tag']})" for k, v in arch.OPTIONS.items())
    st.caption("Architecture preference: " + pref + " · " + arch.BADGE)
    if tab == "Live run":
        st.markdown("##### Follow a request through the architecture")
        q = st.text_input("Business intent", value="Reconcile the selected synthetic scenario end to end", key="ag_liveq")
        st.button("Run architecture", key="runarch", type="primary", on_click=_run_architecture, args=(res, scn))
        run = (st.session_state.get("ag_live") if st.session_state.get("ag_live_scn") == scn else None) or agents.run_request(q, res, scn)
        ev = arch.live_events(run)
        ss = st.session_state
        if not 0 <= ss.get("ag_step", -1) <= len(ev):
            ss["ag_step"] = len(ev)
        c1, c2, c3 = st.columns([1, 1, 3])
        playing = bool(ss.get("ag_play"))
        c1.button("Pause" if playing else "Play replay", key="ag_playbtn", on_click=_toggle_play, args=(len(ev),), help="Replays the request event by event, hands-free.")
        c2.button("Restart", key="ag_restart", on_click=_restart_play)
        c3.select_slider("Speed", options=list(PLAY_SPEEDS), value="1x", key="ag_speed", help="Playback speed. 0.25x is slowest, 4x fastest.")
        every = PLAY_BASE_SECONDS / PLAY_SPEEDS[ss.get("ag_speed", "1x")] if playing else None

        @st.fragment(run_every=every)
        def _replay():
            if ss.get("ag_play"):
                if ss["ag_step"] < len(ev):
                    ss["ag_step"] += 1
                if ss["ag_step"] >= len(ev):
                    ss["ag_play"] = False
                    st.rerun()
            step = st.slider("Replay step", 0, len(ev), key="ag_step", help="Drag to step through manually. Run architecture resets it to the full trace.")
            diagram(AD.sequence_svg(ev, step)[0])
            table([{"#": i + 1, "from": e["from"], "to": e["to"], "event": e["label"], "state": e["state"]} for i, e in enumerate(ev[:max(step, 1)])])
        _replay()
        st.caption("Events are produced from the real orchestrator trace. The last event shows that SAP connectors are not reached in DEMO mode.")
    elif tab == "Complete architecture":
        _complete_architecture(res, s, scn)
    elif tab == "Adapters":
        _adapters_view(res, s, scn)
    elif tab == "Tool hosting":
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Tool (MCP-style) exposure", "SAP-facing access", "Credential handling")])
    elif tab == "Agent hosting":
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Agent runtime hosting", "Agent registration and discovery")])
    elif tab == "Registry":
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Agent registration and discovery", "Registration never decides hosting")])
        st.caption("Registration is a control-plane decision; it never moves where an agent executes.")
    elif tab == "Selection criteria":
        table([{"criterion": c, **{k: arch.SCORES[k][i] for k in arch.OPTIONS}} for i, c in enumerate(arch.CRITERIA)])
        st.caption("All scores are qualitative assumptions for discussion, not measurements. No cost figures are given; commercial and operating cost need customer and vendor input. Only P1 exists in this build.")
    elif tab == "Decision brief":
        st.markdown(arch.BRIEF)
        st.markdown(badge(arch.BADGE, True), unsafe_allow_html=True)
    else:
        st.markdown("**Landscape across systems**")
        diagram(AD.landscape_svg(landscape.build(res, scn), agents.catalog_view(), len(agents.TOOLS))[0])
        st.markdown("**Agent suite architecture**")
        diagram(AD.agent_arch_svg(res, scn)[0])
        st.markdown("**End-to-end data flow and wiring**")
        diagram(AD.dataflow_svg(res, scn)[0])
        for k in arch.OPTIONS:
            st.markdown(f"**Deployment option {k}**")
            diagram(AD.deployment_svg(k, res)[0])


def _adapters_view(res, s, scn):
    st.markdown(badge(adapters.BADGE, True), unsafe_allow_html=True)
    st.markdown("Agents never reach a system directly. Each system is reached through **one read-only adapter** that returns evidence-class-tagged records; the cross-system comparison is only "
                "as good as these adapters. None is configured in this build, so every stage runs on synthetic evidence.")
    table(adapters.registry(res, scn), 520)
    st.markdown("##### Adapter contract (common to every system)")
    table([{"operation": a, "what it does": b} for a, b in adapters.CONTRACT], 300)
    st.caption(adapters.PROVENANCE)
    st.markdown("##### What makes comparing across systems hard, and what the design does about it")
    table([{"challenge": a, "what the design does": b} for a, b in adapters.CHALLENGES], 420)


# ---------------------------------------------------------------------------------------------------- Complete architecture (all components across systems)
LAND_VIEWS = ["Landscape diagram", "Agent suite architecture", "Data flow", "Component inventory", "System drill-down", "Flows", "Deployment options"]
def _complete_architecture(res, s, scn):
    L = landscape.build(res, scn)
    comps = L["components"]
    n_sys = len([c for c in comps if c["kind"] == "System"])
    st.markdown(badge(landscape.BADGE, True) + f"<div class='ag-note' style='margin-top:.4rem'>Scenario {T.esc(scn)}: every component below is derived from the synthetic scenario run; "
                "SAP product names are generic terms and nothing is tenant-verified.</div>", unsafe_allow_html=True)
    st.caption("Modelled landscape. Not shown: SAP BTP, network and Cloud Connector, identity provider, Datasphere spaces and connections, SAP Analytics Cloud as a consumer. "
               "How ECC and BW reach BDC is modelled, not verified.")
    m = st.columns(5)
    m[0].metric("Systems", n_sys)
    m[1].metric("Components", len(comps))
    m[2].metric("Flows", len(L["flows"]))
    m[3].metric("Reconciliation levels", len([f for f in L["flows"] if f["plane"] == "recon"]))
    m[4].metric("Live interfaces reached", 0)
    st.radio("Architecture view", LAND_VIEWS, horizontal=True, key="tabs_archview", label_visibility="collapsed")
    view = st.session_state["tabs_archview"]
    if view == "Landscape diagram":
        diagram(AD.landscape_svg(L, agents.catalog_view(), len(agents.TOOLS))[0])
        st.caption("Agents sit on top and reach systems only through read-only adapters (none configured). Zones run from source systems through Finance consolidation and SAP Business Data Cloud to Datasphere and "
                   "consumption; numbered arrows are explained in the flow key; reconciliation levels are shown below the zones. Hover a component for its detail; the Flows view lists every edge.")
    elif view == "Agent suite architecture":
        diagram(AD.agent_arch_svg(res, scn)[0])
        st.caption("Experience, orchestration (a pluggable planner behind a deterministic validator), three agents with typed tools, the tool layer, deterministic engines and synthetic evidence. "
                   "Governance controls sit beside the layer they govern; nothing reaches SAP.")
    elif view == "Data flow":
        diagram(AD.dataflow_svg(res, scn)[0])
    elif view == "Component inventory":
        names = [n for _, n in L["layers"]]
        c1, c2 = st.columns(2)
        layer = c1.selectbox("Layer", ["(all)"] + names, key="ag_inv_layer")
        syss = ["(all)"] + sorted({c["system"] for c in comps})
        system = c2.selectbox("System", syss, key="ag_inv_sys")
        rows = [r for r in landscape.inventory(L) if layer in ("(all)", r["layer"]) and system in ("(all)", r["system"])]
        st.caption(f"{len(rows)} of {len(comps)} components")
        table(rows, 640)
    elif view == "System drill-down":
        opts = [x for x in L["systems"]] + ["Suite"]
        sysid = st.selectbox("System", opts, key="ag_drill", format_func=lambda x: x if x != "Suite" else "Suite (agent suite, governance)")
        mine = [c for c in comps if c["system"] == sysid]
        head = next((c for c in mine if c["kind"] == "System"), None)
        if head:
            st.markdown(f'<div class="ag-panel"><div class="ag-kicker">{T.esc(dict(L["layers"])[head["layer"]])}</div><h3 style="margin:.1rem 0 .3rem">{T.esc(head["name"])}</h3>{T.esc(head["detail"])}</div>', unsafe_allow_html=True)
        st.markdown("**Components**")
        table([{"component": c["name"], "kind": c["kind"], "detail": c["detail"], "interface": c["interface"], "status": c["status"], "evidence": c["evidence"]} for c in mine], 420)
        is_source = bool(head) and head["layer"] == "source"
        rel = [f for f in L["flows"] if sysid in (f["from"], f["to"]) or (is_source and "source systems" in (f["from"], f["to"]))]
        st.markdown("**Flows touching this system**")
        table([{"plane": f["plane"], "from": f["from"], "to": f["to"], "label": f["label"], "status": f["status"]} for f in rel] or [{"plane": "-", "from": "-", "to": "-", "label": "none", "status": "-"}], 320)
    elif view == "Flows":
        table([{"plane": f["plane"], "from": f["from"], "to": f["to"], "label": f["label"], "status": f["status"]} for f in L["flows"]], 640)
        st.caption("Planes: data, fi (Finance), ref (reference or optional), recon (reconciliation), control, gov (governance), blocked (not reached in DEMO). "
                   "Reconciliation statuses are synthetic verdicts, not live validation.")
    else:
        st.markdown("##### Deployment options for the suite itself (proposed, not tenant-verified)")
        opt = st.radio("Option", list(arch.OPTIONS), format_func=lambda k: f"{k} · {arch.OPTIONS[k]['name']}", horizontal=True, key="ag_opt")
        o = arch.OPTIONS[opt]
        st.markdown(badge(arch.BADGE, True) + f" &nbsp; Execution mode: `{o['mode']}` · {o['tag']}", unsafe_allow_html=True)
        diagram(AD.deployment_svg(opt, res)[0])
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Who owns what**\n\n" + "\n".join(f"- **{k}:** {v}" for k, v in o["owns"].items()))
        c2.markdown("**Advantages**\n\n" + "\n".join(f"- {x}" for x in o["advantages"]))
        c3.markdown("**Assumptions and limits**\n\n" + "\n".join(f"- {x}" for x in o["assumptions"] + o["limits"]))
