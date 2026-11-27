"""Complete architecture landscape: every component across every system of a scenario, derived from the scenario run.

Nothing here is a tenant-verified fact. System ids, objects and products are synthetic; SAP product names are generic terms.
Components that would need a live interface (metadata, catalog, extracts, deployment) are shown as NOT REACHED / UNAVAILABLE / NOT RUN.
"""
from __future__ import annotations

from collections import Counter

from . import agents

LAYERS = [
    ("agent", "Agent suite (this workbench)"),
    ("source", "Source systems"),
    ("finance", "Finance consolidation"),
    ("bdc", "SAP Business Data Cloud"),
    ("dsp", "Datasphere"),
    ("consume", "Consumption"),
    ("gov", "Governance and operations"),
    ("conn", "SAP connectors (interfaces)"),
]
BADGE = "SYNTHETIC LANDSCAPE - MODELLED, NOT TENANT-VERIFIED"
ENGINES = [("Discovery and dependency", "core.py / scenarios.py"), ("Catalog and evidence classes", "catalog.py"), ("Mapping and delta (16 dimensions)", "mapping.py"),
           ("Extensibility decision", "decision.py"), ("Business rule book", "rules.py"), ("Artifact generator (templates)", "artifacts.py"),
           ("Datasphere model and SQL check", "dsp_model.py"), ("Technical validation (offline)", "validation.py"),
           ("Reconciliation and golden", "recon.py / golden.py"), ("Synthetic data and BDC path", "synthetic.py / bdc.py"),
           ("Execution planner and audit", "execution.py"), ("Gates and status", "status.py")]


def _c(id_, layer, system, name, kind, detail, interface="-", status="SYNTHETIC", evidence="SYNTHETIC_FIXTURE"):
    return {"id": id_, "layer": layer, "system": system, "name": name, "kind": kind, "detail": detail, "interface": interface, "status": status, "evidence": evidence}


def build(res: dict, scn_key: str) -> dict:
    s = res["scenarios"][scn_key]
    top = s["topology"]
    systems = top["systems"]
    auth = top["fi_authority"]
    objs = s["objects"]
    by = Counter((o["system"], o["obj_type"]) for o in objs)
    comps: list[dict] = []
    flows: list[dict] = []

    # ---------------------------------------------------------------- source systems and finance consolidation
    for sid, sv in systems.items():
        t = sv["type"]
        if t not in ("ECC", "S4", "CFIN", "BW"):
            continue
        layer = "source" if t in ("ECC", "S4") else "finance"
        comps.append(_c(sid, layer, sid, f"{sid}", "System", f"{sv['release']} - client {sv['client']} - {sv['role']}"))
        names = {o["name"] for o in objs if o["system"] == sid}
        iface = "Read-only metadata (ADT / DDIC) - NOT REACHED"
        for typ, label in (("DDIC_TABLE", "DDIC tables"), ("CDS_INTERFACE_VIEW", "Released CDS interface views"), ("ODP_DATASOURCE", "ODP data sources"),
                           ("CDS_CUSTOM_VIEW", "Custom CDS views"), ("CUBE", "Analytic cubes"), ("QUERY", "Analytic queries"),
                           ("ADSO", "Advanced DataStore objects"), ("BW_QUERY", "BW queries")):
            n = by.get((sid, typ), 0)
            if n:
                sample = ", ".join(sorted(o["name"] for o in objs if o["system"] == sid and o["obj_type"] == typ)[:4])
                comps.append(_c(f"{sid}.{typ}", layer, sid, f"{label} ({n})", typ, f"e.g. {sample}", iface, evidence="SYNTHETIC_FIXTURE"))
        fi_tabs = [n for n in ("ACDOCA", "BKPF", "BSEG") if n in names]
        if fi_tabs:
            own = sorted(k.split("|")[1] for k, a in auth.items() if a == sid and k.startswith(sid + "|"))
            repl = sorted(k.split("|")[1] for k, a in auth.items() if k.startswith(sid + "|") and a != sid)
            txt = ", ".join(fi_tabs) + (f" - FI authority for company code(s) {', '.join(own)}" if own else "") + (f" - replicated to Central Finance for {', '.join(repl)}" if repl else "")
            comps.append(_c(f"{sid}.FI", layer, sid, "FI documents", "FI", txt, iface))
        cust = sum(len(o.get("custom_fields") or []) for o in objs if o["system"] == sid)
        if cust:
            comps.append(_c(f"{sid}.EXT", layer, sid, f"Custom fields ({cust})", "Extension", "customer fields found on discovered objects (key-user extension candidates)", iface))
    if "CFIN01" in systems:
        rep = sorted({f"{k.split('|')[0]} cc {k.split('|')[1]}" for k, a in auth.items() if a == "CFIN01"})
        comps.append(_c("CFIN01.REPL", "finance", "CFIN01", "FI replication from source systems", "Replication", ", ".join(rep) or "none", "Central Finance replication (modelled)"))
        comps.append(_c("CFIN01.MAP", "finance", "CFIN01", "Mapping tables", "Mapping", "supplier, company code and G/L account mappings (synthetic bridge)", "Mapping service (modelled)"))
    if "BW401" in systems:
        comps.append(_c("BW401.REF", "finance", "BW401", "Reference reporting output", "Reference", "existing BW result used only as a reconciliation reference (B4)", "Reference extract - NOT RUN", status="REFERENCE"))

    # ---------------------------------------------------------------- BDC
    cat = s["catalog"]["products"]
    ev = Counter(p["evidence"] for p in cat)
    acq = s["model"]["layers"]["1_acquisition"]
    acq_types = Counter(a["type"] for a in acq)
    flows_n = sum(1 for a in acq if str(a.get("replication_flow")) == "True")
    comps.append(_c("BDC01", "bdc", "BDC01", "BDC01", "System", systems["BDC01"]["role"]))
    comps.append(_c("BDC01.CAT", "bdc", "BDC01", f"Data-product catalog ({len(cat)})", "Catalog", ", ".join(f"{k} {v}" for k, v in sorted(ev.items())), "Hub / tenant catalog - UNAVAILABLE", status="UNAVAILABLE"))
    comps.append(_c("BDC01.ACQ", "bdc", "BDC01", f"Acquisition mappings ({len(acq)})", "Acquisition", ", ".join(f"{k} {v}" for k, v in sorted(acq_types.items())) or "none"))
    comps.append(_c("BDC01.RF", "bdc", "BDC01", f"Replication flows ({flows_n})", "Replication flow", "planned flows for customer-managed products; not deployed"))
    comps.append(_c("BDC01.CMP", "bdc", "BDC01", f"Customer-managed product packages ({len(s['packages'])})", "Package", "GENERATED templates; activated=False, published=False", "Not deployed", status="GENERATED"))

    # ---------------------------------------------------------------- Datasphere
    lay = s["model"]["layers"]
    sem = lay["4_semantic"]
    comps.append(_c("DSP01", "dsp", "DSP01", "DSP01", "System", systems["DSP01"]["role"]))
    comps.append(_c("DSP01.L1", "dsp", "DSP01", "Layer 1 Acquisition", "Model layer", f"{len(lay['1_acquisition'])} acquisition objects"))
    comps.append(_c("DSP01.L2", "dsp", "DSP01", "Layer 2 Harmonization", "Model layer", ", ".join(v["view"] for v in lay["2_harmonization"][:6])))
    comps.append(_c("DSP01.L3", "dsp", "DSP01", "Layer 3 Transformation", "Model layer", ", ".join(v["view"] for v in lay["3_transformation"][:4])))
    comps.append(_c("DSP01.L4", "dsp", "DSP01", "Layer 4 Semantic", "Model layer",
                    f"{len(sem['facts'])} facts, {len(sem['dimensions'])} dimensions, {len(sem['bridges'])} bridges, {len(sem['analytic_models'])} analytic models"))
    comps.append(_c("DSP01.L5", "dsp", "DSP01", "Layer 5 Consumption", "Model layer", ", ".join(x["exposure"] for x in lay["5_consumption"])))
    sql = s["sqlite"]
    comps.append(_c("DSP01.CHK", "dsp", "DSP01", "Model checks", "Validation", f"grain {s['grain']['status']}; SQL functional check {sql['status']} ({sql['mode']})", "Not deployed to Datasphere", status=sql["status"]))

    # ---------------------------------------------------------------- consumption
    cons = lay["5_consumption"][0].get("optional_consumers", []) if lay["5_consumption"] else []
    comps.append(_c("CON.AM", "consume", "-", "Analytic models", "Consumption", ", ".join(a["name"] for a in sem["analytic_models"])))
    if "DBX01" in systems:
        comps.append(_c("DBX01", "consume", "DBX01", "DBX01 (optional)", "System", systems["DBX01"]["role"], status="OPTIONAL"))
    for i, c in enumerate(cons):
        comps.append(_c(f"CON.{i}", "consume", "-", c, "Optional consumer", "downstream consumption; not part of this build", status="OPTIONAL"))

    # ---------------------------------------------------------------- agent suite
    cv = agents.catalog_view()
    comps.append(_c("AG.UI", "agent", "Suite", "Cockpit UI", "UI", "Home, Delta journey (5 stages), Agents, Architecture & operations"))
    comps.append(_c("AG.ORCH", "agent", "Suite", "Orchestrator", "Orchestrator", "plans and routes requests to the lead agent; refuses write intents; cannot act on SAP"))
    for a in cv:
        comps.append(_c(f"AG.F.{a['id']}", "agent", "Suite", f"{a['name']} ({a['tool_count']} tools)", "Agent", f"stages {', '.join(str(x) for x in a['stages'])}: {a['blurb']}"))
    by_layer = Counter(t["layer"] for t in agents.TOOLS.values())
    comps.append(_c("AG.TOOLS", "agent", "Suite", f"Typed tool layer ({len(agents.TOOLS)} tools)", "Tool layer", ", ".join(f"{k} {v}" for k, v in sorted(by_layer.items())), "MCP-style typed calls"))
    comps.append(_c("AG.ENG", "agent", "Suite", f"Domain engines ({len(ENGINES)})", "Engines", "; ".join(n for n, _ in ENGINES)))
    comps.append(_c("AG.EVID", "agent", "Suite", "Evidence store", "Store", "persisted results.json and release evidence; read by agents"))

    # ---------------------------------------------------------------- governance
    gates = res["gates"]
    comps.append(_c("GOV.RULES", "gov", "Suite", f"Business rule book ({len(s['rules']['after'])} rules)", "Rule book", "AI can propose, never approve; approvals here are synthetic-scope"))
    comps.append(_c("GOV.PLAN", "gov", "Suite", "Execution planner", "Planner", f"3 modes; {len(s['plan']['DEMO'])} steps; DEPLOYED / RUNTIME_VERIFIED unreachable"))
    comps.append(_c("GOV.APPR", "gov", "Suite", "Approval queue", "Approval", "draft-only proposals; named human approves outside the suite"))
    comps.append(_c("GOV.GATES", "gov", "Suite", f"Acceptance gates ({sum(1 for g in gates if g['status'] == 'PASS')}/{len(gates)} PASS)", "Gates", "G01-G15 evaluated on synthetic evidence"))
    comps.append(_c("GOV.AUDIT", "gov", "Suite", "Audit log", "Audit", "redacted; idempotency keys; bounded retries"))

    # ---------------------------------------------------------------- connectors (none reached)
    comps.append(_c("CN.ADT", "conn", "-", "Metadata interface (ADT, read-only)", "Connector", "object discovery against source systems", "NOT REACHED", status="NOT REACHED", evidence="UNKNOWN"))
    comps.append(_c("CN.HUB", "conn", "-", "Catalog interface (Hub / tenant)", "Connector", "data-product catalog capture", "UNAVAILABLE", status="UNAVAILABLE", evidence="UNKNOWN"))
    comps.append(_c("CN.EXT", "conn", "-", "Aggregated extracts (source and BDC)", "Connector", "runtime figures for live reconciliation", "NOT RUN", status="NOT RUN", evidence="UNKNOWN"))
    comps.append(_c("CN.DEP", "conn", "-", "Deployment / activation / transport", "Connector", "writes to SAP, BDC or Datasphere", "NOT AUTHORIZED", status="NOT AUTHORIZED", evidence="UNKNOWN"))

    # ---------------------------------------------------------------- flows
    lv = s["recon"]["levels"]

    def st(k):
        return (lv.get(k) or {}).get("status", "-")

    for src in top["sources"]:
        flows.append({"from": src, "to": "BDC01", "label": "data products / extraction", "plane": "data", "status": "MODELLED"})
    for k, a in auth.items():
        sy, cc = k.split("|")
        if a == "CFIN01":
            flows.append({"from": sy, "to": "CFIN01", "label": f"FI replication cc {cc}", "plane": "fi", "status": "MODELLED"})
    if "CFIN01" in systems:
        flows.append({"from": "CFIN01", "to": "BDC01", "label": "mapped FI", "plane": "fi", "status": "MODELLED"})
    if "BW401" in systems:
        flows.append({"from": "ECC01", "to": "BW401", "label": "ODP", "plane": "data", "status": "MODELLED"})
        flows.append({"from": "BW401", "to": "BDC01", "label": "history (reference only)", "plane": "ref", "status": "REFERENCE"})
    flows.append({"from": "BDC01", "to": "DSP01", "label": "acquisition", "plane": "data", "status": "MODELLED"})
    flows.append({"from": "DSP01", "to": "CON.AM", "label": "analytic model consumption", "plane": "data", "status": "MODELLED"})
    if "DBX01" in systems:
        flows.append({"from": "DSP01", "to": "DBX01", "label": "optional", "plane": "ref", "status": "OPTIONAL"})
    recon_pairs = [("L1", "source systems", "BDC01", "L1 source to acquisition"), ("L2", "BDC01", "DSP01", "L2 acquisition to model"), ("L3", "source systems", "DSP01", "L3 end-to-end")]
    for k, a, b, lab in recon_pairs:
        flows.append({"from": a, "to": b, "label": f"{lab}: {st(k)}", "plane": "recon", "status": st(k)})
    if "CFIN01" in systems:
        flows.append({"from": "source systems", "to": "CFIN01", "label": f"B1 source to Central Finance: {st('B1')}", "plane": "recon", "status": st("B1")})
    if "BW401" in systems:
        flows.append({"from": "BW401", "to": "BDC01", "label": f"B4 BW reference vs BDC: {st('B4')}", "plane": "recon", "status": st("B4")})
    flows += [{"from": "Cockpit UI", "to": "Orchestrator", "label": "request", "plane": "control", "status": "ACTIVE"},
              {"from": "Orchestrator", "to": "Agents", "label": "plan", "plane": "control", "status": "ACTIVE"},
              {"from": "Agents", "to": "Typed tool layer", "label": "typed calls", "plane": "control", "status": "ACTIVE"},
              {"from": "Typed tool layer", "to": "Domain engines", "label": "compute", "plane": "control", "status": "ACTIVE"},
              {"from": "Domain engines", "to": "Evidence store", "label": "read / write results", "plane": "control", "status": "ACTIVE"},
              {"from": "Typed tool layer", "to": "SAP connectors", "label": "not reached (DEMO)", "plane": "blocked", "status": "NOT REACHED"},
              {"from": "SAP connectors", "to": "source systems", "label": "metadata, extracts", "plane": "blocked", "status": "NOT REACHED"},
              {"from": "Orchestrator", "to": "Approval queue", "label": "write intents drafted only", "plane": "gov", "status": "ACTIVE"},
              {"from": "Business rule book", "to": "Reconciliation", "label": "blocks unapproved rules", "plane": "gov", "status": "ACTIVE"}]
    return {"scenario": scn_key, "layers": LAYERS, "components": comps, "flows": flows, "systems": [k for k, v in systems.items()]}


# ---------------------------------------------------------------------------------------------------------- diagram
def _q(x: str) -> str:
    return '"' + str(x).replace('"', "'").replace("\n", "\\n") + '"'


def _short(x: str, n: int = 46) -> str:
    return x if len(x) <= n else x[: n - 1] + "..."


def dot(L: dict, view: str = "Full landscape") -> str:
    """Graphviz DOT with one cluster per system (system header node + component nodes) and flows drawn between the system headers."""
    comps = L["components"]
    layers_in = {"Full landscape": {"agent", "source", "finance", "bdc", "dsp", "consume", "gov", "conn"},
                 "Data landscape": {"source", "finance", "bdc", "dsp", "consume"},
                 "Agent suite and governance": {"agent", "gov", "conn"}}[view]
    fill = {"source": "#e3f1e3", "finance": "#e8e3f5", "bdc": "#d9edf7", "dsp": "#d9edf7", "consume": "#f2f2f2", "agent": "#fff2cc", "gov": "#fde9d9", "conn": "#f8d7da"}
    g = ["digraph LAND { rankdir=LR; compound=true; newrank=true; nodesep=0.18; ranksep=0.7; fontname=Helvetica;",
         'node [shape=box, style="rounded,filled", fontname=Helvetica, fontsize=9, margin="0.08,0.04"]; edge [fontname=Helvetica, fontsize=8];']
    anchor: dict[str, str] = {}
    # group by (layer, system)
    groups: dict[tuple[str, str], list[dict]] = {}
    for c in comps:
        if c["layer"] in layers_in:
            groups.setdefault((c["layer"], c["system"]), []).append(c)
    n = 0
    for (layer, system), items in groups.items():
        n += 1
        title = dict(LAYERS)[layer] if system in ("Suite", "-") else system
        if layer == "consume" and system == "DSP01":
            title = "Consumption"
        g.append(f"subgraph cluster_{n} {{ label={_q(title)}; labeljust=l; style=\"rounded,filled\"; color=\"#9db4c8\"; fillcolor=\"#ffffff\"; fontsize=11;")
        head = next((c for c in items if c["kind"] == "System"), None)
        for c in items:
            shape = "box"
            style = '"rounded,filled,dashed"' if c["status"] in ("NOT REACHED", "UNAVAILABLE", "NOT RUN", "NOT AUTHORIZED", "OPTIONAL") else '"rounded,filled"'
            label = (c["name"] if c["kind"] != "System" else c["name"] + "\\n" + _short(c["detail"], 52)) if c["kind"] == "System" else c["name"] + "\\n" + _short(c["detail"])
            g.append(f"{_q(c['id'])} [label={_q(label)}, shape={shape}, style={style}, fillcolor=\"{fill[layer]}\"];")
        first = head or items[0]
        anchor[system if head else f"{layer}:{system}"] = first["id"]
        g.append("}")
    # map flow endpoint names to nodes
    ep = {"BDC01": "BDC01", "DSP01": "DSP01", "CFIN01": "CFIN01", "BW401": "BW401", "ECC01": "ECC01", "S4A": "S4A", "S4B": "S4B", "DBX01": "DBX01", "CON.AM": "CON.AM",
          "Cockpit UI": "AG.UI", "Orchestrator": "AG.ORCH", "Agents": next((c["id"] for c in comps if c["id"].startswith("AG.F.")), "AG.ORCH"),
          "Typed tool layer": "AG.TOOLS", "Domain engines": "AG.ENG", "Evidence store": "AG.EVID", "SAP connectors": "CN.ADT", "Approval queue": "GOV.APPR",
          "Business rule book": "GOV.RULES", "Reconciliation": "GOV.GATES"}
    present = {c["id"] for c in comps if c["layer"] in layers_in}
    srcs = [c["id"] for c in comps if c["kind"] == "System" and c["layer"] == "source"]
    color = {"data": "#1a73c8", "fi": "#7a5ca8", "ref": "#888888", "recon": "#2e7d32", "control": "#555555", "blocked": "#b3261e", "gov": "#c77700"}
    for f in L["flows"]:
        a, b = f["from"], f["to"]
        if a == "source systems":
            a = srcs[0] if srcs else None
        if b == "source systems":
            b = srcs[0] if srcs else None
        a, b = ep.get(a, a), ep.get(b, b)
        if a not in present or b not in present:
            continue
        if f["plane"] in ("control", "blocked", "gov") and view == "Data landscape":
            continue
        style = "dashed" if f["plane"] in ("recon", "blocked", "ref") else "solid"
        con = "false" if f["plane"] in ("control", "blocked", "gov", "recon") else "true"
        g.append(f"{_q(a)} -> {_q(b)} [label={_q(_short(f['label'], 40))}, color=\"{color.get(f['plane'], '#555')}\", fontcolor=\"{color.get(f['plane'], '#555')}\", style={style}, constraint={con}];")
    g.append("}")
    return "\n".join(g)


def inventory(L: dict) -> list[dict]:
    names = dict(L["layers"])
    return [{"layer": names[c["layer"]], "system": c["system"], "component": c["name"], "kind": c["kind"], "detail": c["detail"], "interface": c["interface"],
             "status": c["status"], "evidence": c["evidence"]} for c in L["components"]]
