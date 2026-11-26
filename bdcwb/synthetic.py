"""Deterministic, relationally consistent SYNTHETIC Procure-to-Pay data for Scenario A and B.

Seeded (configurable). Every posting is balanced. Document numbers deliberately collide across systems. Nothing here is
derived from, or represents, a real SAP system or customer.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from .core import CCY_DECIMALS, FX_TO_INR, D, qccy, qqty
from .scenarios import SCENARIOS

# chart of accounts per system family; S4B uses its own numbering (mapped to the common chart in CFIN)
COA = {"common": dict(INV="300000", EXP="400000", GRIR="191100", AP="160000", BANK="113100", TAX="154000", PD="399000"),
       "S4B": dict(INV="5000100", EXP="6000100", GRIR="2100100", AP="2000100", BANK="1100100", TAX="1500100", PD="7000100")}
GL_MAP_S4B_TO_COMMON = {v: COA["common"][k] for k, v in COA["S4B"].items()}
CC_MAP_TO_CFIN = {("S4B", "1000"): "2000"}
SUPPLIERS = {sid: [f"{100000 + n}" for n in range(1, 9)] for sid in ("ECC01", "S4A", "S4B")}
HIST_CUTOFF = date(2026, 6, 30)
TAX_RATE = Decimal("0.18")
START = date(2026, 1, 1)


def fiscal(system: str, d: date) -> tuple[int, int]:
    """(fiscal year, period). S4B uses an April-start fiscal year; the others use the calendar year."""
    if system == "S4B":
        return (d.year if d.month >= 4 else d.year - 1, (d.month - 4) % 12 + 1)
    return d.year, d.month


def lc(amount: Decimal, doc_ccy: str, lc_ccy: str) -> Decimal:
    return qccy(amount * FX_TO_INR[doc_ccy] / FX_TO_INR[lc_ccy], lc_ccy)


class SysData:
    def __init__(self, sid: str, client: str):
        self.sid, self.client = sid, client
        self.pr, self.po_items, self.po_acct, self.po_hist = [], [], [], []
        self.gr, self.inv, self.pay = [], [], []
        self.bkpf, self.bseg, self.acdoca = [], [], []
        self.n_po, self.n_mat, self.n_fi, self.n_inv = 4500000000, 5000000000, 1900000000, 5100000000  # SAME counters in every system

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items() if isinstance(v, list)}


def _post(sd: SysData, bukrs: str, cc_ccy: str, dt: date, ref_type: str, ref_doc: str, lines: list[tuple], ccy: str,
          supplier: str | None, po: str | None, clears: str | None = None) -> str:
    """lines: (account_key, 'D'|'C', amount_doc_ccy, cost_center|None). Posts BKPF/BSEG/ACDOCA-style rows, balanced in LC."""
    sd.n_fi += 1
    belnr = str(sd.n_fi)
    gjahr, per = fiscal(sd.sid, dt)
    coa = COA["S4B"] if sd.sid == "S4B" else COA["common"]
    lcs = []
    for key, dc, amt, cc in lines:
        lcs.append(lc(amt, ccy, cc_ccy))
    dsum = sum(v for (k, dc, a, c), v in zip(lines, lcs) if dc == "D")
    csum = sum(v for (k, dc, a, c), v in zip(lines, lcs) if dc == "C")
    if dsum != csum:  # rounding residual goes to the largest credit line so the document balances in LC
        idx = max((i for i, l in enumerate(lines) if l[1] == "C"), key=lambda i: lcs[i])
        lcs[idx] += dsum - csum
    sd.bkpf.append({"id": f"{sd.sid}|BKPF|{bukrs}|{belnr}|{gjahr}", "system": sd.sid, "client": sd.client, "bukrs": bukrs,
                    "belnr": belnr, "gjahr": gjahr, "period": per, "date": dt.isoformat(), "ccy": ccy, "lc_ccy": cc_ccy,
                    "ref_type": ref_type, "ref_doc": ref_doc, "supplier": supplier, "po": po, "clears": clears})
    for n, ((key, dc, amt, cost), l) in enumerate(zip(lines, lcs), 1):
        acct = coa[key]
        sd.bseg.append({"id": f"{sd.sid}|BSEG|{bukrs}|{belnr}|{gjahr}|{n:03d}", "system": sd.sid, "client": sd.client,
                        "bukrs": bukrs, "belnr": belnr, "gjahr": gjahr, "buzei": n, "hkont": acct, "shkzg": "S" if dc == "D" else "H",
                        "wrbtr": amt, "dmbtr": l, "waers": ccy, "hwaer": cc_ccy, "lifnr": supplier if key == "AP" else None,
                        "kostl": cost, "period": per, "date": dt.isoformat()})
        sd.acdoca.append({"id": f"{sd.sid}|ACDOCA|{bukrs}|{belnr}|{gjahr}|{n:06d}", "rldnr": "0L", "rbukrs": bukrs,
                          "gjahr": gjahr, "belnr": belnr, "docln": f"{n:06d}", "racct": acct, "hsl": l if dc == "D" else -l,
                          "rhcur": cc_ccy, "rwcur": ccy, "wsl": amt if dc == "D" else -amt, "drcrk": "S" if dc == "D" else "H",
                          "poper": per, "lifnr": supplier if key == "AP" else None, "rcntr": cost, "src_system": sd.sid,
                          "client": sd.client, "budat": dt.isoformat()})
    return belnr


def _gen_pos(sd: SysData, rng: random.Random, bukrs: str, cc_ccy: str, n: int, golden_first: bool, offset: int = 0) -> None:
    sup = SUPPLIERS[sd.sid]
    for i in range(n):
        gold = golden_first and i == 0
        k = i + offset
        sd.n_po += 1
        po = str(sd.n_po)
        ccy = cc_ccy if (k % 6 != 0 or gold or k == 0) else "EUR"
        if cc_ccy == "INR" and ccy == "EUR":
            ccy = "USD"
        d0 = START + timedelta(days=(k * 7) % 250)
        supplier = sup[k % len(sup)]
        n_items = 1 if gold else 1 + (k % 3)
        for it in range(1, n_items + 1):
            if gold:
                qty, price, mat = D(100), D(100), "MAT-GOLD"
            else:
                qty = D(10 + rng.randrange(0, 90) * 5)
                price = qccy(D(10 + rng.randrange(0, 400)) + D(rng.randrange(0, 100)) / D(100), ccy)
                mat = f"MAT-{(k * 3 + it) % 25:03d}"
            item = f"{it * 10:05d}"
            net = qccy(qty * price, ccy)
            acct2 = (k % 4 == 0 and not gold)
            sd.po_items.append({"id": f"{sd.sid}|EKPO|{po}|{item}", "system": sd.sid, "client": sd.client, "po": po, "item": item,
                                "bukrs": bukrs, "supplier": supplier, "material": mat, "qty": qty, "unit": "EA", "price": price,
                                "peinh": 1, "net": net, "ccy": ccy, "date": d0.isoformat(), "golden": gold,
                                "zz_safety_class": "A" if k % 5 == 0 else None})
            if acct2:
                a1 = qccy(net * D("0.6"), ccy)
                for n_, (cc_, amt) in enumerate((("CC1000", a1), ("CC2000", net - a1)), 1):
                    sd.po_acct.append({"id": f"{sd.sid}|EKKN|{po}|{item}|{n_:02d}", "system": sd.sid, "po": po, "item": item,
                                       "seq": n_, "cost_center": cc_, "amount": amt, "ccy": ccy})
            else:
                sd.po_acct.append({"id": f"{sd.sid}|EKKN|{po}|{item}|01", "system": sd.sid, "po": po, "item": item, "seq": 1,
                                   "cost_center": None, "amount": net, "ccy": ccy})
            if k % 2 == 0 or gold:
                sd.pr.append({"id": f"{sd.sid}|EBAN|PR{po}|{item}", "system": sd.sid, "pr": f"PR{po}", "item": item, "qty": qty,
                              "price": price, "value": net, "ccy": ccy, "bukrs": bukrs})
            _flow(sd, rng, bukrs, cc_ccy, k, gold, po, item, supplier, qty, price, ccy, d0, acct2)


def _gr(sd, bukrs, cc_ccy, po, item, supplier, qty, price, ccy, dt, kind, acct2, cost=None):
    sd.n_mat += 1
    doc = str(sd.n_mat)
    value = qccy(abs(qty) * price, ccy) * (1 if qty > 0 else -1)
    sd.gr.append({"id": f"{sd.sid}|MATDOC|{doc}|2026|{item}", "system": sd.sid, "client": sd.client, "mat_doc": doc, "year": 2026,
                  "item": item, "po": po, "po_item": item, "qty": qty, "value": value, "ccy": ccy, "date": dt.isoformat(),
                  "kind": kind, "bukrs": bukrs})
    sd.po_hist.append({"id": f"{sd.sid}|EKBE|{po}|{item}|E|{doc}", "system": sd.sid, "po": po, "item": item, "type": "E",
                       "doc": doc, "qty": qty, "value": value, "ccy": ccy, "date": dt.isoformat()})
    dr, cr = ("D", "C") if qty > 0 else ("C", "D")
    mag = abs(value)
    dkey = "EXP" if acct2 else "INV"
    _post(sd, bukrs, cc_ccy, dt, "GR", doc, [(dkey, dr, mag, "CC1000" if acct2 else None), ("GRIR", cr, mag, None)], ccy, supplier, po)


def _inv(sd, bukrs, cc_ccy, po, item, supplier, qty, po_price, inv_price, ccy, dt, taxed, kind="INV"):
    sd.n_inv += 1
    doc = str(sd.n_inv)
    sign = 1 if kind == "INV" else -1
    net_po = qccy(qty * po_price, ccy)
    net_inv = qccy(qty * inv_price, ccy)
    diff = net_inv - net_po
    tax = qccy(net_inv * TAX_RATE, ccy) if taxed else D(0)
    gross = net_po + diff + tax
    sd.inv.append({"id": f"{sd.sid}|RSEG|{doc}|2026|{item}", "system": sd.sid, "client": sd.client, "inv_doc": doc, "year": 2026,
                   "item": item, "po": po, "po_item": item, "qty": qty * sign, "net_po": net_po * sign, "net": net_inv * sign,
                   "price_diff": diff * sign, "tax": tax * sign, "gross": gross * sign, "ccy": ccy, "date": dt.isoformat(),
                   "kind": kind, "supplier": supplier, "bukrs": bukrs})
    sd.po_hist.append({"id": f"{sd.sid}|EKBE|{po}|{item}|Q|{doc}", "system": sd.sid, "po": po, "item": item, "type": "Q",
                       "doc": doc, "qty": qty * sign, "value": net_inv * sign, "ccy": ccy, "date": dt.isoformat()})
    lines = [("GRIR", "D", net_po, None)]
    if diff:
        lines.append(("PD", "D" if diff > 0 else "C", abs(diff), None))
    if tax:
        lines.append(("TAX", "D", tax, None))
    lines.append(("AP", "C", gross, None))
    if kind == "CREDIT":
        lines = [(k, "C" if dc == "D" else "D", a, c) for k, dc, a, c in lines]
    _post(sd, bukrs, cc_ccy, dt, "INV", doc, lines, ccy, supplier, po)
    return doc, gross * sign


def _pay(sd, bukrs, cc_ccy, supplier, inv_doc, amount, ccy, dt, po, full):
    sd.pay.append({"id": f"{sd.sid}|PAY|{inv_doc}|{len(sd.pay) + 1}", "system": sd.sid, "client": sd.client, "inv_doc": inv_doc,
                   "amount": amount, "ccy": ccy, "date": dt.isoformat(), "supplier": supplier, "bukrs": bukrs, "full": full})
    _post(sd, bukrs, cc_ccy, dt, "PAY", f"PAY{inv_doc}", [("AP", "D", amount, None), ("BANK", "C", amount, None)], ccy, supplier,
          po, clears=inv_doc)


def _flow(sd, rng, bukrs, cc_ccy, k, gold, po, item, supplier, qty, price, ccy, d0, acct2):
    g1 = d0 + timedelta(days=5)
    if gold:
        _gr(sd, bukrs, cc_ccy, po, item, supplier, D(60), price, ccy, g1, "GR", False)
        _gr(sd, bukrs, cc_ccy, po, item, supplier, D(40), price, ccy, g1 + timedelta(days=3), "GR", False)
        d1, a1 = _inv(sd, bukrs, cc_ccy, po, item, supplier, D(60), price, price, ccy, g1 + timedelta(days=7), False)
        _inv(sd, bukrs, cc_ccy, po, item, supplier, D(40), price, price, ccy, g1 + timedelta(days=10), False)
        _pay(sd, bukrs, cc_ccy, supplier, d1, a1, ccy, g1 + timedelta(days=20), po, True)
        return
    partial = k % 10 == 0
    recv = qqty(qty / 2) if partial else qty
    taxed = k % 3 == 0
    inv_price = qccy(price * D("1.02"), ccy) if k % 5 == 0 else price
    if k % 13 == 0:  # GR, full reversal, re-GR
        _gr(sd, bukrs, cc_ccy, po, item, supplier, recv, price, ccy, g1, "GR", acct2)
        _gr(sd, bukrs, cc_ccy, po, item, supplier, -recv, price, ccy, g1 + timedelta(days=1), "REVERSAL", acct2)
        _gr(sd, bukrs, cc_ccy, po, item, supplier, recv, price, ccy, g1 + timedelta(days=2), "GR", acct2)
    elif k % 3 == 1 and not partial:  # two receipts, 60/40
        r1 = qqty(recv * D("0.6"))
        _gr(sd, bukrs, cc_ccy, po, item, supplier, r1, price, ccy, g1, "GR", acct2)
        _gr(sd, bukrs, cc_ccy, po, item, supplier, recv - r1, price, ccy, g1 + timedelta(days=4), "GR", acct2)
    else:
        _gr(sd, bukrs, cc_ccy, po, item, supplier, recv, price, ccy, g1, "GR", acct2)
    net_recv = recv
    if k % 7 == 0 and not partial:  # return of 10%
        ret = qqty(recv * D("0.1"))
        _gr(sd, bukrs, cc_ccy, po, item, supplier, -ret, price, ccy, g1 + timedelta(days=6), "RETURN", acct2)
        net_recv = recv - ret
    i_date = g1 + timedelta(days=12)
    doc, gross = _inv(sd, bukrs, cc_ccy, po, item, supplier, net_recv, price, inv_price, ccy, i_date, taxed)
    total_gross = gross
    if k % 11 == 0 and not partial:  # credit memo for 20% of the invoiced quantity
        cq = qqty(net_recv * D("0.2"))
        _, cg = _inv(sd, bukrs, cc_ccy, po, item, supplier, cq, price, inv_price, ccy, i_date + timedelta(days=3), taxed, "CREDIT")
        total_gross += cg
    if k % 9 == 0:
        return  # unpaid
    if k % 2 == 0:
        _pay(sd, bukrs, cc_ccy, supplier, doc, gross, ccy, i_date + timedelta(days=15), po, True)
    else:
        _pay(sd, bukrs, cc_ccy, supplier, doc, qccy(gross / 2, ccy), ccy, i_date + timedelta(days=15), po, False)


def generate(scenario: str = "A", seed: int | None = None, n_po: dict | None = None, defects: tuple = ()) -> dict:
    """Return the synthetic SOURCE world. Defects are applied later (acquisition/model level), not here."""
    sc = SCENARIOS[scenario]
    seed = sc["seed"] if seed is None else seed
    rng = random.Random(seed)
    world: dict = {"scenario": scenario, "seed": seed, "systems": {}, "extraction_ts": "2026-11-26T06:00:00Z",
                   "evidence_mode": "SYNTHETIC", "fixture_version": "bdcwb-synth-1"}
    for sid in sc["sources"]:
        from .scenarios import SYSTEMS
        sd = SysData(sid, SYSTEMS[sid]["client"])
        counts = (n_po or sc["n_po"])[sid]
        ccs = sc["company_codes"][sid]
        per = [counts // len(ccs)] * len(ccs)
        per[0] += counts - sum(per)
        off = 0
        for ci, ((bukrs, ccy), n) in enumerate(zip(ccs, per)):
            _gen_pos(sd, rng, bukrs, ccy, n, golden_first=(scenario == "A" and sid == "S4A" and ci == 0), offset=off)
            off += n
        world["systems"][sid] = sd.as_dict() | {"client": sd.client}
    world["cfin"] = _replicate_cfin(world, sc) if scenario == "B" else {"bkpf": [], "acdoca": [], "bridge": []}
    world["masters"] = {"supplier_map": {(sid, s): f"BP-{sid}-{s}" for sid in world["systems"] for s in SUPPLIERS[sid]},
                        "company_code_map": {f"{a}|{b}": c for (a, b), c in CC_MAP_TO_CFIN.items()},
                        "gl_map_s4b": dict(GL_MAP_S4B_TO_COMMON)}
    world["bw_reference"] = bw_reference(world, sc) if scenario == "B" else None
    return world


def _replicate_cfin(world: dict, sc: dict) -> dict:
    """Central Finance replicates ONLY the FI documents of (system, company code) pairs whose authority is CFIN01."""
    out = {"bkpf": [], "acdoca": [], "bridge": []}
    n = 1900000000  # same starting counter as the source systems -> colliding document numbers
    cc_ccy = {}
    for sid, ccs in sc["company_codes"].items():
        for b, c in ccs:
            cc_ccy[(sid, b)] = c
    for sid, d in world["systems"].items():
        sm = {(h["bukrs"], h["belnr"], h["gjahr"]): h for h in d["bkpf"]}
        for h in d["bkpf"]:
            if sc["fi_authority"].get((sid, h["bukrs"])) != "CFIN01":
                continue
            n += 1
            tb = CC_MAP_TO_CFIN.get((sid, h["bukrs"]), h["bukrs"])
            gj, per = fiscal("CFIN01", date.fromisoformat(h["date"]))
            out["bkpf"].append({"id": f"CFIN01|BKPF|{tb}|{n}|{gj}", "bukrs": tb, "belnr": str(n), "gjahr": gj, "period": per,
                                "date": h["date"], "src_system": sid, "src_bukrs": h["bukrs"], "src_belnr": h["belnr"],
                                "src_gjahr": h["gjahr"], "ccy": h["ccy"], "lc_ccy": h["lc_ccy"]})
            out["bridge"].append({"id": f"CFIN01|MAP|{sid}|{h['bukrs']}|{h['belnr']}|{h['gjahr']}", "src_system": sid,
                                  "src_bukrs": h["bukrs"], "src_belnr": h["belnr"], "src_gjahr": h["gjahr"], "cfin_bukrs": tb,
                                  "cfin_belnr": str(n), "cfin_gjahr": gj})
            for a in d["acdoca"]:
                if a["rbukrs"] == h["bukrs"] and a["belnr"] == h["belnr"] and a["gjahr"] == h["gjahr"]:
                    acct = GL_MAP_S4B_TO_COMMON.get(a["racct"], a["racct"]) if sid == "S4B" else a["racct"]
                    out["acdoca"].append({**a, "id": f"CFIN01|ACDOCA|{tb}|{n}|{gj}|{a['docln']}", "rbukrs": tb, "belnr": str(n),
                                          "gjahr": gj, "poper": per, "racct": acct, "src_system": "CFIN01",
                                          "origin": {"system": sid, "bukrs": h["bukrs"], "belnr": h["belnr"], "gjahr": h["gjahr"]},
                                          "lifnr": ("BP-%s-%s" % (sid, a["lifnr"])) if a["lifnr"] else None})
    return out


def bw_reference(world: dict, sc: dict) -> dict:
    """Existing BW401 historical output: G/L balances per period for ECC01 company code 0100 up to the history cutoff.

    Computed through its own path (a transformation over BSEG-style source lines with its own period rule).
    """
    rows: dict = {}
    for l in world["systems"]["ECC01"]["bseg"]:
        if l["bukrs"] != "0100" or date.fromisoformat(l["date"]) > HIST_CUTOFF:
            continue
        key = ("0100", int(l["date"][5:7]), l["hkont"])
        rows[key] = rows.get(key, D(0)) + (l["dmbtr"] if l["shkzg"] == "S" else -l["dmbtr"])
    return {"scope": {"systems": ["ECC01"], "company_codes": ["0100"], "periods": list(range(1, 7)), "currency": "INR",
                      "ledger": "0L"}, "balances": rows}
