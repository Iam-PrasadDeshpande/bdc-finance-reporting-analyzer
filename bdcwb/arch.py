"""Architecture & operations content: complete architecture options, hosting/registry decisions, selection criteria, decision brief,
ontology, live-run event model and Graphviz diagrams. All options are PROPOSED DESIGNS FOR EVALUATION - NOT TENANT-VERIFIED."""
from __future__ import annotations

BADGE = "PROPOSED DESIGN FOR EVALUATION - NOT TENANT-VERIFIED"
OPTIONS = {
    "P1": {"name": "Local workbench", "tag": "preferred for demo and offline", "preferred": True, "mode": "DEMO",
           "chain": ["UI (Streamlit)", "Orchestrator", "Specialist agents", "Typed tool layer", "Domain engines", "Evidence store", "Synthetic metadata + data"],
           "owns": {"UI, orchestrator, agents, tools, engines": "This project (one Python process)", "Data": "Seeded synthetic fixtures", "SAP access": "None by design"},
           "advantages": ["Reproducible and safe for external architecture demonstrations", "No credentials, no network dependency, nothing to leak", "Same tool contract as P2 and P3"],
           "assumptions": ["Synthetic data only", "Rule-based router (deterministic)", "Evidence in the persisted result set"],
           "limits": ["Cannot prove live SAP behaviour", "Cannot validate tenant entitlement or activation"]},
    "P2": {"name": "Customer-hosted suite with read-only SAP adapters", "tag": "preferred for connected validation", "preferred": True, "mode": "CONNECTED_READ_ONLY",
           "chain": ["UI", "Orchestrator", "Specialist agents", "Typed tool layer", "Read-only adapters (ADT metadata, catalog import, reporting reads)", "SAP source / BDC / Datasphere"],
           "owns": {"Hosting": "Customer-controlled runtime in the non-production network zone", "Credentials": "Customer secret store; never in code, fixtures or logs",
                    "Scope": "Least-privilege read roles; metadata, catalog and report reads only"},
           "advantages": ["Collects real discovery and catalog evidence", "Writes are structurally impossible for the adapters", "Audit log per tool call"],
           "assumptions": ["Verified interfaces exist and are authorized", "Adapter schemas are inspected before use"],
           "limits": ["No adapter is configured in this build (ADT/catalog adapters report UNAVAILABLE)", "Customer approval for hosting and access required"]},
    "P3": {"name": "Gateway-fronted hybrid with registry and approval service", "tag": "conditional, not approved", "preferred": False, "mode": "CONTROLLED_EXECUTION",
           "chain": ["UI", "Orchestrator", "Agent runtime", "Enterprise tool gateway", "Approval service", "Controlled executors (ADT, Datasphere CLI/API)", "Non-production SAP systems"],
           "owns": {"Gateway": "Enterprise platform team", "Approvals": "Named human approvers; per-action, per-session", "Executors": "Only verified interfaces; idempotent and resumable"},
           "advantages": ["Central policy, quota and audit", "Separates agent registration from execution", "Enables authorized engineering changes in non-production"],
           "assumptions": ["Explicit authorization recorded per change", "Environment separation enforced; production never targeted"],
           "limits": ["Not built or approved in this release", "Needs enterprise gateway, registry and approval-service decisions"]},
}
HOSTING = [("Agent runtime hosting", {"P1": "Local Python process", "P2": "Customer VM or platform runtime", "P3": "Managed agent runtime behind the gateway"}),
           ("Tool (MCP-style) exposure", {"P1": "In-process functions", "P2": "Customer-hosted tool server (read-only)", "P3": "Gateway-exposed tools with policy"}),
           ("Agent registration and discovery", {"P1": "Static catalog in code", "P2": "Customer agent registry (optional)", "P3": "Enterprise registry (control plane only)"}),
           ("SAP-facing access", {"P1": "None", "P2": "Read-only adapters", "P3": "Controlled executors after approval"}),
           ("Credential handling", {"P1": "None required", "P2": "Customer secret store", "P3": "Secret store + approval-scoped tokens"}),
           ("Registration never decides hosting", {"P1": "n/a", "P2": "Registry holds metadata only", "P3": "Registry holds metadata only; execution stays in the runtime"})]
CRITERIA = ["Safety (no unintended SAP change)", "Evidence strength", "Time to demonstrate", "Operational effort", "Customer approval effort", "Scalability across systems"]
SCORES = {"P1": ["High", "Low (synthetic)", "High", "Low", "None", "Low"], "P2": ["High", "Medium (live metadata)", "Medium", "Medium", "Medium", "Medium"],
          "P3": ["Medium (needs strong controls)", "High (runtime evidence)", "Low", "High", "High", "High"]}
BRIEF = ("**Recommendation (proposed, not approved):** use P1 now for architecture demonstrations; use P2 for connected discovery and catalog validation once a customer "
         "authorizes read-only access; treat P3 as conditional until a gateway, registry and approval service are approved. All options share one typed tool contract and "
         "one authority model, so moving up the ladder changes hosting and evidence strength, never what an agent may do without a person.")


def concepts() -> list[dict]:
    C = lambda i, l, k, f, g, d: {"id": i, "label": l, "kind": k, "family": f, "grounding": g, "desc": d}  # noqa: E731
    sap, proj = "SAP term, not source-checked", "Project concept"
    return [C("agent", "Agent", "Actor", "shared", proj, "Specialist with typed tools and a fixed authority class"),
            C("orch", "Orchestrator", "Actor", "shared", proj, "Plans a request and calls specialists"),
            C("tool", "Typed tool", "Artifact", "shared", proj, "MCP-style callable with input schema and authority"),
            C("approval", "Human approval", "Process", "shared", proj, "Named person authorizes any change; agents only draft"),
            C("mode", "Execution mode", "Status", "shared", proj, "DEMO, CONNECTED_READ_ONLY or CONTROLLED_EXECUTION"),
            C("evmode", "Evidence class", "Status", "shared", proj, "PUBLISHED_VERIFIED ... SYNTHETIC_FIXTURE / UNKNOWN"),
            C("system", "Source system", "Entity", "discovery", sap, "ECC, S/4HANA, Central Finance, BW/4HANA"),
            C("sapobj", "SAP object", "Entity", "discovery", sap, "CDS view, cube, query, table, DataSource, ADSO"),
            C("graph", "Dependency graph", "Artifact", "discovery", proj, "Recursive, cycle-safe, bounded"),
            C("catalog", "Data product catalog", "Entity", "discovery", sap, "Hub / cockpit / import / snapshot / fixture"),
            C("product", "Data product", "Entity", "discovery", sap, "SAP-managed or customer-managed product"),
            C("entity", "Product entity", "Entity", "discovery", sap, "Entity with fields, keys and grain"),
            C("synth", "Synthetic dataset", "Artifact", "discovery", proj, "Seeded, relationally consistent, golden subset"),
            C("req", "Requirement", "Entity", "gap", proj, "Fields, keys, grain, relationships, delta, authorization"),
            C("gap", "Gap", "Status", "gap", proj, "FIELD, KEY, GRANULARITY, ... CATALOG_UNVERIFIED"),
            C("decision", "Remediation decision", "Process", "gap", proj, "Reuse, extend, customer-managed, enrich, block ..."),
            C("rule", "Business rule", "Rule", "gap", proj, "Explicit, owner-approved, tested"),
            C("logic", "Business logic", "Entity", "gap", proj, "Category A discoverable, B partial, C explicit"),
            C("pkg", "Engineering package", "Artifact", "engineering", proj, "CDS/ODP design, contract, tests; never activated"),
            C("cds", "CDS extraction view", "Artifact", "engineering", sap, "Extraction-enabled CDS (template unless metadata verified)"),
            C("dsp", "Datasphere model", "Artifact", "engineering", sap, "Acquisition, harmonization, transformation, semantic, consumption"),
            C("fact", "Fact (independent grain)", "Entity", "engineering", proj, "Commitment, GR, invoice, journal, open item, clearing"),
            C("techval", "Technical validation", "Process", "engineering", proj, "Offline checks; live checks reported NOT_RUN"),
            C("recon", "Reconciliation", "Process", "recon", proj, "Level 1, 2, 3 plus Central Finance and BW"),
            C("golden", "Golden transaction", "Artifact", "recon", proj, "Hand-authored expected results"),
            C("defect", "Injected defect", "Artifact", "recon", proj, "Deliberate difference to prove detection"),
            C("cfin", "Central Finance document", "Entity", "recon", sap, "Replicated accounting document with source reference"),
            C("authority", "FI source of truth", "Rule", "recon", proj, "Exactly one FI source per company code"),
            C("diff", "Material difference", "Status", "recon", proj, "Beyond approved tolerance; drills to records"),
            C("plan", "Execution plan", "Process", "governance", proj, "15 dependency-ordered steps with states"),
            C("gate", "Acceptance gate", "Rule", "governance", proj, "G01-G15 evaluated from persisted results"),
            C("status", "Release status dimension", "Status", "governance", proj, "Synthetic and live dimensions kept independent"),
            C("audit", "Audit log", "Artifact", "governance", proj, "Credential-safe record of every step")]


def relations() -> list[tuple[str, str, str]]:
    return [("orch", "plans", "agent"), ("agent", "calls", "tool"), ("tool", "runs under", "mode"), ("approval", "authorizes", "decision"),
            ("system", "hosts", "sapobj"), ("sapobj", "depends on", "sapobj"), ("graph", "resolves", "sapobj"), ("catalog", "lists", "product"),
            ("product", "exposes", "entity"), ("evmode", "classifies", "product"), ("synth", "feeds", "recon"), ("req", "derived from", "sapobj"),
            ("req", "compared with", "entity"), ("gap", "found in", "req"), ("decision", "resolves", "gap"), ("rule", "constrains", "logic"),
            ("rule", "approved by", "approval"), ("decision", "may create", "pkg"), ("pkg", "contains", "cds"), ("pkg", "targets", "dsp"),
            ("dsp", "models", "fact"), ("techval", "validates", "pkg"), ("techval", "validates", "dsp"), ("recon", "compares", "fact"),
            ("recon", "uses", "golden"), ("defect", "tests", "recon"), ("cfin", "bridged by", "authority"), ("authority", "protects", "recon"),
            ("recon", "produces", "diff"), ("plan", "sequences", "pkg"), ("plan", "gated by", "approval"), ("gate", "evaluates", "recon"),
            ("gate", "evaluates", "techval"), ("status", "summarizes", "gate"), ("audit", "records", "plan"), ("mode", "restricts", "plan"),
            ("rule", "blocks", "recon")]


def _q(s: str) -> str:
    return '"' + s.replace('"', "'") + '"'


def dot_chain(opt: str, highlight: int | None = None) -> str:
    chain = OPTIONS[opt]["chain"]
    lines = ["digraph G { rankdir=LR; node [shape=box, style=\"rounded,filled\", fontname=Helvetica, fontsize=10, fillcolor=\"#eef4fa\", color=\"#9db4c8\"];"]
    for i, n in enumerate(chain):
        fill = "#cfe8ff" if highlight is not None and i <= highlight else "#eef4fa"
        lines.append(f"n{i} [label={_q(n)}, fillcolor=\"{fill}\"];")
        if i:
            lines.append(f"n{i-1} -> n{i};")
    lines.append("}")
    return "\n".join(lines)


def dot_topology(scn: dict) -> str:
    """Topology derived from the scenario configuration actually run, not a fixed picture."""
    sysd = scn["topology"]["systems"]
    L = ["digraph T { rankdir=LR; node [shape=box, style=\"rounded,filled\", fontname=Helvetica, fontsize=10, fillcolor=\"#eef4fa\"];"]
    col = {"ECC": "#fde9d9", "S4": "#e3f1e3", "CFIN": "#e8e3f5", "BW": "#fff2cc", "BDC": "#d9edf7", "DATASPHERE": "#d9edf7", "DATABRICKS": "#f2f2f2"}
    for k, v in sysd.items():
        L.append(f"{k} [label={_q(k + chr(10) + v['type'] + chr(10) + v['release'][:28])}, fillcolor=\"{col.get(v['type'], '#eef4fa')}\"" + (", style=\"dashed,filled\"" if v.get("optional") else "") + "];")
    for s in scn["topology"]["sources"]:
        L.append(f"{s} -> BDC01 [label=\"data products / extraction\"];")
    auth = scn["topology"]["fi_authority"]
    for key, a in auth.items():
        sys_, cc = key.split("|")
        if a == "CFIN01":
            L.append(f"{sys_} -> CFIN01 [label={_q('FI replication cc ' + cc)}, color=\"#7a5ca8\"];")
    if "CFIN01" in sysd:
        L.append("CFIN01 -> BDC01 [label=\"mapped FI\", color=\"#7a5ca8\"];")
    if "BW401" in sysd:
        L.append("ECC01 -> BW401 [label=\"ODP\"]; BW401 -> BDC01 [label=\"history (reference)\", style=dashed];")
    L.append("BDC01 -> DSP01 [label=\"acquisition\"];")
    if "DBX01" in sysd:
        L.append("DSP01 -> DBX01 [style=dashed, label=\"optional\"];")
    L.append("}")
    return "\n".join(L)


def dot_dependencies(scn: dict, max_edges: int = 90) -> str:
    d = scn["dependencies"]
    L = ["digraph D { rankdir=LR; node [shape=box, style=\"rounded,filled\", fontname=Helvetica, fontsize=9];"]
    for nid, n in d["nodes"].items():
        fill = "#f8d7da" if not n.get("resolved") else ("#fff2cc" if n.get("type") in ("QUERY", "CUBE") else "#eef4fa")
        L.append(f"{_q(nid)} [label={_q(nid.replace(':', chr(10)))}, fillcolor=\"{fill}\"];")
    for e in d["edges"][:max_edges]:
        L.append(f"{_q(e['from'])} -> {_q(e['to'])};")
    L.append("}")
    return "\n".join(L)


def dot_ontology(family: str | None = None) -> str:
    cs = [c for c in concepts() if family in (None, "all") or c["family"] in (family, "shared")]
    ids = {c["id"] for c in cs}
    pal = {"Actor": "#d9edf7", "Entity": "#e3f1e3", "Process": "#e8e3f5", "Rule": "#fde9d9", "Artifact": "#fff2cc", "Status": "#eeeeee"}
    L = ["digraph O { rankdir=LR; node [shape=box, style=\"rounded,filled\", fontname=Helvetica, fontsize=10];"]
    for c in cs:
        L.append(f"{c['id']} [label={_q(c['label'] + chr(10) + c['kind'])}, fillcolor=\"{pal[c['kind']]}\", " + ("style=\"dashed,filled\"" if c["grounding"] == "Project concept" else "style=\"rounded,filled\"") + "];")
    for a, l, b in relations():
        if a in ids and b in ids:
            L.append(f"{a} -> {b} [label={_q(l)}, fontsize=8];")
    L.append("}")
    return "\n".join(L)


def live_events(run: dict) -> list[dict]:
    """Component-communication events derived from the real orchestrator trace of one request."""
    ev = [{"from": "UI", "to": "Orchestrator", "label": run["request"][:60], "state": "REQUEST"}]
    for t in run["trace"]:
        ev.append({"from": "Orchestrator", "to": t["agent"], "label": f"plan step {t['step']}", "state": "PLAN"})
        ev.append({"from": t["agent"], "to": "Typed tool layer", "label": t["tool"], "state": t["status"]})
        ev.append({"from": "Typed tool layer", "to": t["layer"], "label": t["authority"], "state": t["status"]})
        ev.append({"from": t["layer"], "to": t["agent"], "label": t["summary"][:70], "state": "RESULT"})
    if run["refusal"]:
        ev.append({"from": "Orchestrator", "to": "Approval queue", "label": "write intent refused; proposal drafted", "state": "REFUSED"})
    ev.append({"from": "Orchestrator", "to": "UI", "label": "answer + trace", "state": "DONE"})
    ev.append({"from": "Typed tool layer", "to": "SAP connectors", "label": "not reached (DEMO)", "state": "NOT_REACHED"})
    return ev


def dot_live(events: list[dict], upto: int) -> str:
    nodes = []
    for e in events:
        for k in (e["from"], e["to"]):
            if k not in nodes:
                nodes.append(k)
    L = ["digraph L { rankdir=LR; node [shape=box, style=\"rounded,filled\", fontname=Helvetica, fontsize=9, fillcolor=\"#f4f6f8\"];"]
    active = {k for e in events[:upto] for k in (e["from"], e["to"])}
    for n in nodes:
        L.append(f"{_q(n)} [fillcolor=\"{'#cfe8ff' if n in active else '#f4f6f8'}\"" + (", style=\"dashed,filled\"" if n == "SAP connectors" else "") + "];")
    for i, e in enumerate(events):
        c = "#1a73c8" if i < upto else "#cccccc"
        if e["state"] in ("REFUSED", "NOT_REACHED"):
            c = "#b3261e" if i < upto else "#dddddd"
        L.append(f"{_q(e['from'])} -> {_q(e['to'])} [label={_q(str(i + 1))}, color=\"{c}\", fontsize=8];")
    L.append("}")
    return "\n".join(L)
