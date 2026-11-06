"""Public-site pages: architecture, decision points and the AR Aging method demonstration.

Public-safe by construction: generic architecture, public SAP documentation names only (cited), and the project-authored
demonstration engine (ar_aging_demo). No SAP-delivered content logic, object names or trial details.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Any

import pandas as pd
import streamlit as st

import ar_aging_demo as demo

SAP_HELP_AR_AGING = ("https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/f296651f454c4284ade361292c633d69/"
                     "bd558b1c30144565986f8c683a8516aa.html")
SAP_HUB_DATA_PRODUCTS = "https://api.sap.com/dataproducts"
SYN = "SYNTHETIC"


def _money(x: float) -> str:
    return f"{x:,.2f}"


def render_architecture() -> None:
    st.markdown("**Two places a Finance definition can live.** Left: the existing S/4HANA reporting stack. Right: the SAP Business "
                "Data Cloud alternative. Between them: the analyzer, which compares the two before any recommendation.")
    st.graphviz_chart("""digraph G { rankdir=TB; newrank=true; nodesep=0.35; ranksep=0.4;
 node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, color="#9fb3bf"];
 subgraph cluster_s4 { label="SAP S/4HANA PCE (existing reporting)"; fontname="Helvetica-Bold"; color="#5686a3";
  rep [label="Finance AR aging report\\n(customer's actual report: to be identified)", fillcolor="#f8e3e3"];
  qry [label="Analytical query\\n(e.g. C_ARAgingGridGenLedgerQry, SAP documentation)", fillcolor="#fdf1d6"];
  cube [label="Analytical cube\\n(e.g. I_ARAgingGridGenLedgerCube, SAP documentation)", fillcolor="#fdf1d6"];
  tabs [label="Journal entry data, configuration,\\ncustomer extensions (to be verified)", fillcolor="#f8e3e3"];
  rep -> qry -> cube -> tabs; }
 subgraph cluster_az { label="Transition analyzer"; fontname="Helvetica-Bold"; color="#14796f";
  a1 [label="Discover and understand\\nthe source definition", fillcolor="#e4f4ef"];
  a2 [label="Map semantics and\\nvalidate edge cases", fillcolor="#e4f4ef"];
  a3 [label="Reconcile results and\\nrecommend a route", fillcolor="#e4f4ef"];
  a1 -> a2 -> a3; }
 subgraph cluster_bdc { label="SAP Business Data Cloud (candidate target)"; fontname="Helvetica-Bold"; color="#17776c";
  dp [label="SAP-managed data products\\n(e.g. journal entry line items, G/L account, customer)", fillcolor="#e4f4ef"];
  ds [label="SAP Datasphere\\nSAP-delivered content or customer models", fillcolor="#e4f4ef"];
  am [label="Analytic model with key date\\nand aging intervals", fillcolor="#e4f4ef"];
  dp -> ds -> am; }
 rep -> a1 [style=dashed, color="#5686a3", constraint=false];
 a3 -> am [style=dashed, color="#17776c", constraint=false];
}""")
    st.caption("Legend: red = must be identified in the customer system; amber = named in public SAP documentation; green = candidate "
               "capability to be evaluated. Product availability depends on the customer's SAP licences and tenant.")
    c1, c2 = st.columns(2)
    c1.markdown("**Existing S/4HANA reporting**\n- The report's real definition sits in queries, CDS views, configuration and "
                "customer extensions\n- Reference: SAP S/4HANA 2023 documentation of the AR aging query and cube "
                f"([SAP Help]({SAP_HELP_AR_AGING}))\n- Customer report, mapping and runtime figures: not available")
    c2.markdown("**SAP Business Data Cloud alternative**\n- SAP-managed data products listed publicly in the "
                f"[SAP Business Accelerator Hub]({SAP_HUB_DATA_PRODUCTS})\n- Modeling and SAP-delivered content in SAP Datasphere\n"
                "- Availability, entitlement and release compatibility: to be confirmed per customer")


DECISION_POINTS = [
    {"decision point": "Key date", "why it matters": "Items open at a past date must include items cleared after it",
     "S/4HANA evidence needed": "Report parameters and query definition", "BDC evidence needed": "Whether cleared items are retained"},
    {"decision point": "Ledger", "why it matters": "Different ledgers can carry different valuations",
     "S/4HANA evidence needed": "Ledger used by the report", "BDC evidence needed": "Ledger scope of the data product / model"},
    {"decision point": "Aging basis and due date", "why it matters": "Decides overdue vs not due and the days counted",
     "S/4HANA evidence needed": "Due-date derivation and payment terms", "BDC evidence needed": "Due date delivered or derived"},
    {"decision point": "Partial payments and credits", "why it matters": "Changes which amounts are open and how they age",
     "S/4HANA evidence needed": "Clearing practice and report rules", "BDC evidence needed": "Representation of references and clearing"},
    {"decision point": "Special G/L items", "why it matters": "Down payments and similar items can change totals materially",
     "S/4HANA evidence needed": "Include/exclude rules per indicator", "BDC evidence needed": "Availability of the indicator"},
    {"decision point": "Currency", "why it matters": "Totals differ by currency role and translation",
     "S/4HANA evidence needed": "Currency type shown in the report", "BDC evidence needed": "Currency roles delivered"},
    {"decision point": "Aging buckets", "why it matters": "Bucket totals depend on configured intervals",
     "S/4HANA evidence needed": "Configured intervals", "BDC evidence needed": "Bucket configuration in the model"},
]


def render_decision_points() -> None:
    st.markdown("**Decision points the Finance owner and architects must settle** before any route can be recommended. "
                "Each one needs evidence from both sides.")
    st.table(DECISION_POINTS)


def _buckets_from_text(text: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        limits = tuple(sorted({int(x) for x in text.split(",") if x.strip()}))
        if not limits or limits[0] < 1 or len(limits) > 8:
            raise ValueError
        return demo.default_buckets(limits), None
    except ValueError:
        return demo.default_buckets(), "Bucket limits must be 1 to 8 positive whole numbers, e.g. 30,60,90. Showing 30,60,90."


def render_demo() -> None:
    st.info("This is a **method demonstration** on SYNTHETIC data with project-authored rules. It shows how the analyzer compares a "
            "source report definition with a candidate target definition and reconciles the results. It does not reproduce "
            "SAP-delivered content and says nothing about any customer's compatibility.")
    r1, r2, r3 = st.columns(3)
    kd = r1.date_input("Key date", _dt.date(2026, 9, 30), min_value=_dt.date(2026, 1, 1), max_value=_dt.date(2027, 3, 31),
                       key="demo_kd").isoformat()
    cc = r2.selectbox("Company code (synthetic)", list(demo.COMPANY_CODES), key="demo_cc",
                      format_func=lambda c: f"{c} ({demo.COMPANY_CODES[c]})")
    buckets, warn = _buckets_from_text(r3.text_input("Aging bucket limits in days", "30,60,90", key="demo_bounds"))
    if warn:
        st.warning(warn)
    st.markdown("**Candidate target definition** (change a rule to see how a definition difference is detected)")
    t1, t2, t3 = st.columns(3)
    rules = {}
    for col, key in zip((t1, t2, t3), demo.RULE_LABELS):
        label, values = demo.RULE_LABELS[key]
        opts = list(values)
        rules[key] = col.selectbox(label, opts, index=opts.index(demo.REFERENCE_RULES[key]), key=f"demo_rule_{key}",
                                   format_func=lambda v, vals=values: vals[v])
    res = demo.run(kd, cc, buckets, rules)
    rec, src, tgt = res["reconciliation"], res["source"], res["target"]
    status = rec["status"]
    (st.success if status == "SYNTHETIC_PASS" else st.error)(
        f"Reconciliation: **{status}** ({SYN}). " + ("Definitions match; synthetic results agree." if status == "SYNTHETIC_PASS"
                                                     else rec.get("reason") or "Results differ."))
    a, b = st.columns(2)
    a.markdown("**Source: S/4HANA report definition** (reference rules, illustrative)")
    a.metric(f"Open AR ({SYN}, {res['currency']})", _money(src["measures"]["open_ar"]))
    a.metric(f"Overdue AR ({SYN}, {res['currency']})", _money(src["measures"]["overdue_ar"]))
    b.markdown("**Target: candidate BDC definition** (rules as selected above)")
    b.metric(f"Open AR ({SYN}, {res['currency']})", _money(tgt["measures"]["open_ar"]),
             delta=None if status == "SYNTHETIC_PASS" else _money(tgt["measures"]["open_ar"] - src["measures"]["open_ar"]))
    b.metric(f"Overdue AR ({SYN}, {res['currency']})", _money(tgt["measures"]["overdue_ar"]),
             delta=None if status == "SYNTHETIC_PASS" else _money(tgt["measures"]["overdue_ar"] - src["measures"]["overdue_ar"]))
    names = [x["name"] for x in buckets]
    labels = [f"{i}. {n}" for i, n in enumerate(names, 1)]
    st.markdown(f"**Aging buckets ({SYN}, overdue days)**")
    st.bar_chart(pd.DataFrame({"Source (S/4HANA definition)": [src["buckets"][n] for n in names],
                               "Target (candidate definition)": [tgt["buckets"][n] for n in names]}, index=labels), stack=False)
    st.table([{"bucket": n, f"source ({SYN})": _money(src["buckets"][n]), f"target ({SYN})": _money(tgt["buckets"][n]),
               "result": next((x["result"] for x in rec.get("buckets", []) if x.get("bucket") == n), "not compared")} for n in names])
    st.markdown(f"**Finance sensitivities** ({SYN}): effect of changing one rule against the reference definition")
    st.table([{"decision": s["decision"], "reference": s["reference"], "alternative": s["alternative"],
               "open AR delta": f"{s['open_ar_delta']:+,.2f}", "overdue AR delta": f"{s['overdue_ar_delta']:+,.2f}",
               "comparison": s["reconciliation"]} for s in res["sensitivities"]])
    st.caption("A different definition is reported as BLOCKED (not comparable) rather than as a mismatch: the analyzer only "
               "reconciles results produced under the same business context. Both synthetic extracts derive from one generated "
               "ledger, so their independence is simulated.")
    st.download_button("Export demonstration result (JSON)", json.dumps(res, indent=2, default=str),
                       f"ar_aging_method_demo_SYNTHETIC_{kd}_{cc}.json", mime="application/json")
