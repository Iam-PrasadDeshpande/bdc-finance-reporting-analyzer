"""BDC Transition Agent Suite (v0.13) - Streamlit page. SYNTHETIC data only, DEMO mode only.

Two-level topology: Home (ask the agents) -> three spaces: Workbench apps, Agents, Architecture & operations.
Everything shown derives from the persisted/cached result set produced by bdcwb.run; no figure is hardcoded.
"""
from __future__ import annotations

import json

import streamlit as st

from bdcwb import agents, arch
from bdcwb.run import run_all

AREAS = ["1 Architecture and scenario", "2 Source systems", "3 SAP object discovery", "4 Dependency graph", "5 Data product catalog",
         "6 Mapping and delta analysis", "7 Extensibility decisions", "8 Customer-managed product engineering", "9 Business rules",
         "10 Datasphere modelling", "11 Execution plan", "12 Technical validation", "13 Finance reconciliation", "14 Evidence and release readiness"]
SCEN = {"A": "Scenario A - single S/4HANA system", "B": "Scenario B - multi-system landscape with Central Finance"}

CSS = """<style>
.ag-badge{display:inline-block;padding:.15rem .6rem;border:1px solid #b7d3ea;border-radius:6px;background:#eaf3fb;color:#0b5394;font-size:.72rem;font-weight:700;letter-spacing:.04em}
.ag-badge.warn{background:#fff4e5;border-color:#f0c58a;color:#8a4b00}
.ag-card{border:1px solid #dfe6ee;border-radius:10px;padding:.8rem .9rem;background:#fff;min-height:110px}
.ag-card h4{margin:.1rem 0 .3rem;font-size:.98rem;color:#163145}.ag-card p{margin:.1rem 0;color:#53697b;font-size:.85rem}
.ag-tag{display:inline-block;margin:.15rem .25rem 0 0;padding:.05rem .5rem;border:1px solid #d5dde6;border-radius:99px;font-size:.72rem;color:#47586a;background:#f6f8fa}
.ag-kicker{font-size:.72rem;font-weight:800;letter-spacing:.12em;color:#5a7184;text-transform:uppercase}
</style>"""


@st.cache_data(show_spinner="Running the synthetic pipeline (Scenario A and B)...")
def load() -> dict:
    return run_all()


def table(rows, **kw):
    st.dataframe(rows, width="stretch", hide_index=True, **kw)


def badge(text: str, warn: bool = False) -> str:
    return f'<span class="ag-badge{" warn" if warn else ""}">{text}</span>'


def render() -> None:
    res = load()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="ag-kicker">Finance / BDC transition agents</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([3, 2, 1.4])
    c1.markdown("## BDC Transition Agent Suite")
    scn_key = c2.selectbox("Scenario", list(SCEN), format_func=lambda k: SCEN[k], key="ag_scn")
    tech = c3.checkbox("Technical details", key="ag_tech")
    st.markdown(badge("DEMO MODE - SYNTHETIC DATA - NO SAP CONNECTION") + " " + badge("LIVE SAP VALIDATION: HOLD", True) + " " +
                badge("FINANCE VALIDATION: HOLD / INSUFFICIENT_EVIDENCE", True), unsafe_allow_html=True)
    s = res["scenarios"][scn_key]
    home, apps, ag, archt = st.tabs(["Home - ask the agents", "Workbench apps", "Agents", "Architecture & operations"])
    with home:
        _home(res, s, scn_key, tech)
    with apps:
        _apps(res, s, tech)
    with ag:
        _agents(res, s, scn_key, tech)
    with archt:
        _architecture(res, s, scn_key, tech)
    st.caption("Independent assessment prototype, not affiliated with SAP. Synthetic finance data; no live SAP, BDC or Datasphere system is connected. "
               "SYNTHETIC_PASS is not a live Finance validation.")


# ---------------------------------------------------------------------------------------------------- Home
def _home(res, s, scn, tech):
    st.markdown("### Ask the agents")
    st.write("An orchestrator plans your request, routes it to an agent family and calls its specialist agents through typed, MCP-style tools. "
             "Agents read the persisted synthetic results or draft locally; a person approves and nothing is written to SAP.")
    q = st.text_input("Your request", value=st.session_state.get("ag_q", agents.EXAMPLES[0]), key="ag_q_input")
    cols = st.columns(4)
    for i, ex in enumerate(agents.EXAMPLES):
        if cols[i % 4].button(ex, key=f"ex{i}", width="stretch"):
            st.session_state["ag_q"] = ex
            st.session_state["ag_q_input"] = ex
            st.session_state["ag_run"] = agents.run_request(ex, res, scn)
            st.rerun()
    if st.button("Run plan", type="primary", key="runplan"):
        st.session_state["ag_run"] = agents.run_request(q, res, scn)
    r = st.session_state.get("ag_run")
    route = agents.route(q)
    fam = next(f for f in agents.FAMILIES if f["id"] == route["family"])
    st.caption(f"Routed to: **{fam['name']}** (intent: {route['intent']})")
    if r:
        _show_run(r, tech)
    st.markdown("#### How it works")
    cc = st.columns(4)
    for c, (t, d) in zip(cc, [("You ask", "Plain request or an example; the scenario selector applies."), ("Orchestrator", "Plans, routes, calls tools; cannot act on SAP."),
                              ("Specialist agents", "Each has typed tools and a fixed authority class."), ("Application layers", "Domain engines and the evidence store; SAP connectors are not reached in DEMO.")]):
        c.markdown(f'<div class="ag-card"><h4>{t}</h4><p>{d}</p></div>', unsafe_allow_html=True)


def _show_run(r, tech):
    if r["refusal"]:
        st.warning(r["refusal"])
    st.markdown("**Plan**")
    st.write(" → ".join(r["plan"]) if r["plan"] else "-")
    st.markdown("**Answer**")
    for t in r["trace"]:
        st.markdown(f"- **{t['agent']}** · `{t['tool']}` · _{t['authority']}_ — {t['summary']}")
    st.markdown("**Layers reached:** " + " → ".join(r["layers_reached"]))
    if r["approvals_needed"]:
        st.info("Approvals needed from people (nothing proceeds without them): " + "; ".join(r["approvals_needed"]))
    if tech:
        with st.expander("Execution trace (technical)"):
            table([{k: (json.dumps(v, default=str)[:140] if isinstance(v, (dict, list)) else v) for k, v in t.items() if k != "data"} for t in r["trace"]])


# ---------------------------------------------------------------------------------------------------- Workbench apps
def _apps(res, s, tech):
    area = st.selectbox("Workbench area", AREAS, key="ag_area")
    n = int(area.split()[0])
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
    table([{k: o[k] for k in ("id", "obj_type", "release", "api_state", "domain", "grain", "evidence")} | {"delta": o["extraction"]["delta"], "mechanism": o["extraction"]["mechanism"]} for o in objs])


def _a4(res, s, tech):
    d = s["dependencies"]
    st.write(f"{len(d['nodes'])} nodes, {len(d['edges'])} edges; cycles: {len(d['cycles'])}; truncated: {d['truncated']}. Red nodes are **unresolved** (reported, never guessed).")
    st.graphviz_chart(arch.dot_dependencies(s))
    st.markdown("**Unresolved objects**")
    table(d["unresolved"] or [{"object": "none"}])


def _a5(res, s, tech):
    c = s["catalog"]
    st.write(f"Snapshot **{c['snapshot']}** (synthetic fixture). Domain completeness declared: {c['domain_completeness']}. A product missing from an accessible catalog is UNKNOWN unless completeness is established.")
    table([{k: p[k] for k in ("product_id", "name", "version", "evidence", "supported_releases", "activation", "entitlement", "installation", "consumption")} | {"entities": ", ".join(p["entities"])} for p in c["products"]])
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
        table([{"dimension": k, "status": v["status"], "detail": json.dumps(v["detail"], default=str)[:160]} for k, v in c["dimensions"].items()])
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
    table([{"step": p["step"], "name": p["name"], "state": p["state"], "detail": p["detail"]} | ({"idempotency_key": p["idempotency_key"]} if tech else {}) for p in s["plan"][mode]])
    st.caption("DEPLOYED and RUNTIME_VERIFIED are reserved for live evidence and cannot be reached by the synthetic flow.")


def _a12(res, s, tech):
    v = s["validation"]
    st.write(f"Offline status **{v['offline_status']}** · live status **{v['live_status']}**. {v['note']}")
    table(v["checks"])


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
    table([{"gate": g["id"], "name": g["name"], "status": g["status"], "evidence": g["evidence"]} for g in res["gates"]])
    st.info(f"Overall: {res['overall_release']}. Synthetic success establishes engineering readiness for an architecture demonstration only. "
            "Live SAP, BDC and Finance validation remain HOLD until live evidence is collected and reviewed.")
    st.download_button("Download results (JSON)", json.dumps(res, default=str, indent=1), "bdc_v013_synthetic_results.json", mime="application/json")


# ---------------------------------------------------------------------------------------------------- Agents space
def _agents(res, s, scn, tech):
    ask, cat, techo = st.tabs(["Ask the agents", "Agent catalog", "Technical options"])
    with ask:
        st.markdown("##### Agent launchpad")
        q = st.text_input("Request", value=agents.EXAMPLES[3], key="ag_q2")
        if st.button("Run plan", key="runplan2", type="primary"):
            st.session_state["ag_run2"] = agents.run_request(q, res, scn)
        if st.session_state.get("ag_run2"):
            _show_run(st.session_state["ag_run2"], tech)
    with cat:
        fams = agents.catalog_view()
        st.write(f"{len(agents.AGENTS)} agents in {len(fams)} families; each family has one orchestrator that only plans.")
        pick = st.radio("Family", ["All"] + [f["name"] for f in fams], horizontal=True, key="ag_fam")
        for f in fams:
            if pick not in ("All", f["name"]):
                continue
            st.markdown(f"**{f['icon']} {f['name']}** - {f['blurb']}")
            cols = st.columns(3)
            for i, a in enumerate(f["agents"]):
                cols[i % 3].markdown(f'<div class="ag-card"><div class="ag-kicker">{a["role"]}</div><h4>{a["name"]}</h4><p>{a["blurb"]}</p>'
                                     f'<span class="ag-tag">{a["authority_label"]}</span><span class="ag-tag">{a["tool_count"]} tool(s)</span></div>', unsafe_allow_html=True)
    with techo:
        st.markdown("##### Tool catalog (MCP-style, typed)")
        table(agents.tool_catalog())
        st.caption("Authority classes: plans only · read · read (simulated) · read + local draft · draft only. No tool can write to SAP, activate, transport, deploy or publish.")


# ---------------------------------------------------------------------------------------------------- Architecture & operations
def _architecture(res, s, scn, tech):
    tabs = st.tabs(["Live run", "Complete architecture", "Tool hosting", "Agent hosting", "Registry", "Selection & cost", "Decision brief", "Ontology", "Diagrams"])
    pref = " ".join(f"**{k}** {'preferred' if v['preferred'] else 'conditional, not approved'} ({v['tag']})" for k, v in arch.OPTIONS.items())
    st.caption("Architecture preference: " + pref + " · " + arch.BADGE)
    with tabs[0]:
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
    with tabs[1]:
        opt = st.radio("Option", list(arch.OPTIONS), format_func=lambda k: f"{k} · {arch.OPTIONS[k]['name']}", horizontal=True, key="ag_opt")
        o = arch.OPTIONS[opt]
        st.markdown(badge(arch.BADGE, True) + f" &nbsp; Execution mode: `{o['mode']}` · {o['tag']}", unsafe_allow_html=True)
        st.graphviz_chart(arch.dot_chain(opt))
        c1, c2, c3 = st.columns(3)
        c1.markdown("**Who owns what**\n\n" + "\n".join(f"- **{k}:** {v}" for k, v in o["owns"].items()))
        c2.markdown("**Advantages**\n\n" + "\n".join(f"- {x}" for x in o["advantages"]))
        c3.markdown("**Assumptions and limits**\n\n" + "\n".join(f"- {x}" for x in o["assumptions"] + o["limits"]))
    with tabs[2]:
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Tool (MCP-style) exposure", "SAP-facing access", "Credential handling")])
    with tabs[3]:
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Agent runtime hosting", "Agent registration and discovery")])
    with tabs[4]:
        table([{"decision": k, **{o: v[o] for o in arch.OPTIONS}} for k, v in arch.HOSTING if k in ("Agent registration and discovery", "Registration never decides hosting")])
        st.caption("Registration is a control-plane decision; it never moves where an agent executes.")
    with tabs[5]:
        table([{"criterion": c, **{k: arch.SCORES[k][i] for k in arch.OPTIONS}} for i, c in enumerate(arch.CRITERIA)])
        st.caption("Qualitative only. No cost figures are invented; commercial and operating cost need customer and vendor input.")
    with tabs[6]:
        st.markdown(arch.BRIEF)
        st.markdown(badge(arch.BADGE, True), unsafe_allow_html=True)
    with tabs[7]:
        fam = st.radio("Concepts", ["all"] + [f["id"] for f in agents.FAMILIES], horizontal=True, key="ag_onto")
        cs = [c for c in arch.concepts() if fam in ("all", c["family"], ) or c["family"] == "shared"]
        st.write(f"{len(cs)} concepts and {len(arch.relations())} relations in the full model. Dashed = project concept; solid = SAP term (not source-checked). This is the suite's own model, not an SAP-published ontology.")
        st.graphviz_chart(arch.dot_ontology(fam))
        table([{k: c[k] for k in ("label", "kind", "family", "grounding", "desc")} for c in cs])
    with tabs[8]:
        st.markdown("**Scenario topology**")
        st.graphviz_chart(arch.dot_topology(s))
        st.markdown("**Dependency graph**")
        st.graphviz_chart(arch.dot_dependencies(s))
        for k in arch.OPTIONS:
            st.markdown(f"**{k} chain**")
            st.graphviz_chart(arch.dot_chain(k))
