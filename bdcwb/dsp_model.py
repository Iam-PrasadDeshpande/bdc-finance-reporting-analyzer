"""SAP Datasphere model-generation engine (layers 1-5) with grain validation and an offline SQLite functional check.

The SQL is portable ANSI-style SQL. The SQLite run proves the generated logic reproduces the measures on synthetic data; it is
NOT a Datasphere/HANA validation.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal

from .core import D

ACQ_DECISIONS = {"REUSE_STANDARD": "INSTALLED_PRODUCT", "KEY_USER_EXTENSION": "INSTALLED_PRODUCT",
                 "DEVELOPER_EXTENSION": "INSTALLED_PRODUCT", "DATA_PRODUCT_EXTENSION": "INSTALLED_PRODUCT",
                 "CREATE_CUSTOMER_MANAGED_PRODUCT": "REPLICATION_FLOW", "BW_DATA_PRODUCT_ROUTE": "BW_ACQUISITION",
                 "DATASPHERE_ENRICHMENT": "ENRICHMENT_SOURCE"}

TOL = Decimal("0.006")  # SQLite uses binary floats; amounts differ from Decimal only below half a minor unit
SQL = {
    "V_H_PO_ITEM": "SELECT system, po, item, bukrs, ccy, qty, price, net FROM po_item",
    "V_T_PO_HIST_AGG": ("SELECT system, po, item, SUM(CASE WHEN type = 'E' THEN qty ELSE 0 END) AS gr_qty, "
                        "SUM(CASE WHEN type = 'E' THEN value ELSE 0 END) AS gr_value FROM po_history GROUP BY system, po, item"),
    "V_T_INV_AGG": ("SELECT system, po, item, SUM(net_po) AS inv_value_po_price FROM inv_item GROUP BY system, po, item"),
    "FACT_COMMITMENT": ("SELECT p.system, p.bukrs, p.ccy, p.po, p.item, p.qty AS po_qty, p.net AS po_value, "
                        "COALESCE(h.gr_qty, 0) AS gr_qty, COALESCE(h.gr_value, 0) AS gr_value, "
                        "COALESCE(i.inv_value_po_price, 0) AS inv_value_po_price, "
                        "CASE WHEN p.qty - COALESCE(h.gr_qty, 0) > 0 THEN p.qty - COALESCE(h.gr_qty, 0) ELSE 0 END AS open_qty, "
                        "CASE WHEN p.qty - COALESCE(h.gr_qty, 0) > 0 THEN (p.qty - COALESCE(h.gr_qty, 0)) * p.price ELSE 0 END AS open_commitment "
                        "FROM V_H_PO_ITEM p LEFT JOIN V_T_PO_HIST_AGG h ON h.system = p.system AND h.po = p.po AND h.item = p.item "
                        "LEFT JOIN V_T_INV_AGG i ON i.system = p.system AND i.po = p.po AND i.item = p.item"),
    "V_T_INV_DOC": ("SELECT system, bukrs, ccy, supplier, inv_doc, SUM(gross) AS gross FROM inv_item GROUP BY system, bukrs, ccy, supplier, inv_doc"),
    "V_T_CLEARING_AGG": "SELECT system, inv_doc, SUM(amount) AS allocated FROM clearing GROUP BY system, inv_doc",
    "FACT_SUPPLIER_OPEN_ITEM": ("SELECT d.system, d.bukrs, d.ccy, d.supplier, d.inv_doc, d.gross, COALESCE(c.allocated, 0) AS allocated, "
                                "d.gross - COALESCE(c.allocated, 0) AS open_amount FROM V_T_INV_DOC d "
                                "LEFT JOIN V_T_CLEARING_AGG c ON c.system = d.system AND c.inv_doc = d.inv_doc"),
}
NAIVE_FANOUT_SQL = ("SELECT p.system, p.bukrs, p.ccy, SUM(p.net) AS po_value FROM po_item p "
                    "JOIN po_history h ON h.system = p.system AND h.po = p.po AND h.item = p.item GROUP BY p.system, p.bukrs, p.ccy")

FACTS = [
    {"name": "FACT_PROCUREMENT_COMMITMENT", "grain": "PO item", "keys": ["system", "po", "item"], "measures": {
        "po_value": "SUM", "po_qty": "SUM", "open_commitment": "SUM", "open_qty": "SUM"}, "dims": ["DIM_COMPANY_CODE", "DIM_SUPPLIER", "DIM_PRODUCT"]},
    {"name": "FACT_GOODS_RECEIPT", "grain": "Material document item", "keys": ["system", "mat_doc", "item"],
     "measures": {"gr_value": "SUM", "gr_qty": "SUM"}, "dims": ["DIM_COMPANY_CODE", "DIM_PRODUCT", "DIM_FISCAL_CALENDAR"]},
    {"name": "FACT_SUPPLIER_INVOICE", "grain": "Invoice item", "keys": ["system", "inv_doc", "item"],
     "measures": {"inv_value": "SUM", "gross": "SUM"}, "dims": ["DIM_COMPANY_CODE", "DIM_SUPPLIER", "DIM_FISCAL_CALENDAR"]},
    {"name": "FACT_JOURNAL_ENTRY", "grain": "Journal entry line", "keys": ["reported_by", "rbukrs", "gjahr", "belnr", "docln"],
     "measures": {"hsl": "SUM"}, "dims": ["DIM_COMPANY_CODE", "DIM_GL_ACCOUNT", "DIM_COST_PROFIT_CENTER", "DIM_FISCAL_CALENDAR"]},
    {"name": "FACT_SUPPLIER_OPEN_ITEM", "grain": "Supplier open item (invoice document)", "keys": ["system", "inv_doc"],
     "measures": {"open_amount": "SUM"}, "dims": ["DIM_COMPANY_CODE", "DIM_SUPPLIER"]},
    {"name": "FACT_CLEARING_ALLOCATION", "grain": "Payment-to-invoice allocation", "keys": ["system", "pay_doc", "inv_doc"],
     "measures": {"allocated": "SUM"}, "dims": ["DIM_SUPPLIER"]},
]
DIMS = ["DIM_SUPPLIER", "DIM_PRODUCT", "DIM_COMPANY_CODE", "DIM_GL_ACCOUNT", "DIM_COST_PROFIT_CENTER", "DIM_FISCAL_CALENDAR"]
BRIDGES = [{"name": "BRIDGE_DOCUMENT_RELATIONSHIP", "purpose": "PR->PO->GR->Invoice->FI->Payment document chain", "grain": "document pair"},
           {"name": "BRIDGE_SOURCE_TO_CFIN", "purpose": "source accounting document <-> Central Finance document", "grain": "document pair"}]
ANALYTIC_MODELS = [{"name": "AM_P2P", "facts": ["FACT_PROCUREMENT_COMMITMENT", "FACT_GOODS_RECEIPT", "FACT_SUPPLIER_INVOICE",
                                                  "FACT_SUPPLIER_OPEN_ITEM"], "note": "facts are exposed side by side on shared dimensions; never fact-to-fact joined"},
                   {"name": "AM_FINANCE_RECON", "facts": ["FACT_JOURNAL_ENTRY", "FACT_SUPPLIER_OPEN_ITEM", "FACT_CLEARING_ALLOCATION"],
                    "note": "reconciliation model; reported FI source per company code is unique"}]


def build_model(scenario: str, decisions: list[dict]) -> dict:
    l1, skipped = [], []
    for d in decisions:
        kind = ACQ_DECISIONS.get(d["decision"])
        if kind is None:
            skipped.append({"requirement": d["requirement"], "decision": d["decision"], "reason": "no acquisition object until the decision is resolved"})
        elif kind == "INSTALLED_PRODUCT":
            l1.append({"requirement": d["requirement"], "type": kind, "replication_flow": False,
                       "note": "installed SAP-managed product consumed as is; no additional replication flow generated"})
        else:
            l1.append({"requirement": d["requirement"], "type": kind, "replication_flow": kind == "REPLICATION_FLOW"})
    l2 = [{"view": "V_H_PO_ITEM", "adds": ["src_system", "client", "system-qualified doc_key"], "sql": SQL["V_H_PO_ITEM"]},
          {"view": "V_H_SUPPLIER_MAP", "adds": ["global business-partner id via DIM mapping"], "sql": None},
          {"view": "V_H_COMPANY_CODE_MAP", "adds": ["source company code -> CFIN company code"], "sql": None},
          {"view": "V_H_FISCAL_ALIGN", "adds": ["fiscal period -> reporting calendar period"], "sql": None},
          {"view": "V_H_CURRENCY", "adds": ["explicit currency precision (INR/USD/EUR decimals)"], "sql": None},
          {"view": "V_H_DUP_ID", "adds": ["duplicate identification on system-qualified keys (cross-system collisions are not duplicates)"], "sql": None}]
    l3 = [{"view": n, "sql": SQL[n]} for n in ("V_T_PO_HIST_AGG", "V_T_INV_AGG", "V_T_INV_DOC", "V_T_CLEARING_AGG")]
    l4 = {"facts": FACTS, "dimensions": DIMS, "bridges": BRIDGES, "views": [{"view": n, "sql": SQL[n]} for n in ("FACT_COMMITMENT", "FACT_SUPPLIER_OPEN_ITEM")],
          "analytic_models": ANALYTIC_MODELS}
    l5 = [{"exposure": m["name"], "mechanism": "Datasphere analytic model consumption", "optional_consumers": ["SAP Analytics Cloud (optional)", "SAP Databricks (optional)"]}
          for m in ANALYTIC_MODELS]
    return {"scenario": scenario, "layers": {"1_acquisition": l1, "2_harmonization": l2, "3_transformation": l3, "4_semantic": l4, "5_consumption": l5},
            "skipped_acquisition": skipped, "status": "GENERATED", "deployed": False,
            "note": "specification and SQL only; not deployed to any Datasphere tenant"}


def validate_grain(model: dict) -> dict:
    """Facts keep independent grains; associations only go fact -> dimension; every fact declares keys and additive measures."""
    problems = []
    facts = {f["name"]: f for f in model["layers"]["4_semantic"]["facts"]}
    dims = set(model["layers"]["4_semantic"]["dimensions"])
    for f in facts.values():
        if not f["keys"] or not f["grain"]:
            problems.append(f"{f['name']}: grain/keys missing")
        for d in f["dims"]:
            if d in facts:
                problems.append(f"{f['name']}: association to fact {d} (fact-to-fact join multiplies measures)")
            elif d not in dims:
                problems.append(f"{f['name']}: unknown dimension {d}")
    grains = [f["grain"] for f in facts.values()]
    if len(set(grains)) != len(grains):
        problems.append("two facts share the same grain definition; confirm they are not duplicates")
    return {"status": "PASS" if not problems else "FAIL", "problems": problems, "facts": len(facts)}


def _load(conn: sqlite3.Connection, acq: dict) -> None:
    e = acq["entities"]
    conn.execute("CREATE TABLE po_item(system, po, item, bukrs, ccy, qty REAL, price REAL, net REAL)")
    conn.execute("CREATE TABLE po_history(system, po, item, type, qty REAL, value REAL)")
    conn.execute("CREATE TABLE inv_item(system, po, item, bukrs, ccy, supplier, inv_doc, net_po REAL, gross REAL)")
    conn.execute("CREATE TABLE clearing(system, inv_doc, amount REAL)")
    conn.executemany("INSERT INTO po_item VALUES (?,?,?,?,?,?,?,?)", [(r["system"], r["po"], r["item"], r["bukrs"], r["ccy"], float(r["qty"]),
                                                                      float(r["price"]), float(r["net"])) for r in e["po_item"]])
    conn.executemany("INSERT INTO po_history VALUES (?,?,?,?,?,?)", [(r["system"], r["po"], r["item"], r["type"], float(r["qty"]), float(r["value"]))
                                                                     for r in e["po_history"]])
    conn.executemany("INSERT INTO inv_item VALUES (?,?,?,?,?,?,?,?,?)", [(r["system"], r["po"], r["item"], r["bukrs"], r["ccy"], r["supplier"], r["inv_doc"],
                                                                         float(r["net_po"]), float(r["gross"])) for r in e["inv_item"]])
    conn.executemany("INSERT INTO clearing VALUES (?,?,?)", [(r["system"], r["inv_doc"], float(r["amount"])) for r in e["clearing"]])


def sqlite_functional_check(acq: dict, bdc_measures: dict) -> dict:
    """Run the generated SQL on the acquired synthetic data and compare to the BDC measures (2-dp / 3-dp rounding)."""
    conn = sqlite3.connect(":memory:")
    _load(conn, acq)
    for n in ("V_H_PO_ITEM", "V_T_PO_HIST_AGG", "V_T_INV_AGG", "V_T_INV_DOC", "V_T_CLEARING_AGG"):
        conn.execute(f"CREATE VIEW {n} AS {SQL[n]}")
    conn.execute(f"CREATE VIEW FACT_COMMITMENT AS {SQL['FACT_COMMITMENT']}")
    conn.execute(f"CREATE VIEW FACT_SUPPLIER_OPEN_ITEM AS {SQL['FACT_SUPPLIER_OPEN_ITEM']}")
    rows = conn.execute("SELECT system, bukrs, ccy, SUM(po_value), SUM(gr_value), SUM(gr_value) - SUM(inv_value_po_price), SUM(open_commitment) "
                        "FROM FACT_COMMITMENT GROUP BY system, bukrs, ccy").fetchall()
    liab = conn.execute("SELECT system, bukrs, ccy, SUM(open_amount) FROM FACT_SUPPLIER_OPEN_ITEM GROUP BY system, bukrs, ccy").fetchall()
    checks = []

    def cmp(measure, key, got):
        exp = bdc_measures[measure].v.get(key, D(0))
        ok = abs(D(round(got, 5)) - D(exp)) <= TOL  # float vs Decimal: rounding-level tolerance only
        checks.append({"measure": measure, "key": list(key), "sql": round(got, 2), "model": str(exp), "status": "PASS" if ok else "FAIL"})

    for s, b, c, po, gr, grir, oc in rows:
        k = (s, b, c)
        cmp("po_value", k, po)
        cmp("gr_value", k, gr)
        cmp("grir_balance", k, grir)
        cmp("open_commitment", k, oc)
    bs = {}
    for s, b, c, ol in liab:
        bs[(s, b, c)] = ol
    for k, ol in bs.items():
        exp = sum((v for kk, v in bdc_measures["supplier_liability"].v.items() if kk[:2] + (kk[3],) == k), D(0))
        ok = abs(D(round(ol, 5)) - exp) <= TOL
        checks.append({"measure": "supplier_liability", "key": list(k), "sql": round(ol, 2), "model": str(exp), "status": "PASS" if ok else "FAIL"})
    naive = conn.execute(NAIVE_FANOUT_SQL).fetchall()
    naive_total = sum(r[3] for r in naive)
    true_total = float(sum((v for v in bdc_measures["po_value"].v.values()), D(0)))
    fanout = {"naive_join_po_value": round(naive_total, 2), "correct_po_value": round(true_total, 2), "multiplied": naive_total > true_total + 0.01}
    conn.close()
    ok = all(c["status"] == "PASS" for c in checks)
    return {"status": "OFFLINE_VALIDATED" if ok else "FAILED", "mode": "OFFLINE_SQLITE", "checks": checks, "fan_out_demonstration": fanout,
            "note": "SQLite functional check of generated logic; not a Datasphere or HANA validation"}
