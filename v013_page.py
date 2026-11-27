"""BDC Transition Agent Suite (v0.13) - Streamlit cockpit. SYNTHETIC data only, DEMO mode only.

Two-level topology modelled on a finance-agent cockpit:
  Level 1  Home: "Ask the transition agents" (scenario + request + example chips) and three launch tabs.
  Level 2  Spaces: Workbench apps (14 apps) | Agents (Ask, Catalog, Technical options) | Architecture & operations.
Everything shown derives from the persisted/cached result set produced by bdcwb.run; no figure is hardcoded.
Navigation changes only happen in callbacks (never by writing a widget's session key after it was instantiated).
"""
from __future__ import annotations

import json
import re

import streamlit as st

import suite_theme as T
from bdcwb import agents, arch
from bdcwb.run import run_all

AREAS = ["1 Architecture and scenario", "2 Source systems", "3 SAP object discovery", "4 Dependency graph", "5 Data product catalog",
         "6 Mapping and delta analysis", "7 Extensibility decisions", "8 Customer-managed product engineering", "9 Business rules",
         "10 Datasphere modelling", "11 Execution plan", "12 Technical validation", "13 Finance reconciliation", "14 Evidence and release readiness"]
AREA_INFO = {1: "Scenario metrics, topology and mode.", 2: "Systems, release, client and FI source of truth.", 3: "P2P object inventory and discovered SAP objects.",
             4: "Recursive dependency graph; unresolved objects shown.", 5: "Data-product catalog with evidence classes.", 6: "16-dimension delta against catalog candidates.",
             7: "Deterministic reuse / extend / build decisions.", 8: "Generated customer-managed product packages (templates).", 9: "Rule book; AI cannot approve a rule.",
             10: "Five-layer model, grain check, SQL fan-out guard.", 11: "Execution plan per mode; writes stay blocked.", 12: "Offline technical validation checks.",
             13: "Golden transaction, three levels, injected defects.", 14: "Status dimensions and gates G01-G15."}
GROUPS = [("Discover", [1, 2, 3, 4, 5]), ("Decide", [6, 7, 9]), ("Engineer", [8, 10, 12]), ("Reconcile", [13]), ("Plan and release", [11, 14])]
SCEN = {"A": "A - single S/4HANA system", "B": "B - multi-system with Central Finance"}
SPACES = ["Workbench apps", "Agents", "Architecture & operations"]
HOME_TABS = ["How it works", "Workbench apps", "Agents & architecture"]
AGENT_TABS = ["Ask the agents", "Agent catalog", "Technical options"]
ARCH_TABS = ["Live run", "Complete architecture", "Tool hosting", "Agent hosting", "Registry", "Selection & cost", "Decision brief", "Ontology", "Diagrams"]
INTENT_APP = {"full": 14, "readiness": 14, "recon": 13, "engineering": 8, "rules": 9, "gap": 6, "discovery": 3, "write": 11}
FAMILY_EXAMPLE = {"discovery": 1, "gap": 2, "engineering": 5, "recon": 4, "governance": 7}
_KEEP = object()


@st.cache_data(show_spinner="Running the synthetic pipeline (Scenario A and B)...")
def load() -> dict:
    return run_all()


def table(rows, max_height: int = 420) -> None:
    st.markdown(T.html_table(rows, max_height), unsafe_allow_html=True)


def badge(text: str, warn: bool = False) -> str:
    return T.badge(text, "warn" if warn else "")


# ---------------------------------------------------------------------------------------------------- navigation
def _go(view: str = "space", space: str | None = None, area=_KEEP, agents_tab: str | None = None, arch_tab: str | None = None,
        home_tab: str | None = None) -> None:
    ss = st.session_state
    ss["nav_view"] = view
    if space:
        ss["tabs_space"] = space
    if area is not _KEEP:
        ss["ag_area"] = area
    if agents_tab:
        ss["tabs_agents"] = agents_tab
    if arch_tab:
        ss["tabs_arch"] = arch_tab
    if home_tab:
        ss["tabs_home"] = home_tab


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
    widths = {"home": [.5, 1.3, 4.0, 3.0, 3.0, 2.0], "space": [.5, 1.3, 3.4, 1.0, 2.8, 2.0, 2.9, 1.9], "old": [.5, 1.3, 5.3, 2.4]}[mode]
    with st.container(key="shell"):
        c = st.columns(widths, vertical_alignment="center")
        c[0].button("", icon=":material/home:", key="nav_home", on_click=_go, kwargs={"view": "home"}, help="My Home")
        with c[1].popover("Menu", icon=":material/apps:"):
            st.caption("BDC TRANSITION WORKSPACE")
            st.button("My Home", key="m_home", icon=":material/home:", on_click=_go, kwargs={"view": "home"}, width="stretch")
            st.button("Discovery and scope", key="m_disc", icon=":material/travel_explore:", on_click=_go,
                      kwargs={"view": "space", "space": "Workbench apps", "area": AREAS[2]}, width="stretch")
            st.button("Gaps and decisions", key="m_gap", icon=":material/rule:", on_click=_go,
                      kwargs={"view": "space", "space": "Workbench apps", "area": AREAS[6]}, width="stretch")
            st.button("Engineering", key="m_eng", icon=":material/construction:", on_click=_go,
                      kwargs={"view": "space", "space": "Workbench apps", "area": AREAS[7]}, width="stretch")
            st.button("Reconciliation", key="m_rec", icon=":material/balance:", on_click=_go,
                      kwargs={"view": "space", "space": "Workbench apps", "area": AREAS[12]}, width="stretch")
            st.button("Live architecture", key="m_live", icon=":material/lan:", on_click=_go,
                      kwargs={"view": "space", "space": "Architecture & operations", "arch_tab": "Live run"}, width="stretch")
            st.button("Complete architecture", key="m_arch", icon=":material/schema:", on_click=_go,
                      kwargs={"view": "space", "space": "Architecture & operations", "arch_tab": "Complete architecture"}, width="stretch")
            st.button("Ask the BDC agents", key="m_ask", icon=":material/smart_toy:", on_click=_go,
                      kwargs={"view": "space", "space": "Agents", "agents_tab": "Ask the agents"}, width="stretch")
            st.divider()
            st.button("Old demo (v0.12 pages)", key="m_old", icon=":material/history:", on_click=_go, kwargs={"view": "old"}, width="stretch")
        c[2].markdown(f'<div class="ag-brand"><div class="ag-logo">B</div><div><div class="ag-crumb">{T.esc(crumb)}</div>'
                      f'<div class="ag-title">{T.esc(title)}</div></div></div>', unsafe_allow_html=True)
        if mode == "old":
            c[3].button("Open the Agent Suite", key="old_to_suite", type="primary", on_click=_go, kwargs={"view": "home"}, width="stretch")
            return
        saved = ss.get("theme_saved", T.DEFAULT_THEME)
        # c[3] is an empty spacer column that pushes the controls to the right edge
        c[4].selectbox("Theme", list(T.THEMES), index=list(T.THEMES).index(saved) if saved in T.THEMES else 0, key="ag_theme", on_change=_save_theme)
        c[5].markdown(T.badge("SYNTHETIC - LOCAL DEMO"), unsafe_allow_html=True)
        if mode == "space":
            c[6].selectbox("Scenario", list(SCEN), format_func=lambda k_: SCEN[k_], key="ag_scn")
            c[7].checkbox("Technical details", key="ag_tech")


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
            _home(res)
        else:
            scn = ss.get("ag_scn", "A")
            s = res["scenarios"][scn]
            tech = bool(ss.get("ag_tech"))
            st.radio("Space", SPACES, horizontal=True, key="tabs_space", label_visibility="collapsed")
            _status_strip(res)
            {"Workbench apps": _apps, "Agents": _agents, "Architecture & operations": _architecture}[ss["tabs_space"]](res, s, scn, tech)
    st.markdown(T.footer(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------------------------------- shared widgets
def _status_strip(res: dict) -> None:
    """Synthetic and live status stay separate and always visible."""
    x = res["status"]
    st.markdown('<div style="margin:.9rem 0 .2rem">' + T.badge("SYNTHETIC DATA - DEMO MODE - NO SAP CONNECTION", "ok") + " "
                + T.badge("LIVE SAP VALIDATION: " + x["LIVE_SAP_VALIDATION"], "warn") + " " + T.badge("LIVE BDC VALIDATION: " + x["LIVE_BDC_VALIDATION"], "warn") + " "
                + T.badge("FINANCE VALIDATION: " + x["FINANCE_VALIDATION"], "warn") + " "
                + T.badge("PUBLICATION AUTHORIZATION (live evidence): " + x["PUBLICATION_AUTHORIZATION"], "warn") + "</div>", unsafe_allow_html=True)


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
    route = agents.route(ss["ag_q_input"])
    fam = next(f for f in agents.FAMILIES if f["id"] == route["family"])
    agree = "selector and request agree" if scn == ss.get("ag_scn", "A") else "the request overrides the selector"
    st.markdown(f'<span class="ag-note">Effective scenario: <b>{scn}</b> &nbsp;{agree} &nbsp;</span><span class="ag-pill">Routed to {T.esc(fam["name"])} agent</span>', unsafe_allow_html=True)


def _scn_select() -> None:
    st.selectbox("Scenario", list(SCEN), format_func=lambda k: SCEN[k], key="ag_scn")


def _app_tiles(prefix: str) -> None:
    for gname, nums in GROUPS:
        st.markdown(f'<div class="ag-kicker" style="margin:.9rem 0 .35rem">{T.esc(gname)}</div>', unsafe_allow_html=True)
        cols = st.columns(4)
        for j, n in enumerate(nums):
            with cols[j % 4]:
                with st.container(key=f"tile_{prefix}_{n}"):
                    st.markdown(f'<div class="ag-kicker">App {n}</div><h4 style="margin:.1rem 0 .25rem;font-size:.98rem">{T.esc(AREAS[n - 1].split(" ", 1)[1])}</h4>'
                                f'<div class="ag-note" style="min-height:2.4em">{T.esc(AREA_INFO[n])}</div>', unsafe_allow_html=True)
                    st.button("Open →", key=f"open_{prefix}_{n}", on_click=_go, kwargs={"view": "space", "space": "Workbench apps", "area": AREAS[n - 1]})


# ---------------------------------------------------------------------------------------------------- Level 1: Home
def _home(res: dict) -> None:
    with st.container(key="home_body"):
        st.markdown('<div class="ag-kicker">BDC transition / agents</div><div class="ag-h1">Ask the transition agents</div>'
                    '<div class="ag-lead">An orchestrator plans your request, routes it to the right agent family and calls its specialist agents with MCP-style '
                    'tool calls. They read the persisted synthetic results; people approve and nothing is written to SAP.</div>', unsafe_allow_html=True)
        _ask_box("h")
        st.radio("Home tabs", HOME_TABS, horizontal=True, key="tabs_home", label_visibility="collapsed")
        tab = st.session_state["tabs_home"]
        if tab == "How it works":
            st.markdown(T.flow([("You ask", "Plain request", "Type a transition question or pick an example; the scenario you choose applies."),
                                ("Orchestrator", "Tool client - plans and calls", "Routes the request to the right agent family and plans the tool calls."),
                                ("Specialist agents", "Tool providers - typed tools", "Each agent has typed tools and a fixed authority class; people approve and nothing is written to SAP."),
                                ("Application layers", "Domain engines and evidence store", "Simulated layers answer the tool calls; no SAP, BDC or Datasphere system is connected.")]),
                        unsafe_allow_html=True)
            st.markdown('<div class="ag-dashed"><b>Run it on your laptop</b><br><span class="ag-note">The code is public and synthetic-only. Python is needed.</span><br>'
                        '<code>git clone https://github.com/Iam-PrasadDeshpande/bdc-finance-reporting-analyzer</code><br>'
                        '<code>pip install -r requirements.txt &amp;&amp; streamlit run app.py</code></div>', unsafe_allow_html=True)
        elif tab == "Workbench apps":
            _app_tiles("home")
        else:
            cols = st.columns(5)
            for col, f in zip(cols, agents.catalog_view()):
                col.markdown(T.card(f"{f['icon']} {f['name']}", f"{len(f['agents'])} agents. {f['blurb']}"), unsafe_allow_html=True)
            b = st.columns(4)
            b[0].button("Ask the agents →", key="h_ask", on_click=_go, kwargs={"view": "space", "space": "Agents", "agents_tab": "Ask the agents"}, width="stretch")
            b[1].button("Agent catalog →", key="h_cat", on_click=_go, kwargs={"view": "space", "space": "Agents", "agents_tab": "Agent catalog"}, width="stretch")
            b[2].button("Live architecture →", key="h_live", on_click=_go,
                        kwargs={"view": "space", "space": "Architecture & operations", "arch_tab": "Live run"}, width="stretch")
            b[3].button("Complete architecture →", key="h_arch", on_click=_go,
                        kwargs={"view": "space", "space": "Architecture & operations", "arch_tab": "Complete architecture"}, width="stretch")
        _status_strip(res)


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
        left.markdown('<div class="ag-kicker">Agents &middot; orchestrated with MCP-style tool calls</div><h3 style="margin:.2rem 0 .4rem">Agent launchpad</h3>'
                      '<div class="ag-note">Every agent is a tile below, grouped by family. Ask in plain words, or pick a tile to see what the agent does. '
                      'The orchestrator plans and calls the specialists; the technical detail (orchestration graph, tool calls, execution options, tool catalog) is in Technical options.</div>',
                      unsafe_allow_html=True)
        with right:
            _ask_box("a")
    r = ss.get("ag_run")
    if r:
        fam = next(f for f in agents.FAMILIES if f["id"] == r["route"]["family"])
        scn_used, src = ss.get("ag_run_scn", ("A", "from the selector"))
        st.markdown(f'<span class="ag-pill">Handled by {T.esc(fam["name"])} agent</span>', unsafe_allow_html=True)
        if r["refusal"]:
            st.markdown(f'<div class="ag-status warn"><b>{T.esc(fam["name"])}</b> &nbsp;Request refused - draft only.</div>', unsafe_allow_html=True)
            st.warning(r["refusal"])
        else:
            st.markdown(f'<div class="ag-status"><b>{T.esc(fam["name"])}</b> &nbsp;Plan complete.</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="ag-note">Your request: <b>&ldquo;{T.esc(r["request"])}&rdquo;</b></div><div class="ag-note" style="margin:.35rem 0 .6rem">'
                    f'Plan scenario: <b>{T.esc(scn_used)}</b> &middot; {T.esc(src)}</div>', unsafe_allow_html=True)
        found = " ".join(t["summary"].rstrip(".") + "." for t in r["trace"][:3])
        agents_used = sorted({t["agent"] for t in r["trace"]})
        st.markdown(f'<div class="ag-panel"><div class="ag-kicker">What the agents found</div>{T.esc(found)}<br>'
                    f'<b>The orchestrator planned {len(r["trace"])} tool call(s) across {len(agents_used)} agent(s):</b> {T.esc(", ".join(agents_used))}. '
                    f'No SAP write was made; a person decides on any proposal.</div>', unsafe_allow_html=True)
        app_no = INTENT_APP.get(r["route"]["intent"], 14)
        st.markdown('<div class="ag-panel" style="margin-bottom:.3rem"><div class="ag-kicker">Full output of this run</div></div>', unsafe_allow_html=True)
        b1, b2, _ = st.columns([2.4, 2.4, 4])
        b1.button(f"Open in {AREAS[app_no - 1].split(' ', 1)[1]} →", key="open_app", type="primary", on_click=_go,
                  kwargs={"view": "space", "space": "Workbench apps", "area": AREAS[app_no - 1]}, width="stretch")
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
    fams = agents.catalog_view()
    if sel:
        a = next((x for f in fams for x in f["agents"] if x["id"] == sel), None)
        if a:
            tools = [t for t in agents.tool_catalog() if t["agent"] == a["name"]]
            st.markdown(f'<div class="ag-panel"><div class="ag-kicker">{T.esc(a["role"])} &middot; {T.esc(a["authority_label"])}</div><h3 style="margin:.1rem 0 .3rem">{T.esc(a["name"])}</h3>'
                        f'{T.esc(a["blurb"])}</div>', unsafe_allow_html=True)
            if tools:
                table([{"tool": t["tool"], "authority": t["authority"], "layer": t["layer"], "description": t["description"]} for t in tools], 220)
            c1, c2, _ = st.columns([2, 1.2, 5])
            c1.button("Try a request for this family →", key="agent_try", on_click=_pick, args=(agents.EXAMPLES[FAMILY_EXAMPLE[a["family"]]],), width="stretch")
            c2.button("Close", key="agent_close", on_click=_select_agent, args=(None,), width="stretch")
    for f in fams:
        st.markdown(f'<div class="ag-kicker" style="margin:1rem 0 .35rem">{T.esc(f["icon"])} {T.esc(f["name"])} &middot; {T.esc(f["blurb"])}</div>', unsafe_allow_html=True)
        cols = st.columns(3)
        for i, a in enumerate(f["agents"]):
            with cols[i % 3]:
                with st.container(key=f"tile_ag_{a['id']}"):
                    st.markdown(f'<div class="ag-kicker">{T.esc(a["role"])}</div><h4 style="margin:.1rem 0 .25rem;font-size:.98rem">{T.esc(a["name"])}</h4>'
                                f'<div class="ag-note" style="min-height:2.6em">{T.esc(a["blurb"])}</div>'
                                f'<span class="ag-tag">{T.esc(a["authority_label"])}</span><span class="ag-tag">{a["tool_count"]} tool(s)</span>', unsafe_allow_html=True)
                    st.button("What does it do? →", key=f"sel_{a['id']}", on_click=_select_agent, args=(a["id"],))


def _catalog_tab():
    fams = agents.catalog_view()
    st.markdown(f'<div class="ag-note">{len(agents.AGENTS)} agents in {len(fams)} families; each family has one orchestrator that only plans. '
                'Authority classes: plans only &middot; read &middot; read (simulated) &middot; local draft &middot; draft only. No agent can write to SAP, activate, transport, deploy or publish.</div>',
                unsafe_allow_html=True)
    pick = st.radio("Family", ["All"] + [f["name"] for f in fams], horizontal=True, key="ag_fam")
    rows = []
    for f in fams:
        if pick in ("All", f["name"]):
            rows += [{"family": f["name"], "agent": a["name"], "role": a["role"], "authority": a["authority_label"], "tools": ", ".join(a["tools"]), "does": a["blurb"]} for a in f["agents"]]
    table(rows, 560)


def _technical_tab(res, scn):
    ss = st.session_state
    r = ss.get("ag_run") or agents.run_request(agents.EXAMPLES[0], res, scn)
    st.markdown('<div class="ag-kicker">Orchestration graph (last run)</div>', unsafe_allow_html=True)
    ev = arch.live_events(r)
    st.graphviz_chart(arch.dot_live(ev, len(ev)))
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
    st.markdown('<div class="ag-kicker" style="margin-top:.8rem">Tool catalog (MCP-style, typed)</div>', unsafe_allow_html=True)
    table(agents.tool_catalog(), 460)


# ---------------------------------------------------------------------------------------------------- Level 2: Workbench apps
def _apps(res, s, scn, tech):
    ss = st.session_state
    c1, c2 = st.columns([4, 1.4], vertical_alignment="bottom")
    area = c1.selectbox("Open a workbench app", AREAS, index=None, placeholder="Open a workbench app", key="ag_area")
    if area is None:
        st.markdown('<div class="ag-kicker" style="margin-top:.4rem">Workbench apps &middot; 14 apps in 5 groups</div>', unsafe_allow_html=True)
        _app_tiles("space")
        return
    c2.button("← All apps", key="apps_back", on_click=_go, kwargs={"view": "space", "area": None}, width="stretch")
    n = int(area.split()[0])
    st.markdown(f'<div class="ag-kicker">Workbench app {n} of 14 &middot; Scenario {T.esc(scn)}</div><h2 style="margin:.1rem 0 .2rem">{T.esc(area.split(" ", 1)[1])}</h2>'
                f'<div class="ag-note" style="margin-bottom:.8rem">{T.esc(AREA_INFO[n])}</div>', unsafe_allow_html=True)
    {1: _a1, 2: _a2, 3: _a3, 4: _a4, 5: _a5, 6: _a6, 7: _a7, 8: _a8, 9: _a9, 10: _a10, 11: _a11, 12: _a12, 13: _a13, 14: _a14}[n](res, s, tech)


def _a1(res, s, tech):
    m = s["metrics"]
    st.caption(f"All figures derive from the persisted run (seed {s['seed']}, mode {s['mode']}, evidence {s['evidence_mode']}).")
    cols = st.columns(4)
    items = [("Source systems", m["source_systems"]), ("Discovered objects", m["discovered_objects"]), ("Dependent objects", m["dependent_objects"]),
             ("Assessed requirements", m["assessed_requirements"]), ("Verified SAP-managed products", m["verified_sap_managed_products"]),
             ("Synthetic fixture products", m["synthetic_fixture_products"]), ("Unverified candidates", m["unverified_product_candidates"]),
             ("Reusable products", m["reusable_products"]), ("Required extensions", m["required_extensions"]), ("Proposed customer-managed", m["proposed_customer_managed_products"]),
             ("Unresolved rules (before → after)", f"{m['unresolved_business_rules_before']} → {m['unresolved_business_rules_after']}"),
             ("Generated artifacts", m["generated_artifacts"]), ("Executed artifacts", m["executed_artifacts"]),
             ("Technical validation", m["technical_validation"]), ("Finance reconciliation", m["finance_reconciliation"]), ("Mode", "DEMO (synthetic)")]
    for i, (k, v) in enumerate(items):
        cols[i % 4].metric(k, v)
    st.markdown("##### Topology (derived from the scenario configuration)")
    st.graphviz_chart(arch.dot_topology(s))


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
    st.graphviz_chart(arch.dot_dependencies(s))
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


# ---------------------------------------------------------------------------------------------------- Level 2: Architecture & operations
def _architecture(res, s, scn, tech):
    st.radio("Architecture", ARCH_TABS, horizontal=True, key="tabs_arch", label_visibility="collapsed")
    tab = st.session_state["tabs_arch"]
    pref = " ".join(f"**{k}** {'preferred' if v['preferred'] else 'conditional, not approved'} ({v['tag']})" for k, v in arch.OPTIONS.items())
    st.caption("Architecture preference: " + pref + " · " + arch.BADGE)
    if tab == "Live run":
        st.markdown("##### Follow a request through the architecture")
        q = st.text_input("Business intent", value="Reconcile the selected synthetic scenario end to end", key="ag_liveq")
        if st.button("Run architecture", key="runarch", type="primary"):
            st.session_state["ag_live"] = agents.run_request(q, res, scn)
        run = st.session_state.get("ag_live") or agents.run_request(q, res, scn)
        ev = arch.live_events(run)
        step = st.slider("Replay step", 0, len(ev), len(ev), key="ag_step")
        st.graphviz_chart(arch.dot_live(ev, step))
        table([{"#": i + 1, "from": e["from"], "to": e["to"], "event": e["label"], "state": e["state"]} for i, e in enumerate(ev[:max(step, 1)])])
        st.caption("Events are produced from the real orchestrator trace. The last event shows that SAP connectors are not reached in DEMO mode.")
    elif tab == "Complete architecture":
        opt = st.radio("Option", list(arch.OPTIONS), format_func=lambda k: f"{k} · {arch.OPTIONS[k]['name']}", horizontal=True, key="ag_opt")
        o = arch.OPTIONS[opt]
        st.markdown(badge(arch.BADGE, True) + f" &nbsp; Execution mode: `{o['mode']}` · {o['tag']}", unsafe_allow_html=True)
        st.graphviz_chart(arch.dot_chain(opt))
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Who owns what**\n\n" + "\n".join(f"- **{k}:** {v}" for k, v in o["owns"].items()))
        c2.markdown("**Advantages**\n\n" + "\n".join(f"- {x}" for x in o["advantages"]))
        c3.markdown("**Assumptions and limits**\n\n" + "\n".join(f"- {x}" for x in o["assumptions"] + o["limits"]))
    elif tab == "Tool hosting":
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Tool (MCP-style) exposure", "SAP-facing access", "Credential handling")])
    elif tab == "Agent hosting":
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Agent runtime hosting", "Agent registration and discovery")])
    elif tab == "Registry":
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Agent registration and discovery", "Registration never decides hosting")])
        st.caption("Registration is a control-plane decision; it never moves where an agent executes.")
    elif tab == "Selection & cost":
        table([{"criterion": c, **{k: arch.SCORES[k][i] for k in arch.OPTIONS}} for i, c in enumerate(arch.CRITERIA)])
        st.caption("Qualitative only. No cost figures are invented; commercial and operating cost need customer and vendor input.")
    elif tab == "Decision brief":
        st.markdown(arch.BRIEF)
        st.markdown(badge(arch.BADGE, True), unsafe_allow_html=True)
    elif tab == "Ontology":
        fam = st.radio("Concepts", ["all"] + [f["id"] for f in agents.FAMILIES], horizontal=True, key="ag_onto")
        cs = [c for c in arch.concepts() if fam in ("all", c["family"], ) or c["family"] == "shared"]
        st.write(f"{len(cs)} concepts and {len(arch.relations())} relations in the full model. Dashed = project concept; solid = SAP term (not source-checked). This is the suite's own model, not an SAP-published ontology.")
        st.graphviz_chart(arch.dot_ontology(fam))
        table([{k: c[k] for k in ("label", "kind", "family", "grounding", "desc")} for c in cs], 520)
    else:
        st.markdown("**Scenario topology**")
        st.graphviz_chart(arch.dot_topology(s))
        st.markdown("**Dependency graph**")
        st.graphviz_chart(arch.dot_dependencies(s))
        for k in arch.OPTIONS:
            st.markdown(f"**{k} chain**")
            st.graphviz_chart(arch.dot_chain(k))
