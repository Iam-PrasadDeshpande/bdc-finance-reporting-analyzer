"""BDC-side pipeline: acquisition -> harmonization -> transformation -> semantic facts -> measures.

Independent of the backend reference path (recon_reference.py): this pipeline reads ACDOCA-style rows and PO history
(EKBE-style), the reference reads BSEG/BKPF-style rows and PO/GR/invoice documents. Transactional grains stay independent
and are never joined fact-to-fact; PO history is pre-aggregated per PO item before it meets the commitment fact.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from decimal import Decimal

from .core import D
from .scenarios import SCENARIOS

DEFECTS = ("DELAYED_CFIN_REPLICATION", "MISSING_SUPPLIER_MAPPING", "LATE_ARRIVING_CHANGE", "AMOUNT_TAMPER", "DROPPED_INVOICE",
           "DUPLICATED_JOURNAL_LINE", "WRONG_CURRENCY", "NAIVE_DOUBLE_FI")


class Acc:
    """Accumulator keeping contributor ids for drill-down."""

    def __init__(self):
        self.v: dict = defaultdict(lambda: D(0))
        self.ids: dict = defaultdict(list)

    def add(self, key, amount, rec_id):
        self.v[key] += D(amount)
        self.ids[key].append(rec_id)

    def values(self):
        return dict(self.v)


def acquire(world: dict, defects: tuple = ()) -> dict:
    """Acquisition layer: data-product style entity extracts with system-qualified keys and an extraction watermark."""
    acq = {"watermark": world["extraction_ts"], "entities": defaultdict(list), "applied_defects": []}
    for sid, d in world["systems"].items():
        for r in d["po_items"]:
            acq["entities"]["po_item"].append({**r, "doc_key": f"{sid}|{r['client']}|{r['po']}|{r['item']}"})
        for r in d["pr"]:
            acq["entities"]["pr"].append(dict(r))
        for r in d["po_hist"]:
            acq["entities"]["po_history"].append(dict(r))
        for r in d["gr"]:
            acq["entities"]["gr"].append({**r, "doc_key": f"{sid}|{r['client']}|{r['mat_doc']}|{r['item']}"})
        for r in d["inv"]:
            acq["entities"]["inv_item"].append({**r, "doc_key": f"{sid}|{r['client']}|{r['inv_doc']}|{r['item']}"})
        for r in d["pay"]:
            acq["entities"]["clearing"].append(dict(r))
        for r in d["acdoca"]:
            acq["entities"]["acdoca_src"].append({**r, "reporting_system": sid})
    cf = world["cfin"]
    for r in cf["acdoca"]:
        acq["entities"]["acdoca_cfin"].append({**r, "reporting_system": "CFIN01"})
    for r in cf["bridge"]:
        acq["entities"]["bridge"].append(dict(r))
    acq["entities"] = {k: copy.deepcopy(v) for k, v in acq["entities"].items()}
    e = acq["entities"]
    if "DELAYED_CFIN_REPLICATION" in defects and e.get("bridge"):
        late = {(b["cfin_bukrs"], b["cfin_belnr"], b["cfin_gjahr"]) for b in e["bridge"][-3:]}
        e["bridge"] = e["bridge"][:-3]
        e["acdoca_cfin"] = [a for a in e["acdoca_cfin"] if (a["rbukrs"], a["belnr"], a["gjahr"]) not in late]
        acq["applied_defects"].append({"defect": "DELAYED_CFIN_REPLICATION", "documents_missing": len(late)})
    if "MISSING_SUPPLIER_MAPPING" in defects:
        sm = dict(world["masters"]["supplier_map"])
        pref = "S4B" if any(k[0] == "S4B" for k in sm) else "S4A"
        victim = sorted(k for k in sm if k[0] == pref)[0]
        sm.pop(victim)
        acq["supplier_map"] = sm
        acq["applied_defects"].append({"defect": "MISSING_SUPPLIER_MAPPING", "supplier": f"{victim[0]}:{victim[1]}"})
    else:
        acq["supplier_map"] = dict(world["masters"]["supplier_map"])
    if "LATE_ARRIVING_CHANGE" in defects and e["po_item"]:
        acq["late_source_change"] = e["po_item"][0]["id"]  # source changed after the watermark; extract is stale
        acq["applied_defects"].append({"defect": "LATE_ARRIVING_CHANGE", "record": e["po_item"][0]["id"]})
    return acq


def transform(acq: dict, scenario: str, defects: tuple = ()) -> dict:
    """Harmonization, transformation and semantic facts. Returns the model plus rejected records."""
    sc = SCENARIOS[scenario]
    e = acq["entities"]
    authority = sc.get("fi_authority", {})
    rejected: list[dict] = []
    # --- procurement facts (independent grains) ---
    hist = defaultdict(lambda: {"E_qty": D(0), "E_val": D(0), "Q_qty": D(0), "Q_val": D(0)})
    for h in e["po_history"]:
        k = (h["system"], h["po"], h["item"])
        hist[k][f"{h['type']}_qty"] += h["qty"]
        hist[k][f"{h['type']}_val"] += h["value"]
    commitment = []
    for p in e["po_item"]:
        k = (p["system"], p["po"], p["item"])
        h = hist.get(k, {"E_qty": D(0), "Q_qty": D(0)})
        open_qty = max(p["qty"] - h["E_qty"], D(0))
        commitment.append({"id": p["id"], "system": p["system"], "bukrs": p["bukrs"], "ccy": p["ccy"], "po": p["po"],
                           "po_qty": p["qty"], "po_value": p["net"], "gr_qty": h["E_qty"], "open_qty": open_qty,
                           "open_commitment": open_qty * p["price"]})
    gr_fact = [{"id": g["id"], "system": g["system"], "bukrs": g["bukrs"], "ccy": g["ccy"], "qty": g["qty"], "value": g["value"],
                "doc_key": g["doc_key"]} for g in e["gr"]]
    inv_fact = [{"id": i["id"], "system": i["system"], "bukrs": i["bukrs"], "ccy": i["ccy"], "qty": i["qty"], "net": i["net"],
                 "net_po": i["net_po"], "gross": i["gross"], "doc": i["inv_doc"], "supplier": i["supplier"],
                 "doc_key": i["doc_key"]} for i in e["inv_item"]]
    # --- supplier open items (grain: invoice document) with explicit clearing rule R-CLEARING-ALLOC-001 ---
    alloc = defaultdict(lambda: D(0))
    for c in e["clearing"]:
        alloc[(c["system"], c["inv_doc"])] += c["amount"]
    docs: dict = {}
    for i in inv_fact:
        d = docs.setdefault((i["system"], i["doc"]), {"system": i["system"], "bukrs": i["bukrs"], "ccy": i["ccy"], "doc": i["doc"],
                                                      "supplier": i["supplier"], "gross": D(0)})
        d["gross"] += i["gross"]
    sup_map = acq["supplier_map"]
    open_items = []
    for k, d in sorted(docs.items()):
        sys_, sup = d["system"], d["supplier"]
        if (sys_, sup) not in sup_map:
            rejected.append({"entity": "supplier_open_item", "key": f"{sys_}|{d['doc']}", "reason": "MISSING_SUPPLIER_MAPPING",
                             "amount": d["gross"] - alloc[k], "ccy": d["ccy"], "system": sys_, "bukrs": d["bukrs"]})
            continue
        allocated = alloc[k]
        open_items.append({**d, "allocated": allocated, "open": d["gross"] - allocated,
                           "cleared": d["gross"] > 0 and allocated >= d["gross"]})
    # --- journal fact with single FI source of truth per company code ---
    journal, pending = [], []
    bridged = {(b["src_system"], b["src_bukrs"], b["src_belnr"], b["src_gjahr"]) for b in e.get("bridge", [])}
    naive = "NAIVE_DOUBLE_FI" in defects
    for a in e.get("acdoca_src", []):
        auth = authority.get((a["reporting_system"], a["rbukrs"]), a["reporting_system"])
        if auth == "CFIN01" and not naive:
            key = (a["reporting_system"], a["rbukrs"], a["belnr"], a["gjahr"])
            if key not in bridged:
                pending.append({"doc": key, "reason": "NOT_YET_REPLICATED_TO_CFIN"})
            continue  # reported from Central Finance only: never add source and replicated FI
        journal.append({**a, "reported_by": a["reporting_system"]})
    for a in e.get("acdoca_cfin", []):
        origin = a.get("origin", {})
        sup = a.get("lifnr")
        if sup and origin and (origin["system"], sup.split("-")[-1]) not in sup_map:
            rejected.append({"entity": "journal_line", "key": a["id"], "reason": "MISSING_SUPPLIER_MAPPING", "amount": a["hsl"],
                             "ccy": a["rhcur"], "system": "CFIN01", "bukrs": a["rbukrs"]})
            continue
        journal.append({**a, "reported_by": "CFIN01"})
    # de-duplicate on the full system-qualified key: collisions across systems are NOT duplicates
    seen, dedup = {}, []
    for j in journal:
        k = (j["reported_by"], j["rbukrs"], j["gjahr"], j["belnr"], j["docln"], j.get("src_system"))
        if k in seen:
            continue
        seen[k] = 1
        dedup.append(j)
    journal = dedup
    model = {"commitment": commitment, "gr": gr_fact, "inv": inv_fact, "open_items": open_items, "journal": journal,
             "clearing": [dict(c) for c in e["clearing"]], "pr": e["pr"], "rejected": rejected, "pending_replication": pending}
    _apply_model_defects(model, defects)
    return model


def _apply_model_defects(m: dict, defects: tuple) -> None:
    applied = []
    if "AMOUNT_TAMPER" in defects and m["gr"]:
        m["gr"][5]["value"] += D(100)
        applied.append({"defect": "AMOUNT_TAMPER", "record": m["gr"][5]["id"], "delta": "100"})
    if "DROPPED_INVOICE" in defects and m["inv"]:
        victim = m["inv"].pop(3)
        applied.append({"defect": "DROPPED_INVOICE", "record": victim["id"]})
    if "DUPLICATED_JOURNAL_LINE" in defects and m["journal"]:
        m["journal"].append(dict(m["journal"][7]))
        applied.append({"defect": "DUPLICATED_JOURNAL_LINE", "record": m["journal"][7]["id"]})
    if "WRONG_CURRENCY" in defects and m["inv"]:
        m["inv"][2]["ccy"] = "EUR" if m["inv"][2]["ccy"] != "EUR" else "USD"
        applied.append({"defect": "WRONG_CURRENCY", "record": m["inv"][2]["id"]})
    m["model_defects"] = applied


def measures(m: dict, scenario: str) -> dict:
    """Measure ledgers from the BDC semantic facts. Keys mirror the reference measures exactly."""
    out: dict[str, Acc] = defaultdict(Acc)
    for c in m["commitment"]:
        k = (c["system"], c["bukrs"], c["ccy"])
        out["po_qty"].add(k, c["po_qty"], c["id"])
        out["po_value"].add(k, c["po_value"], c["id"])
        out["open_po_qty"].add(k, c["open_qty"], c["id"])
        out["open_commitment"].add(k, c["open_commitment"], c["id"])
    for p in m["pr"]:
        k = (p["system"], p["bukrs"], p["ccy"])
        out["pr_qty"].add(k, p["qty"], p["id"])
        out["pr_value"].add(k, p["value"], p["id"])
    gr_docs: dict = defaultdict(set)
    for g in m["gr"]:
        k = (g["system"], g["bukrs"], g["ccy"])
        out["gr_qty"].add(k, g["qty"], g["id"])
        out["gr_value"].add(k, g["value"], g["id"])
        gr_docs[k].add(g["doc_key"].rsplit("|", 1)[0])
    inv_docs: dict = defaultdict(set)
    for i in m["inv"]:
        k = (i["system"], i["bukrs"], i["ccy"])
        out["inv_qty"].add(k, i["qty"], i["id"])
        out["inv_value"].add(k, i["net"], i["id"])
        out["inv_value_po_price"].add(k, i["net_po"], i["id"])
        inv_docs[k].add(i["doc_key"].rsplit("|", 1)[0])
    for k, s in gr_docs.items():
        out["gr_doc_count"].add(k, len(s), "docs")
    for k, s in inv_docs.items():
        out["inv_doc_count"].add(k, len(s), "docs")
    # GR/IR per rule R-GRIR-001: GR value minus invoiced value at PO price
    grir = Acc()
    for k in set(out["gr_value"].v) | set(out["inv_value_po_price"].v):
        grir.v[k] = out["gr_value"].v.get(k, D(0)) - out["inv_value_po_price"].v.get(k, D(0))
        grir.ids[k] = out["gr_value"].ids.get(k, []) + out["inv_value_po_price"].ids.get(k, [])
    out["grir_balance"] = grir
    liab = Acc()
    for o in m["open_items"]:
        liab.add((o["system"], o["bukrs"], o["supplier"], o["ccy"]), o["open"], f"{o['system']}|{o['doc']}")
        out["supplier_open_items"].add((o["system"], o["bukrs"], o["ccy"]), 0 if o["cleared"] else 1, f"{o['system']}|{o['doc']}")
        out["supplier_cleared_items"].add((o["system"], o["bukrs"], o["ccy"]), 1 if o["cleared"] else 0, f"{o['system']}|{o['doc']}")
    out["supplier_liability"] = liab
    for j in m["journal"]:
        rep = j["reported_by"]
        bukrs = j["rbukrs"]
        out["gl_balance"].add((rep, bukrs, j["poper"], j["racct"]), j["hsl"], j["id"])
        out["debit_total"].add((rep, bukrs, j["poper"]), j["hsl"] if j["hsl"] > 0 else 0, j["id"])
        out["credit_total"].add((rep, bukrs, j["poper"]), -j["hsl"] if j["hsl"] < 0 else 0, j["id"])
        out["fi_line_count"].add((rep, bukrs, j["poper"]), 1, j["id"])
    return out


def run_bdc(world: dict, scenario: str, defects: tuple = ()) -> dict:
    acq = acquire(world, defects)
    model = transform(acq, scenario, defects)
    return {"acq": acq, "model": model, "measures": measures(model, scenario)}
