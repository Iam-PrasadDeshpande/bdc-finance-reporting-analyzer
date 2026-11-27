"""BDC Transition Agent Suite: three agents, MCP-style typed tools, a deterministic orchestrator.

  S/4HANA agent            customizations in standard SAP, the delta register, the solution (extend, or a new backend CDS view)
  BDC & Datasphere agent   SAP-delivered data products, comparison with SAP objects, flows, transformation, semantic model
  Utility agent            rules and approvals, validation, reconciliation, execution plan, gates, end-to-end result, refusal of writes

The orchestrator plans a plain-language request, routes it to the lead agent and calls typed tools. Agents READ persisted results or draft
locally; none can write to SAP, activate, transport, deploy or publish. The router is rule-based (deterministic); an LLM can later replace
it behind the same tool contract without widening any authority.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Callable

from . import delta, ontology

AUTHORITY = {"PLANS_ONLY": "plans only", "READ": "read", "READ_SIMULATED": "read (simulated)", "LOCAL_DRAFT": "read + local draft",
             "DRAFT_ONLY": "draft only"}
AGENTS = [{**x, "role": "AGENT"} for x in delta.AGENT3]
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


def t_delta(res, a):
    s = _scn(res, a)
    sm = delta.summary(s)
    parts = ", ".join(f"{delta.DELTA_TYPES[k][0].lower()} {v}" for k, v in sorted(sm["by_type"].items(), key=lambda kv: -kv[1]))
    return {"summary": f"{sm['objects']} standard SAP objects compared with SAP-delivered products: {sm['no_delta']} with no delta; {sm['customizations']} customization(s) found "
                       f"(custom fields, customer objects), {sm['rule_differences']} business-rule difference(s), {sm['coverage_gaps']} product coverage gap(s); "
                       f"{sm['logic_markers']} custom-logic marker(s) to review. By type: {parts}", "data": {"by_type": sm["by_type"], "customizations": sm["customizations"]}}


def t_solution(res, a):
    s = _scn(res, a)
    sm = delta.summary(s)
    rows = delta.register(s)
    appr = sorted({x for r in rows for x in r["approvals"]})
    parts = "; ".join(f"{k}: {v}" for k, v in sorted(sm["routes"].items(), key=lambda kv: -kv[1]))
    return {"summary": f"Solution routes - {parts}", "data": {"routes": sm["routes"]}, "needs_approval": appr}


def t_dsp(res, a):
    s = _scn(res, a)
    p = delta.dsp_plan(s)
    sem, sim = p["semantic"], p["simulation"]
    return {"summary": f"{len(p['replication_flows'])} replication flow(s), {len(p['harmonization'])} harmonization and {len(p['transformation'])} transformation view(s), semantic model "
                       f"{len(sem['facts'])} facts / {len(sem['dimensions'])} dimensions / {len(sem['analytic_models'])} analytic models; offline simulation: grain {sim['grain']}, "
                       f"SQL check {sim['sql']}; nothing deployed", "data": {"flows": len(p["replication_flows"]), "simulation": sim["sql"]}}


def t_journey(res, a):
    j = delta.journey(res, _scn(res, a)["scenario"])
    rc = ", ".join(f"{k} {v}" for k, v in j["recon"].items() if v != "-")
    return {"summary": f"End to end (synthetic): {j['delta']['objects']} objects compared, {j['delta']['no_delta']} no delta, {j['delta']['customizations']} customization(s); {j['packages']} package(s) generated; "
                       f"reconciliation {rc}; golden {j['golden_rows']}; defects detected {j['defects']}; gates {j['gates']}. Live SAP/BDC validation HOLD; Finance validation HOLD / INSUFFICIENT_EVIDENCE",
            "data": {"recon": j["recon"], "gates": j["gates"]}}


def t_onto(res, a):
    o = ontology.build(res, _scn(res, a)["scenario"])
    c = o["counts"]
    rel = ", ".join(f"{k} {v}" for k, v in sorted(o["by_relation"].items(), key=lambda kv: -kv[1])[:5])
    return {"summary": f"Ontology (data flow) for {c['objects']} SAP objects: {c['reused']} reused, {c['extended']} extended, {c['created']} new backend view / customer-managed product, "
                       f"{c['datasphere']} solved in Datasphere, {c['unresolved']} unresolved; {o['nodes']} nodes and {len(o['edges'])} typed relations ({rel}) from SAP object to proof",
            "data": {"counts": c, "by_relation": o["by_relation"]}}


TOOLS: dict[str, dict] = {}


def _t(name, agent, desc, schema, authority, layer, fn: Callable):
    TOOLS[name] = {"name": name, "agent": agent, "description": desc, "input_schema": schema, "authority": authority, "layer": layer, "fn": fn}


_S = {"scenario": "A|B"}
_t("scope.resolve_request", "s4", "Resolve scenario, mode and route from plain text", {"request": "string"}, "READ", "Orchestrator", t_scope)
_t("discovery.inventory", "s4", "The 20 P2P object groups as discovery references", _S, "READ_SIMULATED", "SAP metadata (synthetic)", t_inventory)
_t("discovery.list_objects", "s4", "Discovered objects with release, API state and evidence", {**_S, "system": "string?"}, "READ_SIMULATED", "SAP metadata (synthetic)", t_objects)
_t("discovery.dependency_graph", "s4", "Bounded recursive dependency resolution", _S, "READ_SIMULATED", "SAP metadata (synthetic)", t_graph)
_t("catalog.lookup", "bdc", "Catalog candidates and evidence state for a requirement", {**_S, "requirement": "string"}, "READ_SIMULATED", "Catalog (synthetic)", t_catalog)
_t("data.synthetic_summary", "s4", "Seed, counts and evidence mode", _S, "READ", "Evidence store", t_synth)
_t("gap.analyze", "bdc", "Gap classes and coverage", {**_S, "group": "string?"}, "READ", "Domain engine", t_gap)
_t("decision.recommend", "s4", "Deterministic extensibility decision", {**_S, "requirement": "string"}, "READ", "Domain engine", t_decide)
_t("rules.list", "utility", "Business rules and approval state", _S, "READ", "Domain engine", t_rules_list)
_t("rules.draft", "utility", "Draft a PROPOSED rule (cannot approve)", {**_S, "rule": "object"}, "LOCAL_DRAFT", "Domain engine", t_rules_draft)
_t("logic.discover", "s4", "Category A/B/C logic discovery", _S, "READ", "Domain engine", t_logic)
_t("artifacts.generate", "s4", "Engineering package for a customer-managed decision", {**_S, "requirement": "string"}, "LOCAL_DRAFT", "Domain engine", t_artifacts)
_t("model.layers", "bdc", "Datasphere layers, grain check, SQL functional check", _S, "LOCAL_DRAFT", "Domain engine", t_model)
_t("validation.run", "utility", "Technical validation results", _S, "READ", "Domain engine", t_validation)
_t("recon.level", "utility", "Reconciliation levels 1-3 (+B1/B4)", _S, "READ", "Domain engine", t_recon_level)
_t("recon.golden", "utility", "Golden transaction check", _S, "READ", "Domain engine", t_golden)
_t("recon.cfin_guard", "utility", "Central Finance and duplicate-posting guard", _S, "READ", "Domain engine", t_cfin)
_t("recon.investigate", "utility", "Injected-defect detection and drill-down", {**_S, "defect": "string?"}, "READ_SIMULATED", "Domain engine", t_investigate)
_t("exec.plan", "utility", "15-step plan for a mode", {**_S, "mode": "DEMO|CONNECTED_READ_ONLY|CONTROLLED_EXECUTION"}, "READ", "Domain engine", t_plan)
_t("approvals.draft", "utility", "Draft a proposal; never executes", {"action": "string"}, "DRAFT_ONLY", "Approval queue", t_draft)
_t("gates.status", "utility", "Acceptance gates and status dimensions", {}, "READ", "Evidence store", t_gates)

_t("delta.register", "s4", "Delta register: customizations in standard SAP vs the SAP-delivered data products", _S, "READ_SIMULATED", "SAP metadata (synthetic)", t_delta)
_t("delta.solution", "s4", "Solution route per delta: extend the product, or new backend CDS view + customer-managed model", _S, "READ", "Domain engine", t_solution)
_t("dsp.plan", "bdc", "Datasphere plan: replication flows, transformation, semantic model, offline simulation", _S, "LOCAL_DRAFT", "Domain engine", t_dsp)
_t("ontology.lineage", "bdc", "Ontology: how data flows from the SAP object to the proof, and how the components are wired", _S, "READ", "Evidence store", t_onto)
_t("result.journey", "utility", "End-to-end result of the delta journey", _S, "READ", "Evidence store", t_journey)

_WRITE_WORDS = (r"deploy\w*|activat\w*|transport\w*|publish\w*|post(ing)?(?![-\w])|release (to|the|into)|push\w*|install\w*|delete\w*|remov\w*|drop|execute|execution in|write|"
                r"ship\w*|promot\w*|appl(y|ies|ied)|roll ?out|go live|go-live|import\w*|commit\w*|migrat\w*|provision\w*|create (it |them |the \w+ )?in (sap|datasphere|bdc|s/?4)|"
                r"run (it )?in prod\w*|bereitstell\w*|aktivier\w*|freigeb\w*|loesch\w*|veroeffentlich\w*|transportier\w*|despleg\w*|activar|publicar|deployer|activer|publier")
WRITE_INTENT = re.compile(r"\b(" + _WRITE_WORDS + r")", re.I)
_ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue"})
ALLOWED_AUTHORITY = {"READ", "READ_SIMULATED", "LOCAL_DRAFT", "DRAFT_ONLY"}  # a tool with any other authority is refused at call time


def _normalise(text: str) -> str:
    return _ZERO_WIDTH.sub("", unicodedata.normalize("NFKC", text)).lower()


def _is_write(text: str) -> bool:
    t = _normalise(text)
    return bool(WRITE_INTENT.search(t) or WRITE_INTENT.search(t.translate(_LEET)))


INTENTS = [
    ("write", None, "utility", ["approvals.draft", "exec.plan"]),  # matched by _is_write (normalised, fail closed)
    ("full", re.compile(r"\b(end[- ]to[- ]end|walkthrough|full demo|everything|overall result)\b", re.I), "s4",
     ["scope.resolve_request", "delta.register", "catalog.lookup", "gap.analyze", "delta.solution", "artifacts.generate", "dsp.plan", "model.layers", "ontology.lineage",
      "validation.run", "recon.level", "recon.golden", "result.journey"]),
    ("readiness", re.compile(r"\b(ready|readiness|gate|status|evidence|release)\b", re.I), "utility", ["gates.status", "exec.plan"]),
    ("recon", re.compile(r"\b(reconcil\w*|recon|golden|variance|difference|inject|detect|drill|duplicate|central finance|cfin|bw)\b", re.I), "utility",
     ["recon.level", "recon.golden", "recon.cfin_guard", "recon.investigate"]),
    ("ontology", re.compile(r"\b(ontolog\w*|lineage|wiring|wired|data flows?|trace)\b", re.I), "bdc", ["ontology.lineage"]),
    ("datasphere", re.compile(r"\b(datasphere|replication|flows?|semantic|transformation\w*|harmoni\w*|model\w*|simulat\w*)\b", re.I), "bdc", ["dsp.plan", "model.layers"]),
    ("solution", re.compile(r"\b(generat\w*|artifact\w*|cds|odp|datasource|solution\w*|solv\w*|extend|extension\w*|key-user|customer-managed|build|decision\w*|decide|recommend\w*|reuse)\b", re.I), "s4",
     ["delta.solution", "decision.recommend", "artifacts.generate"]),
    ("validation", re.compile(r"\b(validat\w*|technical)\b", re.I), "utility", ["validation.run"]),
    ("rules", re.compile(r"\b(rule\w*|logic|approve\w*|approval\w*)\b", re.I), "utility", ["rules.list", "logic.discover", "rules.draft"]),
    ("delta", re.compile(r"\b(delta|custom\w*|gap\w*|coverage|field\w*|compare|standard)\b", re.I), "s4", ["delta.register", "catalog.lookup", "gap.analyze"]),
    ("discovery", re.compile(r"\b(discover\w*|object\w*|dependenc\w*|graph|catalog|product\w*|scope|synthetic|data)\b", re.I), "s4",
     ["scope.resolve_request", "discovery.inventory", "discovery.dependency_graph", "catalog.lookup", "data.synthetic_summary"]),
]
EXAMPLES = ["Show the delta: what is customized in standard SAP and how was it found?", "Compare the purchase order item with the SAP-delivered data product",
            "How should we solve each delta: extend the product or build a new CDS view?", "Generate the customer-managed product package for the invoice item",
            "Which Datasphere flows and models are needed?", "Reconcile scenario B and prove duplicate Finance postings are prevented",
            "Give me the end-to-end result for scenario A", "Show how data flows from the SAP object to the report (ontology)", "Deploy the artifacts to the S/4HANA system"]


def route(request: str) -> dict:
    """Deterministic, rule-based routing (no LLM). Write-like requests are refused first; a request that matches nothing is not executed."""
    if _is_write(request):
        return {"intent": "write", "agent": "utility", "tools": ["approvals.draft", "exec.plan"], "refused": True}
    t = _normalise(request)
    for name, rx, agent, tools in INTENTS:
        if rx is not None and rx.search(t):
            return {"intent": name, "agent": agent, "tools": tools, "refused": False}
    return {"intent": "unrecognized", "agent": "s4", "tools": ["scope.resolve_request"], "refused": False}


def _args(request: str, tool: str, res: dict) -> dict:
    sc = "B" if re.search(r"\b(scenario b|cfin|central finance|multi|ecc|bw)\b", request, re.I) and "B" in res["scenarios"] else "A"
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
        a["mode"] = "CONTROLLED_EXECUTION" if _is_write(request) else "DEMO"
    return a


def run_request(request: str, res: dict, scenario: str | None = None) -> dict:
    """Plan, call tools, return trace. Every call is recorded; refusals are explicit."""
    r = route(request)
    trace, approvals = [], []
    layers = ["UI", "Orchestrator"]
    for i, tname in enumerate(r["tools"], 1):
        tool = TOOLS.get(tname)
        if tool is None:
            trace.append({"step": i, "agent": "-", "agent_id": "-", "tool": tname, "authority": "-", "args": {}, "status": "ERROR", "summary": "unknown tool refused", "layer": "-", "data": {}})
            continue
        agent = _AGENT[tool["agent"]]
        args = _args(request, tname, res)
        if scenario:
            args["scenario"] = scenario
        if tool["authority"] not in ALLOWED_AUTHORITY:
            out, status = {"summary": f"refused: authority {tool['authority']} is not allowed for any tool", "data": {}}, "REFUSED"
        else:
            try:
                out = tool["fn"](res, args)
                status = "OK"
            except Exception as e:  # noqa: BLE001 - surfaced in the trace without the exception text
                out, status = {"summary": f"tool error ({type(e).__name__}); details are not shown", "data": {}}, "ERROR"
        if tool["layer"] not in layers:
            layers.append(tool["layer"])
        approvals += out.get("needs_approval", [])
        trace.append({"step": i, "agent": agent["name"], "agent_id": agent["id"], "tool": tname, "authority": AUTHORITY.get(tool["authority"], tool["authority"]),
                      "args": {k: v for k, v in args.items() if k not in ("request", "action")}, "status": status, "summary": out["summary"], "layer": tool["layer"], "data": out.get("data", {})})
    if "Evidence store" not in layers:
        layers.append("Evidence store")
    layers.append("SAP connectors: NOT REACHED (DEMO mode, no live interface)")
    refusal = ("Write-type request recognised. This suite can draft a proposal and show the plan, but cannot execute SAP writes, activation, transports, "
               "deployment or publication. A named human must authorize those separately.") if r["refused"] else None
    notice = ("Request not recognised: nothing was executed beyond resolving the scope. Rephrase it as a question about the delta, the solution, the Datasphere plan, "
              "the reconciliation or the ontology.") if r["intent"] == "unrecognized" else None
    return {"request": request, "route": r, "plan": [f"{t['agent']} -> {t['tool']}" for t in trace], "trace": trace, "layers_reached": layers,
            "approvals_needed": sorted(set(approvals)), "refusal": refusal, "notice": notice,
            "answer": "SYNTHETIC DEMO, not tenant-verified. " + " | ".join(t["summary"] for t in trace)[:1700]}


def catalog_view() -> list[dict]:
    out = []
    for ag in AGENTS:
        tools = [t for t in TOOLS.values() if t["agent"] == ag["id"]]
        out.append({**ag, "authority_label": AUTHORITY[ag["authority"]], "tool_count": len(tools), "tools": [t["name"] for t in tools],
                    "stage_names": [st["name"] for st in delta.STAGES if st["agent"] == ag["id"]]})
    return out


def tool_catalog() -> list[dict]:
    return [{"tool": t["name"], "agent": _AGENT[t["agent"]]["name"], "authority": AUTHORITY[t["authority"]], "layer": t["layer"], "description": t["description"],
             "input": json.dumps(t["input_schema"])} for t in TOOLS.values()]
