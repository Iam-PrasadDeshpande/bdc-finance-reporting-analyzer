"""Two-way lookup between a business process and the SAP-delivered data products (synthetic catalog, deterministic).

  process  -> data products : "for this process, which data products exist, how well do they cover it, and what is the delta?"
  product  -> processes     : "if I activate or extend this data product, which processes does it serve and what differs in the backend?"

Both directions read the same delta register and catalog as the delta journey, so the answers can never disagree with it.
The process taxonomy below is a small SYNTHETIC illustration (it is not SAP's process model or a process-mining result): it names the
standard-object groups a process touches, and the catalog says which products cover those groups. A process that is not in the
taxonomy is reported as not found, never guessed. A group with no product is "no SAP product" only where the catalog declares its
domain complete; otherwise it is "not established", never "does not exist"."""
from __future__ import annotations

import re

from . import delta, scenarios

BADGE = "SYNTHETIC PROCESS TAXONOMY AND CATALOG - NOT TENANT-VERIFIED"

# process id -> name, aliases and ordered steps (step name, object groups)
PROCESSES: dict[str, dict] = {
    "P2P": {"name": "Procure to Pay", "aliases": ["procure to pay", "purchase to pay", "p2p", "procurement", "purchasing"],
            "steps": [("Purchase requisition", ["PR", "PRACC"]), ("Purchase order", ["POH", "POI", "POACC", "POSCH"]),
                      ("Goods receipt", ["MATDOC"]), ("Invoice verification", ["INVH", "INVI"]),
                      ("Accounting posting", ["BKPF", "BSEG", "ACDOCA"]), ("Supplier master", ["BP"]), ("Material master", ["MAT"])]},
    "GRIR": {"name": "GR/IR reconciliation", "aliases": ["gr/ir", "grir", "gr ir", "goods receipt invoice receipt", "goods receipt/invoice receipt", "grir clearing"],
             "steps": [("Order value and history", ["POI", "POHIST"]), ("Goods receipt", ["MATDOC"]), ("Invoice receipt", ["INVI"]),
                       ("Journal entry", ["ACDOCA"])]},
    "AP": {"name": "Accounts payable (open items and payment)", "aliases": ["accounts payable", "payables", "open items", "open item", "vendor payment", "supplier payment", "payment run", "ap"],
           "steps": [("Supplier master", ["BP"]), ("Supplier open items", ["SUPOI"]), ("Payment and clearing", ["PAYCLR"]),
                     ("Accounting posting", ["BKPF", "ACDOCA"])]},
    "R2R": {"name": "Record to Report (general ledger)", "aliases": ["record to report", "r2r", "general ledger", "financial close", "period close", "journal entries"],
            "steps": [("Journal entries", ["ACDOCA", "BKPF", "BSEG"]), ("Chart of accounts", ["GL"]), ("Cost objects", ["CC"])]},
    "CFIN": {"name": "Central Finance consolidation", "aliases": ["central finance", "cfin", "cross-system finance", "consolidation"],
             "steps": [("Journal entries", ["ACDOCA", "BKPF"]), ("Cross-system document mapping", ["XMAP"]), ("Business partner", ["BP"])]},
    "MD": {"name": "Master data (suppliers, materials, accounts)", "aliases": ["master data", "supplier master", "business partner", "material master", "master"],
           "steps": [("Business partner", ["BP"]), ("Material", ["MAT"]), ("G/L account", ["GL"]), ("Cost center", ["CC"])]},
}

FIT = {"COVERED_AS_IS": "Covered as delivered", "COVERED_WITH_DELTA": "Covered, with a delta", "CANDIDATE_ONLY": "Candidate product only (unverified)",
       "NO_PRODUCT": "No SAP product", "NOT_ESTABLISHED": "Not established (catalog completeness unknown)"}
_ORDER = ["COVERED_AS_IS", "COVERED_WITH_DELTA", "CANDIDATE_ONLY", "NOT_ESTABLISHED", "NO_PRODUCT"]   # best to worst


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/ ]", " ", (text or "").lower())).strip()


def _word_in(alias: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text) is not None


def resolve_process(text: str) -> list[str]:
    """Process ids named in free text, best match first (longest alias wins). Empty if nothing matches: never guessed."""
    t = _norm(text)
    hits = []
    for pid, p in PROCESSES.items():
        best = max((len(a) for a in [p["name"].lower(), *p["aliases"]] if _word_in(_norm(a), t)), default=0)
        if best:
            hits.append((best, pid))
    return [pid for _, pid in sorted(hits, key=lambda x: (-x[0], x[1]))]


def _fit(row: dict, catalog_by_id: dict) -> str:
    prod = row["product"].split(" / ")[0]
    if prod == "none" or prod not in catalog_by_id:
        return "NOT_ESTABLISHED" if row["delta_type"] == "UNKNOWN_CATALOG" else "NO_PRODUCT"
    if catalog_by_id[prod]["evidence"] != "SYNTHETIC_FIXTURE":
        return "CANDIDATE_ONLY"
    return "COVERED_AS_IS" if row["delta_type"] == "NO_DELTA" else "COVERED_WITH_DELTA"


def _group_rows(s: dict) -> dict:
    """group -> register rows (one per system) for the scenario."""
    objs = {a["requirement"]: a for a in s["analysis"]}
    out: dict[str, list] = {}
    for r in delta.register(s):
        a = objs.get(r["requirement"])
        if a:
            out.setdefault(a["group"], []).append(r)
    return out


def _grain(g: str) -> str:
    return scenarios.GROUPS[g]["grain"]


def process_to_products(res: dict, scn: str, text: str) -> dict:
    """Which data products serve this process, how well, and what the delta is."""
    s = res["scenarios"][scn]
    ids = resolve_process(text)
    if not ids:
        return {"found": False, "query": text, "known": [{"id": k, "name": v["name"]} for k, v in PROCESSES.items()],
                "summary": "No process in the synthetic taxonomy matches the request. Nothing is guessed. Known processes: " + "; ".join(v["name"] for v in PROCESSES.values()) + "."}
    pid = ids[0]
    proc = PROCESSES[pid]
    cat = {p["product_id"]: p for p in s["catalog"]["products"]}
    rows_by_group = _group_rows(s)
    steps, products = [], {}
    worst = 0
    for step, groups in proc["steps"]:
        srows = []
        for g in groups:
            for r in rows_by_group.get(g, []):
                fit = _fit(r, cat)
                worst = max(worst, _ORDER.index(fit))
                prod, _, ent = r["product"].partition(" / ")
                srows.append({"step": step, "object": _grain(g), "system": r["system"], "sap_object": r["sap_object"],
                              "product": prod if prod != "none" else "-", "entity": ent or "-", "fit": fit, "delta": r["delta_type"],
                              "solution": r["route"], "evidence": cat[prod]["evidence"] if prod in cat else "-"})
                if prod in cat:
                    d = products.setdefault(prod, {"product": prod, "name": cat[prod]["name"], "evidence": cat[prod]["evidence"], "domain": cat[prod].get("domain", ""),
                                                   "activation": cat[prod]["activation"], "entitlement": cat[prod]["entitlement"], "steps": set(), "objects": 0, "with_delta": 0})
                    d["steps"].add(step)
                    d["objects"] += 1
                    d["with_delta"] += fit != "COVERED_AS_IS"
        steps.append({"step": step, "rows": srows})
    allrows = [r for st_ in steps for r in st_["rows"]]
    counts = {k: sum(1 for r in allrows if r["fit"] == k) for k in _ORDER}
    plist = sorted(({**d, "steps": sorted(d["steps"])} for d in products.values()), key=lambda d: (-d["objects"], d["product"]))
    verdict = _ORDER[worst] if allrows else "NOT_ESTABLISHED"
    summary = (f"{proc['name']} touches {len(allrows)} object(s) in this scenario across {len(steps)} step(s): " +
               ", ".join(f"{counts[k]} {FIT[k].lower()}" for k in _ORDER if counts[k]) +
               f". {len(plist)} SAP data product(s) are involved. Overall: {FIT[verdict]}. {BADGE}.")
    return {"found": True, "process": pid, "name": proc["name"], "other_matches": [PROCESSES[i]["name"] for i in ids[1:]], "steps": steps, "products": plist,
            "counts": counts, "verdict": verdict, "summary": summary}


def product_to_processes(res: dict, scn: str, text: str) -> dict:
    """Which processes does this data product serve, and what differs in the backend if it is activated or extended."""
    s = res["scenarios"][scn]
    cat = {p["product_id"]: p for p in s["catalog"]["products"]}
    q = (text or "").strip()
    pid = next((k for k in cat if k.lower() == q.lower()), None)
    if pid is None:
        m = re.search(r"sim_dp_\w+", q, re.I)
        pid = next((k for k in cat if m and k.lower() == m.group(0).lower()), None)
    if pid is None:
        t = _norm(q)
        tokens = set(t.split())
        skip = {"synthetic", "header", "level", "only", "no", "delta", "candidate"}
        full = {k: [w for w in _norm(p["name"]).split() if w not in skip] for k, p in cat.items()}
        named = {k: w for k, w in full.items() if w and all(x in tokens for x in w)}      # a longer name beats a shorter one ("purchase order" over "order")
        if named:
            top = max(len(w) for w in named.values())
            best = [k for k, w in named.items() if len(w) == top]
            if len(best) == 1:
                pid = best[0]
    if pid is None:
        t = _norm(q)
        cands = [k for k, p in cat.items() if t and (_word_in(t, _norm(p["name"])) or _word_in(t, _norm(k)))]
        words = [w for w in t.split() if len(w) > 3]
        if not cands and words:
            cands = [k for k, p in cat.items() if all(w in _norm(p["name"] + " " + k) for w in words)]
        if len(cands) == 1:
            pid = cands[0]
    if pid is None:
        amb = cands if len(cands) > 1 else []
        return {"found": False, "query": q, "known": [{"id": k, "name": p["name"]} for k, p in cat.items()],
                "summary": ("Several data products match (" + "; ".join(amb) + "): name one. " if amb else "No data product in the synthetic catalog matches. ") +
                           "Known products: " + "; ".join(cat) + "."}
    p = cat[pid]
    rows_by_group = _group_rows(s)
    # coverage comes from the delta register (the same mapping the journey uses): a group is covered when a register row maps it to this product
    entity_of = {g: r["product"].partition(" / ")[2] for g, rs in rows_by_group.items() for r in rs if r["product"].split(" / ")[0] == pid}
    covered = set(entity_of)
    procs = []
    for k, proc in PROCESSES.items():
        groups = [g for _, gs in proc["steps"] for g in gs]
        hit = [g for g in groups if g in covered]
        if not hit:
            continue
        steps = sorted({st_ for st_, gs in proc["steps"] if any(g in covered for g in gs)}, key=[x for x, _ in proc["steps"]].index)
        rr = [r for g in hit for r in rows_by_group.get(g, []) if r["product"].split(" / ")[0] == pid]
        fits = [_fit(r, cat) for r in rr]
        procs.append({"process": k, "name": proc["name"], "steps": steps, "objects_served": len(hit), "objects_in_process": len(groups),
                      "share": f"{len(hit)} of {len(groups)}", "with_delta": sum(f != "COVERED_AS_IS" for f in fits),
                      "other_products_needed": sorted({r["product"].split(" / ")[0] for g in groups if g not in covered for r in rows_by_group.get(g, [])
                                                       if r["product"].split(" / ")[0] != "none"})})
    backend = [{"object": _grain(g), "system": r["system"], "sap_object": r["sap_object"], "entity": entity_of.get(g, "-"), "delta": r["delta_type"],
                "solution": r["route"], "customization": r["kind"] == "Customization"}
               for g in sorted(covered) for r in rows_by_group.get(g, []) if r["product"].split(" / ")[0] == pid]
    bp = delta.by_product(s)["products"].get(pid, {})
    ext = p.get("extension") or {}
    summary = (f"{p['name']} ({pid}, {p['evidence']}) serves {len(procs)} process(es): " + ", ".join(x["name"] for x in procs) +
               f". In the backend: {sum(1 for b in backend if b['delta'] != 'NO_DELTA')} of {len(backend)} mapped object(s) differ from the product "
               f"({sum(1 for b in backend if b['customization'])} customization(s)). Product status {bp.get('status', '-')}. {BADGE}.")
    return {"found": True, "product": pid, "name": p["name"], "evidence": p["evidence"], "domain": p.get("domain", ""),
            "state": {"activation": p["activation"], "entitlement": p["entitlement"], "installation": p["installation"], "releases": p["supported_releases"],
                      "key_user_extension": bool(ext.get("key_user")), "developer_extension": bool(ext.get("developer")), "data_product_extension": bool(ext.get("data_product_extension"))},
            "processes": procs, "backend": backend, "status": bp.get("status", "-"), "summary": summary}


def process_matrix(res: dict, scn: str) -> list[dict]:
    """Overview: every process with its verdict, so the user can pick one."""
    out = []
    for k, v in PROCESSES.items():
        r = process_to_products(res, scn, v["name"])
        out.append({"process": v["name"], "steps": len(v["steps"]), "products": len(r["products"]), "verdict": FIT[r["verdict"]],
                    **{FIT[c]: r["counts"][c] for c in _ORDER}})
    return out
