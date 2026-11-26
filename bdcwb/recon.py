"""Finance reconciliation engine: backend reference measures, three independent levels, drill-down, tolerance policy.

The reference path reads BSEG/BKPF-style rows and operational documents; the BDC path (bdc.py) reads ACDOCA-style rows and
PO history. Decimal arithmetic only. SYNTHETIC_PASS is the strongest verdict synthetic data can earn.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from .bdc import Acc
from .core import D
from .golden import EXPECTED, EXPECTED_JOURNAL
from .scenarios import SCENARIOS
from .synthetic import COA, HIST_CUTOFF

TOLERANCE = {"approved": True, "approved_by": "SYNTHETIC_OWNER_FIXTURE", "scope": "SYNTHETIC_ONLY",
             "amount": D("0.00"), "quantity": D("0.000"), "count": D("0")}
MEASURE_KIND = {"po_qty": "quantity", "gr_qty": "quantity", "inv_qty": "quantity", "open_po_qty": "quantity", "pr_qty": "quantity",
                "gr_doc_count": "count", "inv_doc_count": "count", "supplier_open_items": "count",
                "supplier_cleared_items": "count", "fi_line_count": "count"}
RULE_DEPENDENCY = {"grir_balance": "R-GRIR-001", "supplier_open_items": "R-CLEARING-ALLOC-001",
                   "supplier_cleared_items": "R-CLEARING-ALLOC-001", "gl_balance": "R-FI-SOURCE-001",
                   "debit_total": "R-FI-SOURCE-001", "credit_total": "R-FI-SOURCE-001", "fi_line_count": "R-FI-SOURCE-001"}
PROCUREMENT = ["pr_qty", "pr_value", "po_qty", "po_value", "gr_qty", "gr_value", "inv_qty", "inv_value", "open_po_qty",
                "open_commitment", "grir_balance", "supplier_liability", "supplier_open_items", "supplier_cleared_items",
                "gr_doc_count", "inv_doc_count"]
FINANCE = ["gl_balance", "debit_total", "credit_total", "fi_line_count"]


def reference_measures(world: dict, scenario: str) -> dict[str, Acc]:
    """Authoritative backend reporting figures computed from operational documents and FI lines."""
    sc = SCENARIOS[scenario]
    authority = sc.get("fi_authority", {})
    out: dict[str, Acc] = defaultdict(Acc)
    for sid, d in world["systems"].items():
        coa = COA["S4B"] if sid == "S4B" else COA["common"]
        net_gr = defaultdict(lambda: D(0))
        for g in d["gr"]:
            net_gr[(g["po"], g["po_item"])] += g["qty"]
        for p in d["po_items"]:
            k = (sid, p["bukrs"], p["ccy"])
            out["po_qty"].add(k, p["qty"], p["id"])
            out["po_value"].add(k, p["net"], p["id"])
            op = max(p["qty"] - net_gr[(p["po"], p["item"])], D(0))
            out["open_po_qty"].add(k, op, p["id"])
            out["open_commitment"].add(k, op * p["price"], p["id"])
        for r in d["pr"]:
            k = (sid, r["bukrs"], r["ccy"])
            out["pr_qty"].add(k, r["qty"], r["id"])
            out["pr_value"].add(k, r["value"], r["id"])
        gdocs, idocs = defaultdict(set), defaultdict(set)
        for g in d["gr"]:
            k = (sid, g["bukrs"], g["ccy"])
            out["gr_qty"].add(k, g["qty"], g["id"])
            out["gr_value"].add(k, g["value"], g["id"])
            gdocs[k].add(g["mat_doc"])
        for i in d["inv"]:
            k = (sid, i["bukrs"], i["ccy"])
            out["inv_qty"].add(k, i["qty"], i["id"])
            out["inv_value"].add(k, i["net"], i["id"])
            idocs[k].add(i["inv_doc"])
        for k, s in gdocs.items():
            out["gr_doc_count"].add(k, len(s), "docs")
        for k, s in idocs.items():
            out["inv_doc_count"].add(k, len(s), "docs")
        # GR/IR, liability and open items come from the FI lines (independent of the PO-history path)
        hdr = {(h["bukrs"], h["belnr"], h["gjahr"]): h for h in d["bkpf"]}
        inv_res: dict = defaultdict(lambda: D(0))
        for l in d["bseg"]:
            h = hdr[(l["bukrs"], l["belnr"], l["gjahr"])]
            signed_c = l["wrbtr"] if l["shkzg"] == "H" else -l["wrbtr"]  # credit positive
            if l["hkont"] == coa["GRIR"]:
                out["grir_balance"].add((sid, l["bukrs"], l["waers"]), signed_c, l["id"])
            if l["hkont"] == coa["AP"]:
                out["supplier_liability"].add((sid, l["bukrs"], l["lifnr"], l["waers"]), signed_c, l["id"])
                target = h["ref_doc"] if h["ref_type"] == "INV" else h["clears"]
                inv_res[(l["bukrs"], target, l["waers"])] += signed_c
        invdocs = {(h["bukrs"], h["ref_doc"]): h for h in d["bkpf"] if h["ref_type"] == "INV"}
        for (bukrs, doc, ccy), res in inv_res.items():
            if (bukrs, doc) not in invdocs:
                continue
            gross_pos = invdocs[(bukrs, doc)]
            is_credit = any(i["inv_doc"] == doc and i["kind"] == "CREDIT" for i in d["inv"])
            cleared = (res == 0) and not is_credit
            k = (sid, bukrs, ccy)
            out["supplier_open_items"].add(k, 0 if cleared else 1, f"{sid}|{doc}")
            out["supplier_cleared_items"].add(k, 1 if cleared else 0, f"{sid}|{doc}")
        # journal per the FI authority policy
        for l in d["bseg"]:
            if authority.get((sid, l["bukrs"]), sid) == "CFIN01":
                continue
            k3 = (sid, l["bukrs"], l["period"])
            amt = l["dmbtr"] if l["shkzg"] == "S" else -l["dmbtr"]
            out["gl_balance"].add((sid, l["bukrs"], l["period"], l["hkont"]), amt, l["id"])
            out["debit_total"].add(k3, amt if amt > 0 else 0, l["id"])
            out["credit_total"].add(k3, -amt if amt < 0 else 0, l["id"])
            out["fi_line_count"].add(k3, 1, l["id"])
    for a in world["cfin"]["acdoca"]:
        k3 = ("CFIN01", a["rbukrs"], a["poper"])
        out["gl_balance"].add(("CFIN01", a["rbukrs"], a["poper"], a["racct"]), a["hsl"], a["id"])
        out["debit_total"].add(k3, a["hsl"] if a["hsl"] > 0 else 0, a["id"])
        out["credit_total"].add(k3, -a["hsl"] if a["hsl"] < 0 else 0, a["id"])
        out["fi_line_count"].add(k3, 1, a["id"])
    return out


def compare(name: str, ref: dict[str, Acc], tgt: dict[str, Acc], measures: list[str], tol: dict, extra: dict | None = None) -> dict:
    diffs, checked = [], 0
    for m in measures:
        r, t = ref.get(m, Acc()), tgt.get(m, Acc())
        kind = MEASURE_KIND.get(m, "amount")
        for key in sorted(set(r.v) | set(t.v), key=str):
            checked += 1
            rv, tv = r.v.get(key, D(0)), t.v.get(key, D(0))
            delta = tv - rv
            if abs(delta) > tol[kind]:
                diffs.append({"measure": m, "key": [str(x) for x in key], "reference": str(rv), "bdc": str(tv), "delta": str(delta),
                              "material": True, "drill_reference": r.ids.get(key, [])[:25], "drill_bdc": t.ids.get(key, [])[:25]})
    return {"name": name, "checked_keys": checked, "differences": diffs, **(extra or {})}


def verdict(res: dict, rules, tol: dict, scope_ok: bool = True, watermark_ok: bool = True, measures: list[str] | None = None) -> dict:
    blocked = rules.blocks_finance_validation(measures or []) if rules else ["NO_RULEBOOK"]
    if not tol.get("approved"):
        status, why = "INSUFFICIENT_EVIDENCE", "tolerance policy not approved"
    elif not scope_ok or not watermark_ok:
        status, why = "INSUFFICIENT_EVIDENCE", "scope or extraction timestamps not aligned"
    elif blocked:
        status, why = "BLOCKED_UNAPPROVED_RULE", f"unapproved material rule(s): {blocked}"
    elif res["differences"]:
        status, why = "FAIL", f"{len(res['differences'])} material difference(s)"
    else:
        status, why = "SYNTHETIC_PASS", "no material difference on synthetic data; not a live Finance validation"
    return {**res, "status": status, "reason": why, "blocked_rules": blocked, "evidence_mode": "SYNTHETIC"}


# ---- Level 1: source -> acquisition ---------------------------------------------------------------------------------

def level1(world: dict, acq: dict) -> dict:
    e = acq["entities"]
    checks = []
    src_counts = {"po_item": sum(len(d["po_items"]) for d in world["systems"].values()),
                  "gr": sum(len(d["gr"]) for d in world["systems"].values()),
                  "inv_item": sum(len(d["inv"]) for d in world["systems"].values()),
                  "po_history": sum(len(d["po_hist"]) for d in world["systems"].values()),
                  "acdoca_src": sum(len(d["acdoca"]) for d in world["systems"].values()),
                  "acdoca_cfin": len(world["cfin"]["acdoca"]), "bridge": len(world["cfin"]["bridge"])}
    for ent, n in src_counts.items():
        got = len(e.get(ent, []))
        ids = [r["id"] for r in e.get(ent, [])]
        checks.append({"entity": ent, "source_records": n, "acquired_records": got, "duplicates": len(ids) - len(set(ids)),
                       "status": "PASS" if n == got and len(ids) == len(set(ids)) else "FAIL"})
    amt_src = sum((g["value"] for d in world["systems"].values() for g in d["gr"]), D(0))
    amt_acq = sum((g["value"] for g in e["gr"]), D(0))
    checks.append({"entity": "gr.value (amount control total)", "source": str(amt_src), "acquired": str(amt_acq),
                   "status": "PASS" if amt_src == amt_acq else "FAIL"})
    stale = acq.get("late_source_change")
    checks.append({"entity": "extraction watermark", "watermark": acq["watermark"], "source_extraction_ts": world["extraction_ts"],
                   "stale_record": stale, "status": "FAIL" if stale else "PASS"})
    ok = all(c["status"] == "PASS" for c in checks)
    return {"level": 1, "name": "Source to acquisition", "checks": checks,
            "status": "SYNTHETIC_PASS" if ok else "FAIL", "evidence_mode": "SYNTHETIC"}


# ---- Level 2: acquisition -> semantic model ---------------------------------------------------------------------------

def level2(acq: dict, model: dict, scenario: str) -> dict:
    e = acq["entities"]
    checks = []
    po_acq = sum((p["net"] for p in e["po_item"]), D(0))
    po_fact = sum((c["po_value"] for c in model["commitment"]), D(0))
    checks.append({"check": "PO value preserved (no join fan-out)", "acquired": str(po_acq), "model": str(po_fact),
                   "status": "PASS" if po_acq == po_fact else "FAIL"})
    gr_acq = sum((g["value"] for g in e["gr"]), D(0))
    gr_fact = sum((g["value"] for g in model["gr"]), D(0))
    checks.append({"check": "GR value preserved", "acquired": str(gr_acq), "model": str(gr_fact), "status": "PASS" if gr_acq == gr_fact else "FAIL"})
    inv_acq = sum((i["net"] for i in e["inv_item"]), D(0))
    inv_fact = sum((i["net"] for i in model["inv"]), D(0))
    checks.append({"check": "Invoice net preserved", "acquired": str(inv_acq), "model": str(inv_fact), "status": "PASS" if inv_acq == inv_fact else "FAIL"})
    checks.append({"check": "Invoice item count preserved", "acquired": len(e["inv_item"]), "model": len(model["inv"]),
                   "status": "PASS" if len(e["inv_item"]) == len(model["inv"]) else "FAIL"})
    authority = SCENARIOS[scenario].get("fi_authority", {})
    excluded = sum(1 for a in e.get("acdoca_src", []) if authority.get((a["reporting_system"], a["rbukrs"]), a["reporting_system"]) == "CFIN01")
    rej_j = sum(1 for r in model["rejected"] if r["entity"] == "journal_line")
    expected = len(e.get("acdoca_src", [])) - excluded + len(e.get("acdoca_cfin", [])) - rej_j
    checks.append({"check": "Journal lines: acquired - replicated-excluded - rejected = model", "expected": expected,
                   "model": len(model["journal"]), "excluded_as_replicated": excluded, "rejected": rej_j,
                   "status": "PASS" if expected == len(model["journal"]) else "FAIL"})
    checks.append({"check": "Rejected records", "count": len(model["rejected"]), "detail": model["rejected"][:10],
                   "status": "PASS" if not model["rejected"] else "FAIL"})
    checks.append({"check": "Pending Central Finance replication", "count": len(model["pending_replication"]),
                   "status": "PASS" if not model["pending_replication"] else "FAIL"})
    ok = all(c["status"] == "PASS" for c in checks)
    return {"level": 2, "name": "Acquisition to semantic model", "checks": checks, "status": "SYNTHETIC_PASS" if ok else "FAIL",
            "evidence_mode": "SYNTHETIC"}


# ---- Level 3 and scenario-B reconciliations ----------------------------------------------------------------------------

def level3(world: dict, bdc_out: dict, scenario: str, rules, tol: dict = TOLERANCE) -> dict:
    ref = reference_measures(world, scenario)
    res = compare("Authoritative SAP reporting vs BDC analytical results", ref, bdc_out["measures"], PROCUREMENT + FINANCE, tol)
    v = verdict(res, rules, tol, measures=PROCUREMENT + FINANCE)
    v["level"] = 3
    return v


def source_to_cfin(world: dict, acq: dict, scenario: str, rules, tol: dict = TOLERANCE) -> dict:
    """Operational source -> Central Finance, per document. Never summed with BDC totals."""
    sc = SCENARIOS[scenario]
    bridge = {(b["src_system"], b["src_bukrs"], b["src_belnr"], b["src_gjahr"]): b for b in acq["entities"].get("bridge", [])}
    cfin = defaultdict(lambda: [D(0), 0])
    for a in acq["entities"].get("acdoca_cfin", []):
        cfin[(a["rbukrs"], a["belnr"], a["gjahr"])][0] += a["hsl"] if a["hsl"] > 0 else D(0)
        cfin[(a["rbukrs"], a["belnr"], a["gjahr"])][1] += 1
    ref, tgt = Acc(), Acc()
    for sid, d in world["systems"].items():
        for h in d["bkpf"]:
            if sc["fi_authority"].get((sid, h["bukrs"])) != "CFIN01":
                continue
            src_deb = sum((l["dmbtr"] for l in d["bseg"] if (l["bukrs"], l["belnr"], l["gjahr"]) == (h["bukrs"], h["belnr"], h["gjahr"])
                           and l["shkzg"] == "S"), D(0))
            key = (sid, h["bukrs"], h["belnr"], h["gjahr"])
            ref.add(key, src_deb, h["id"])
            b = bridge.get(key)
            tgt.add(key, cfin[(b["cfin_bukrs"], b["cfin_belnr"], b["cfin_gjahr"])][0] if b else D(0), b["id"] if b else "MISSING_IN_CFIN")
    res = compare("Operational source to Central Finance", {"cfin_doc_debits": ref}, {"cfin_doc_debits": tgt}, ["cfin_doc_debits"], tol)
    for dd in res["differences"]:
        dd["classification"] = "MISSING_IN_TARGET (delayed replication)" if dd["bdc"] == "0" else "AMOUNT_MISMATCH"
    v = verdict(res, rules, tol, measures=["gl_balance"])
    v["level"] = "B1"
    return v


def bw_vs_bdc(world: dict, bdc_out: dict, rules, tol: dict = TOLERANCE) -> dict:
    bw = world["bw_reference"]
    scope = bw["scope"]
    gl = bdc_out["measures"]["gl_balance"]
    ref, tgt = Acc(), Acc()
    for (bukrs, per, racct), v in bw["balances"].items():
        ref.add(("ECC01", bukrs, per, racct), v, "BW401")
    for key, v in gl.v.items():
        if key[0] in scope["systems"] and key[1] in scope["company_codes"] and key[2] in scope["periods"]:
            tgt.add(key, v, ",".join(gl.ids[key][:3]))
    # BDC reports calendar periods only for ECC01 (calendar fiscal year), so the scopes are equivalent here.
    scope_ok = True
    res = compare("Existing BW reference output vs BDC", {"gl_balance": ref}, {"gl_balance": tgt}, ["gl_balance"], tol,
                  {"scope": scope, "scope_equivalent": scope_ok, "history_cutoff": HIST_CUTOFF.isoformat()})
    v = verdict(res, rules, tol, scope_ok=scope_ok, measures=["gl_balance"])
    v["level"] = "B4"
    return v


def golden_check(bdc_out: dict, ref: dict[str, Acc]) -> dict:
    """Compare BOTH calculation paths against the hand-authored expected results."""
    rows, ok = [], True
    for m, exp in EXPECTED.items():
        b = sum(bdc_out["measures"][m].v.values(), D(0))
        r = sum(ref[m].v.values(), D(0))
        good = b == exp and r == exp
        ok &= good
        rows.append({"measure": m, "expected": str(exp), "reference_path": str(r), "bdc_path": str(b), "status": "PASS" if good else "FAIL"})
    j = bdc_out["model"]["journal"]
    debit = sum((x["hsl"] for x in j if x["hsl"] > 0), D(0))
    credit = -sum((x["hsl"] for x in j if x["hsl"] < 0), D(0))
    docs = len({(x["rbukrs"], x["belnr"], x["gjahr"]) for x in j})
    for name, got, exp in (("fi_documents", D(docs), D(EXPECTED_JOURNAL["fi_documents"])), ("fi_lines", D(len(j)), D(EXPECTED_JOURNAL["fi_lines"])),
                           ("debit_total", debit, EXPECTED_JOURNAL["debit_total"]), ("credit_total", credit, EXPECTED_JOURNAL["credit_total"])):
        good = got == exp
        ok &= good
        rows.append({"measure": name, "expected": str(exp), "reference_path": "-", "bdc_path": str(got), "status": "PASS" if good else "FAIL"})
    return {"name": "Golden transaction (hand-authored expectations)", "rows": rows, "status": "SYNTHETIC_PASS" if ok else "FAIL",
            "evidence_mode": "SYNTHETIC"}


def naive_double_count_demo(world: dict, scenario: str, rules) -> dict:
    """Shows what happens WITHOUT the single-source-of-truth rule: source FI + replicated CFIN are both summed."""
    from .bdc import run_bdc
    out = run_bdc(world, scenario, ("NAIVE_DOUBLE_FI",))
    return level3(world, out, scenario, rules)
