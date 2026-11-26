"""BDC Transition Agent Suite: families, specialist agents, MCP-style typed tools, a deterministic orchestrator.

Design follows the finance-agent cockpit topology: an orchestrator plans a plain-language request, routes it to an agent family,
calls specialist agents through typed tools, and a person approves. Agents READ persisted results or draft locally; none can
write to SAP, activate, transport, deploy or publish. The router is rule-based (deterministic); an LLM can later replace it
behind the same tool contract without widening any authority.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

AUTHORITY = {"PLANS_ONLY": "plans only", "READ": "read", "READ_SIMULATED": "read (simulated)", "LOCAL_DRAFT": "read + local draft",
             "DRAFT_ONLY": "draft only"}
FAMILIES = [
    {"id": "discovery", "name": "Discovery & Scope", "icon": "◆", "blurb": "Scope, SAP objects, dependency graph, catalog evidence, synthetic data."},
    {"id": "gap", "name": "Gap & Decision", "icon": "▦", "blurb": "Field/semantic delta, extensibility decision, business rules and logic."},
    {"id": "engineering", "name": "Engineering", "icon": "◧", "blurb": "Customer-managed product artifacts, Datasphere model, technical validation."},
    {"id": "recon", "name": "Reconciliation", "icon": "◍", "blurb": "Source-to-acquisition, model, end-to-end Finance and Central Finance reconciliation."},
    {"id": "governance", "name": "Governance & Release", "icon": "⬡", "blurb": "Execution plan, approvals, evidence, gates, security."},
]


def _a(id_, family, name, role, blurb, authority, tools):
    return {"id": id_, "family": family, "name": name, "role": role, "blurb": blurb, "authority": authority, "tools": tools}


AGENTS = [
    _a("orch.discovery", "discovery", "Discovery Orchestrator", "ORCHESTRATOR", "Plans discovery requests and calls the specialists.", "PLANS_ONLY", ["scope.resolve_request"]),
    _a("scope", "discovery", "Scope & Intake", "SPECIALIST", "Turns a request into scenario, systems, mode and route.", "READ", ["scope.resolve_request"]),
    _a("objects", "discovery", "Object Discovery", "SPECIALIST", "Lists discovered SAP objects with type, release, API state, evidence.", "READ_SIMULATED", ["discovery.inventory", "discovery.list_objects"]),
    _a("graph", "discovery", "Dependency Mapper", "SPECIALIST", "Resolves dependencies recursively with cycle detection and unresolved reporting.", "READ_SIMULATED", ["discovery.dependency_graph"]),
    _a("catalog", "discovery", "Catalog Scout", "SPECIALIST", "Classifies product evidence; unknown stays unknown.", "READ_SIMULATED", ["catalog.lookup"]),
    _a("synth", "discovery", "Synthetic Data Steward", "SPECIALIST", "Describes the seeded, reproducible synthetic datasets.", "READ", ["data.synthetic_summary"]),
    _a("orch.gap", "gap", "Gap Orchestrator", "ORCHESTRATOR", "Plans gap analysis and remediation requests.", "PLANS_ONLY", ["gap.analyze"]),
    _a("delta", "gap", "Delta Analyst", "SPECIALIST", "Field, key, grain, relationship, extraction and security gaps with coverage numerator/denominator.", "READ", ["gap.analyze"]),
    _a("advisor", "gap", "Extensibility Advisor", "SPECIALIST", "Deterministic reuse / extend / customer-managed recommendation.", "READ", ["decision.recommend"]),
    _a("rules", "gap", "Business Rule Steward", "SPECIALIST", "Lists rules and drafts proposals; only a named human approves.", "LOCAL_DRAFT", ["rules.list", "rules.draft"]),
    _a("logic", "gap", "Logic Discoverer", "SPECIALIST", "Categorises business logic as discoverable, partially discoverable or explicit.", "READ", ["logic.discover"]),
    _a("orch.eng", "engineering", "Engineering Orchestrator", "ORCHESTRATOR", "Plans engineering requests.", "PLANS_ONLY", ["artifacts.generate"]),
    _a("producteng", "engineering", "Data Product Engineer", "SPECIALIST", "Generates inspectable, traceable, never-activated artifact packages.", "LOCAL_DRAFT", ["artifacts.generate"]),
    _a("modeler", "engineering", "Datasphere Modeler", "SPECIALIST", "Five-layer model specification, grain checks and SQL functional check.", "LOCAL_DRAFT", ["model.layers"]),
    _a("validator", "engineering", "Technical Validator", "SPECIALIST", "Offline validation; live-only checks reported as not run.", "READ", ["validation.run"]),
    _a("orch.recon", "recon", "Reconciliation Orchestrator", "ORCHESTRATOR", "Plans reconciliation requests.", "PLANS_ONLY", ["recon.level"]),
    _a("recon123", "recon", "Level Reconciler", "SPECIALIST", "Source-to-acquisition, acquisition-to-model, end-to-end.", "READ", ["recon.level", "recon.golden"]),
    _a("cfin", "recon", "Central Finance Guard", "SPECIALIST", "Source-to-CFIN, BW-to-BDC and duplicate-posting prevention.", "READ", ["recon.cfin_guard"]),
    _a("investigator", "recon", "Variance Investigator", "SPECIALIST", "Injects or reads a difference and drills to source and target records.", "READ_SIMULATED", ["recon.investigate"]),
    _a("orch.gov", "governance", "Governance Orchestrator", "ORCHESTRATOR", "Plans governance requests; refuses write actions.", "PLANS_ONLY", ["exec.plan"]),
    _a("planner", "governance", "Execution Planner", "SPECIALIST", "15-step dependency-aware plan per mode with states.", "READ", ["exec.plan"]),
    _a("gatekeeper", "governance", "Approval Gatekeeper", "SPECIALIST", "Drafts a proposal only; refuses deploy, activate, transport, publish, post.", "DRAFT_ONLY", ["approvals.draft"]),
    _a("auditor", "governance", "Evidence & Release Auditor", "SPECIALIST", "Gates, status dimensions and what is still HOLD.", "READ", ["gates.status"]),
]
_AGENT = {a["id"]: a for a in AGENTS}


def _scn(res: dict, args: dict) -> dict:
    s = args.get("scenario") or "A"
    if s not in res["scenarios"]:
        raise KeyError(f"scenario {s} not in results")
    return res["scenarios"][s]


def _req(s: dict, args: dict) -> str:
    r = args.get("requirement") or args.get("group") or "POI"
    return r if r.startswith("REQ-") else next((a["requirement"] for a in s["analysis"] if a["group"] == r), r)


# ---- tool handlers (each returns {"summary": str, "data": dict}) --------------------------------------------------

def t_scope(res, a):
    text = a.get("request", "")
    sc = "B" if re.search(r"\b(scenario b|multi|cfin|central finance|ecc|bw)\b", text, re.I) else "A"
    mode = "DEMO"
    return {"summary": f"Resolved scenario {sc}, mode {mode} (default; no live connection)", "data": {"scenario": sc, "mode": mode, "route": "P1 local workbench"}}


def t_inventory(res, a):
    s = _scn(res, a)
    return {"summary": f"{len(s['inventory'])} logical object groups (discovery reference candidates, not verified released views)", "data": {"inventory": s["inventory"]}}


def t_objects(res, a):
    s = _scn(res, a)
    objs = [o for o in s["objects"] if not a.get("system") or o["system"] == a["system"]]
    return {"summary": f"{len(objs)} discovered objects" + (f" in {a['system']}" if a.get("system") else ""), "data": {"count": len(objs), "sample": [{k: o[k] for k in ("id", "obj_type", "release", "api_state", "evidence")} for o in objs[:12]]}}


def t_graph(res, a):
    d = _scn(res, a)["dependencies"]
    return {"summary": f"{len(d['nodes'])} nodes, {len(d['edges'])} edges, {len(d['cycles'])} cycles, {len(d['unresolved'])} unresolved reported", "data": {"unresolved": d["unresolved"], "cycles": d["cycles"], "truncated": d["truncated"]}}


def t_catalog(res, a):
    s = _scn(res, a)
    rid = _req(s, a)
    an = next(x for x in s["analysis"] if x["requirement"] == rid)
    prod = [c["product"] for c in an["candidates"]]
    return {"summary": f"{rid}: catalog state {an['catalog_state']}; candidates {prod or 'none'}; primary gap {an['primary_gap']}", "data": {"catalog_state": an["catalog_state"], "candidates": prod}}


def t_synth(res, a):
    s = _scn(res, a)
    m = s["metrics"]
    return {"summary": f"seed {s['seed']}, {m['po_count']} POs, {m['journal_lines']} journal lines; evidence mode {s['evidence_mode']}", "data": {"seed": s["seed"], "metrics": m}}


def t_gap(res, a):
    s = _scn(res, a)
    rows = [x for x in s["analysis"] if not a.get("group") or x["group"] == a["group"]]
    from collections import Counter
    c = Counter(x["primary_gap"] for x in rows)
    cov = s["coverage"]
    return {"summary": f"{len(rows)} requirement(s): {dict(c)}; field coverage {cov['numerator']}/{cov['denominator']} comparable ({cov['percent']}%); not AI-verified", "data": {"gaps": dict(c), "coverage": cov}}


def t_decide(res, a):
    s = _scn(res, a)
    rid = _req(s, a)
    d = next(x for x in s["decisions"] if x["requirement"] == rid)
    return {"summary": f"{rid}: {d['decision']} - {d['reason']}", "data": {"decision": d["decision"], "steps": d["implementation_steps"], "approvals": d["approvals"], "alternative": d["alternative"]}, "needs_approval": d["approvals"]}


def t_rules_list(res, a):
    s = _scn(res, a)
    r = s["rules"]["after"]
    return {"summary": f"{len(r)} rules; before approval {s['metrics']['unresolved_business_rules_before']} unresolved, after {s['metrics']['unresolved_business_rules_after']} (synthetic-scope approvals)", "data": {"rules": [{k: x[k] for k in ("rule_id", "status", "approval_scope", "owner")} for x in r]}}


def t_rules_draft(res, a):
    return {"summary": "Draft rule saved as PROPOSED; a named human approver with passing test cases is required. The agent cannot approve.", "data": {"status": "PROPOSED"}, "needs_approval": ["Finance owner (named human)"]}


def t_logic(res, a):
    l = _scn(res, a)["logic_discovery"]
    return {"summary": f"Category A items {len(l['category_A'])}; Category B markers {len(l['category_B'])}; Category C kept as explicit rules", "data": {"A": l["category_A"][:6], "B": l["category_B"][:4]}}


def t_artifacts(res, a):
    s = _scn(res, a)
    rid = _req(s, a)
    p = next((x for x in s["packages"] if x["manifest"]["requirement"] == rid), None)
    if not p:
        return {"summary": f"{rid}: no engineering package (decision is not customer-managed)", "data": {}}
    return {"summary": f"{rid}: {len(p['files'])} files GENERATED ({p['manifest']['metadata_label']}); activated={p['manifest']['activated']}, published={p['manifest']['published']}", "data": {"files": list(p["files"]), "manifest": p["manifest"]}}


def t_model(res, a):
    s = _scn(res, a)
    return {"summary": f"5-layer model GENERATED (not deployed); grain {s['grain']['status']}; SQL functional check {s['sqlite']['status']}; naive join multiplies PO value x{s['sqlite']['fan_out_demonstration']['naive_join_po_value'] / max(s['sqlite']['fan_out_demonstration']['correct_po_value'], 1):.1f}", "data": {"grain": s["grain"], "sqlite": s["sqlite"]["status"]}}


def t_validation(res, a):
    v = _scn(res, a)["validation"]
    n = sum(1 for c in v["checks"] if c["status"] == "NOT_RUN")
    return {"summary": f"offline {v['offline_status']}; {n} live-only checks NOT_RUN", "data": {"offline": v["offline_status"], "live": v["live_status"]}}


def t_recon_level(res, a):
    r = _scn(res, a)["recon"]
    lv = r["levels"]
    return {"summary": "; ".join(f"{k}: {v['status']}" for k, v in lv.items() if v) + f"; overall {r['overall']} (synthetic)", "data": {k: v["status"] for k, v in lv.items() if v}}


def t_golden(res, a):
    g = _scn(res, a)["recon"]["golden"]
    return {"summary": f"golden transaction {g['status']}: {sum(1 for r in g['rows'] if r['status'] == 'PASS')}/{len(g['rows'])} hand-authored expectations matched by both paths", "data": {"rows": g["rows"][:6]}}


def t_cfin(res, a):
    s = _scn(res, a)
    if "B" not in res["scenarios"] or s["scenario"] != "B":
        return {"summary": "Central Finance guard applies to Scenario B only", "data": {}}
    r = s["recon"]
    nv = r["naive_double_count"]
    return {"summary": f"source->CFIN {r['levels']['B1']['status']}; BW->BDC {r['levels']['B4']['status']}; summing source+CFIN FI is detected: {nv['status']} ({nv['differences_count']} differences)", "data": {"naive": nv["status"]}}


def t_investigate(res, a):
    s = _scn(res, a)
    d = a.get("defect") or "AMOUNT_TAMPER"
    row = next((x for x in s["recon"]["defect_matrix"] if x["defect"] == d), None)
    if not row:
        return {"summary": f"{d} not in the {s['scenario']} defect matrix", "data": {}}
    return {"summary": f"{d}: detected={row['detected']} by {row['detected_by']}; {row['l3_differences']} material difference(s) at Level 3; applied {row['applied']}", "data": row}


def t_plan(res, a):
    s = _scn(res, a)
    mode = a.get("mode", "DEMO")
    p = s["plan"][mode]
    from collections import Counter
    c = Counter(x["state"] for x in p)
    return {"summary": f"{mode}: {dict(c)}", "data": {"steps": [{k: x[k] for k in ("step", "name", "state", "detail")} for x in p]}}


def t_draft(res, a):
    act = a.get("action", "change")
    return {"summary": f"Proposal drafted for '{act}'. Not executed: SAP writes, activation, transports, deployment and publication need explicit human authorization outside this suite.", "data": {"status": "DRAFT_ONLY"}, "needs_approval": ["Owner authorization", "Transport owner", "Non-production target confirmation"]}


def t_gates(res, a):
    g = res["gates"]
    ok = sum(1 for x in g if x["status"] == "PASS")
    return {"summary": f"{ok}/{len(g)} gates PASS; {res['overall_release']}; live SAP/BDC validation HOLD; Finance validation HOLD / INSUFFICIENT_EVIDENCE", "data": {"gates": {x["id"]: x["status"] for x in g}, "status": res["status"]}}


TOOLS: dict[str, dict] = {}


def _t(name, agent, desc, schema, authority, layer, fn: Callable):
    TOOLS[name] = {"name": name, "agent": agent, "description": desc, "input_schema": schema, "authority": authority, "layer": layer, "fn": fn}


_S = {"scenario": "A|B"}
_t("scope.resolve_request", "scope", "Resolve scenario, mode and route from plain text", {"request": "string"}, "READ", "Orchestrator", t_scope)
_t("discovery.inventory", "objects", "The 20 P2P object groups as discovery references", _S, "READ_SIMULATED", "SAP metadata (synthetic)", t_inventory)
_t("discovery.list_objects", "objects", "Discovered objects with release, API state and evidence", {**_S, "system": "string?"}, "READ_SIMULATED", "SAP metadata (synthetic)", t_objects)
_t("discovery.dependency_graph", "graph", "Bounded recursive dependency resolution", _S, "READ_SIMULATED", "SAP metadata (synthetic)", t_graph)
_t("catalog.lookup", "catalog", "Catalog candidates and evidence state for a requirement", {**_S, "requirement": "string"}, "READ_SIMULATED", "Catalog (synthetic)", t_catalog)
_t("data.synthetic_summary", "synth", "Seed, counts and evidence mode", _S, "READ", "Evidence store", t_synth)
_t("gap.analyze", "delta", "Gap classes and coverage", {**_S, "group": "string?"}, "READ", "Domain engine", t_gap)
_t("decision.recommend", "advisor", "Deterministic extensibility decision", {**_S, "requirement": "string"}, "READ", "Domain engine", t_decide)
_t("rules.list", "rules", "Business rules and approval state", _S, "READ", "Domain engine", t_rules_list)
_t("rules.draft", "rules", "Draft a PROPOSED rule (cannot approve)", {**_S, "rule": "object"}, "LOCAL_DRAFT", "Domain engine", t_rules_draft)
_t("logic.discover", "logic", "Category A/B/C logic discovery", _S, "READ", "Domain engine", t_logic)
_t("artifacts.generate", "producteng", "Engineering package for a customer-managed decision", {**_S, "requirement": "string"}, "LOCAL_DRAFT", "Domain engine", t_artifacts)
_t("model.layers", "modeler", "Datasphere layers, grain check, SQL functional check", _S, "LOCAL_DRAFT", "Domain engine", t_model)
_t("validation.run", "validator", "Technical validation results", _S, "READ", "Domain engine", t_validation)
_t("recon.level", "recon123", "Reconciliation levels 1-3 (+B1/B4)", _S, "READ", "Domain engine", t_recon_level)
_t("recon.golden", "recon123", "Golden transaction check", _S, "READ", "Domain engine", t_golden)
_t("recon.cfin_guard", "cfin", "Central Finance and duplicate-posting guard", _S, "READ", "Domain engine", t_cfin)
_t("recon.investigate", "investigator", "Injected-defect detection and drill-down", {**_S, "defect": "string?"}, "READ_SIMULATED", "Domain engine", t_investigate)
_t("exec.plan", "planner", "15-step plan for a mode", {**_S, "mode": "DEMO|CONNECTED_READ_ONLY|CONTROLLED_EXECUTION"}, "READ", "Domain engine", t_plan)
_t("approvals.draft", "gatekeeper", "Draft a proposal; never executes", {"action": "string"}, "DRAFT_ONLY", "Approval queue", t_draft)
_t("gates.status", "auditor", "Acceptance gates and status dimensions", {}, "READ", "Evidence store", t_gates)

WRITE_INTENT = re.compile(r"\b(deploy\w*|activat\w*|transport\w*|publish\w*|post(ing)?|release to|push|install\w*|delete|execute in sap|write)\b", re.I)
INTENTS = [
    ("write", WRITE_INTENT, "governance", ["approvals.draft", "exec.plan"]),
    ("full", re.compile(r"\b(end[- ]to[- ]end|walkthrough|full demo|everything)\b", re.I), "discovery",
     ["scope.resolve_request", "discovery.dependency_graph", "catalog.lookup", "gap.analyze", "decision.recommend", "artifacts.generate", "model.layers",
      "validation.run", "recon.level", "recon.golden", "gates.status"]),
    ("readiness", re.compile(r"\b(ready|readiness|gate|status|evidence|release)\b", re.I), "governance", ["gates.status", "exec.plan"]),
    ("recon", re.compile(r"\b(reconcil\w*|recon|golden|variance|difference|inject|detect|drill|duplicate|central finance|cfin|bw)\b", re.I), "recon",
     ["recon.level", "recon.golden", "recon.cfin_guard", "recon.investigate"]),
    ("engineering", re.compile(r"\b(generat\w*|artifact\w*|cds|odp|datasource|model\w*|datasphere|semantic|validat\w*|technical)\b", re.I), "engineering",
     ["artifacts.generate", "model.layers", "validation.run"]),
    ("rules", re.compile(r"\b(rule\w*|logic|approve\w*|approval\w*)\b", re.I), "gap", ["rules.list", "logic.discover", "rules.draft"]),
    ("gap", re.compile(r"\b(gap\w*|delta|coverage|field\w*|compare|extend|extension\w*|decision\w*|decide|recommend\w*|reuse)\b", re.I), "gap",
     ["gap.analyze", "decision.recommend"]),
    ("discovery", re.compile(r"\b(discover\w*|object\w*|dependenc\w*|graph|catalog|product\w*|scope|synthetic|data)\b", re.I), "discovery",
     ["scope.resolve_request", "discovery.inventory", "discovery.dependency_graph", "catalog.lookup", "data.synthetic_summary"]),
]
EXAMPLES = ["Run the end-to-end walkthrough for scenario A", "Show dependencies and catalog evidence for the purchase order item",
            "Which gaps exist and what should we extend?", "Reconcile scenario B and prove duplicate Finance postings are prevented",
            "Inject an amount difference and investigate it", "Generate the customer-managed product package for the invoice item",
            "Deploy the artifacts to the S/4HANA system", "Are we release ready?"]


def route(request: str) -> dict:
    for name, rx, fam, tools in INTENTS:
        if rx.search(request):
            return {"intent": name, "family": fam, "tools": tools, "refused": name == "write"}
    return {"intent": "discovery", "family": "discovery", "tools": ["scope.resolve_request", "gates.status"], "refused": False}


def _args(request: str, tool: str, res: dict) -> dict:
    sc = "B" if re.search(r"\b(scenario b|\bb\b|cfin|central finance|multi|ecc|bw)\b", request, re.I) and "B" in res["scenarios"] else "A"
    a: dict[str, Any] = {"scenario": sc, "request": request}
    m = re.search(r"\b(invoice item|supplier invoice|purchase order item|po item|goods receipt|goods movement|journal|universal journal|po history|bp|supplier)\b", request, re.I)
    grp = {"invoice item": "INVI", "supplier invoice": "INVI", "purchase order item": "POI", "po item": "POI", "goods receipt": "MATDOC",
           "goods movement": "MATDOC", "journal": "ACDOCA", "universal journal": "ACDOCA", "po history": "POHIST", "bp": "BP", "supplier": "BP"}
    a["group"] = grp.get(m.group(1).lower(), "POI") if m else ("INVI" if tool == "artifacts.generate" else "POI")
    a["requirement"] = f"REQ-{'S4A'}-{a['group']}"
    for d in ("AMOUNT_TAMPER", "DROPPED_INVOICE", "DUPLICATED_JOURNAL_LINE", "WRONG_CURRENCY", "DELAYED_CFIN_REPLICATION", "MISSING_SUPPLIER_MAPPING"):
        if d.replace("_", " ").lower() in request.lower() or d.lower() in request.lower():
            a["defect"] = d
    if "amount" in request.lower() and "defect" not in a:
        a["defect"] = "AMOUNT_TAMPER"
    a["action"] = request
    if tool == "exec.plan":
        a["mode"] = "CONTROLLED_EXECUTION" if WRITE_INTENT.search(request) else "DEMO"
    return a


def run_request(request: str, res: dict, scenario: str | None = None) -> dict:
    """Plan, call tools, return trace. Every call is recorded; refusals are explicit."""
    r = route(request)
    trace, approvals = [], []
    layers = ["UI", "Orchestrator"]
    for i, tname in enumerate(r["tools"], 1):
        tool = TOOLS[tname]
        agent = _AGENT[tool["agent"]]
        args = _args(request, tname, res)
        if scenario:
            args["scenario"] = scenario
        try:
            out = tool["fn"](res, args)
            status = "OK"
        except Exception as e:  # noqa: BLE001 - surfaced in the trace
            out, status = {"summary": f"tool error: {e}", "data": {}}, "ERROR"
        if tool["layer"] not in layers:
            layers.append(tool["layer"])
        approvals += out.get("needs_approval", [])
        trace.append({"step": i, "agent": agent["name"], "agent_id": agent["id"], "family": agent["family"], "tool": tname, "authority": AUTHORITY[tool["authority"]],
                      "args": {k: v for k, v in args.items() if k not in ("request", "action")}, "status": status, "summary": out["summary"], "layer": tool["layer"], "data": out.get("data", {})})
    if "Evidence store" not in layers:
        layers.append("Evidence store")
    layers.append("SAP connectors: NOT REACHED (DEMO mode, no live interface)")
    refusal = ("Write-type request recognised. This suite can draft a proposal and show the plan, but cannot execute SAP writes, activation, transports, "
               "deployment or publication. A named human must authorize those separately.") if r["refused"] else None
    return {"request": request, "route": r, "plan": [f"{t['agent']} -> {t['tool']}" for t in trace], "trace": trace, "layers_reached": layers,
            "approvals_needed": sorted(set(approvals)), "refusal": refusal, "answer": " | ".join(t["summary"] for t in trace)[:1800]}


def catalog_view() -> list[dict]:
    out = []
    for f in FAMILIES:
        out.append({**f, "agents": [{**a, "authority_label": AUTHORITY[a["authority"]], "tool_count": len(a["tools"])} for a in AGENTS if a["family"] == f["id"]]})
    return out


def tool_catalog() -> list[dict]:
    return [{"tool": t["name"], "agent": _AGENT[t["agent"]]["name"], "authority": AUTHORITY[t["authority"]], "layer": t["layer"], "description": t["description"],
             "input": json.dumps(t["input_schema"])} for t in TOOLS.values()]
