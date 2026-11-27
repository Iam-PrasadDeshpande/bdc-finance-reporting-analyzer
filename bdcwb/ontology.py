"""Scenario ontology: how data flows and how the components are wired, from the SAP object to the proof.

For every SAP object compared in the delta register this builds one lineage row:
  SAP object -> delta -> solution (what is reused, extended or created) -> acquisition into BDC / Datasphere
             -> harmonization and transformation views -> semantic target (fact / dimension) -> analytic model -> reconciliation level.
The typed relations behind the rows (found_in, compared_with, solved_by, creates, extends, acquired_as, feeds, modelled_in, proven_by)
are returned too, so the wiring can be listed, counted and tested. Everything is derived from the synthetic scenario run.
"""
from __future__ import annotations

from collections import Counter

from . import delta

# Project's own model of where each logical object group lands in the Datasphere model (checked against the generated model below).
GROUP_TARGET = {
    "PR": ("FACT_PROCUREMENT_COMMITMENT", ["V_H_PO_ITEM"], []), "PRACC": ("FACT_PROCUREMENT_COMMITMENT", ["V_H_PO_ITEM"], []),
    "POH": ("FACT_PROCUREMENT_COMMITMENT", ["V_H_PO_ITEM"], []), "POI": ("FACT_PROCUREMENT_COMMITMENT", ["V_H_PO_ITEM"], []),
    "POACC": ("FACT_PROCUREMENT_COMMITMENT", ["V_H_PO_ITEM"], []), "POSCH": ("FACT_PROCUREMENT_COMMITMENT", ["V_H_PO_ITEM"], []),
    "POHIST": ("FACT_PROCUREMENT_COMMITMENT", ["V_H_PO_ITEM"], ["V_T_PO_HIST_AGG"]),
    "MATDOC": ("FACT_GOODS_RECEIPT", ["V_H_PO_ITEM"], ["V_T_PO_HIST_AGG"]),
    "INVH": ("FACT_SUPPLIER_INVOICE", ["V_H_SUPPLIER_MAP"], ["V_T_INV_AGG"]), "INVI": ("FACT_SUPPLIER_INVOICE", ["V_H_SUPPLIER_MAP"], ["V_T_INV_AGG"]),
    "BKPF": ("FACT_JOURNAL_ENTRY", ["V_H_COMPANY_CODE_MAP", "V_H_FISCAL_ALIGN", "V_H_CURRENCY"], []),
    "BSEG": ("FACT_JOURNAL_ENTRY", ["V_H_COMPANY_CODE_MAP", "V_H_FISCAL_ALIGN", "V_H_CURRENCY"], []),
    "ACDOCA": ("FACT_JOURNAL_ENTRY", ["V_H_COMPANY_CODE_MAP", "V_H_FISCAL_ALIGN", "V_H_CURRENCY"], []),
    "SUPOI": ("FACT_SUPPLIER_OPEN_ITEM", ["V_H_SUPPLIER_MAP"], ["V_T_INV_DOC"]),
    "PAYCLR": ("FACT_CLEARING_ALLOCATION", ["V_H_DUP_ID"], ["V_T_CLEARING_AGG"]),
    "BP": ("DIM_SUPPLIER", ["V_H_SUPPLIER_MAP"], []), "MAT": ("DIM_PRODUCT", [], []), "GL": ("DIM_GL_ACCOUNT", [], []),
    "CC": ("DIM_COMPANY_CODE", ["V_H_COMPANY_CODE_MAP"], []), "XMAP": ("BRIDGE_DOCUMENT_RELATIONSHIP", ["V_H_SUPPLIER_MAP", "V_H_COMPANY_CODE_MAP"], []),
}
ACQ_TEXT = {"INSTALLED_PRODUCT": "installed SAP product, consumed as is", "REPLICATION_FLOW": "replication flow for a customer-managed product",
            "ENRICHMENT_SOURCE": "enrichment source combined in Datasphere"}
RELATIONS = {"found_in": ("Delta", "SAP object"), "compared_with": ("SAP object", "SAP-delivered data product"), "solved_by": ("Delta", "Solution"),
             "extends": ("Solution", "SAP-delivered data product"), "creates": ("Solution", "New artifact (CDS view, contract, target)"),
             "acquired_as": ("Solution", "Acquisition (BDC / Datasphere)"), "feeds": ("Acquisition", "Harmonization / transformation view"),
             "modelled_in": ("View", "Fact or dimension"), "exposed_in": ("Fact or dimension", "Analytic model"), "proven_by": ("Analytic model", "Reconciliation level")}


def _artifacts(row: dict, pkg: dict | None) -> list[str]:
    d = row["decision"]
    if d == "CREATE_CUSTOMER_MANAGED_PRODUCT" and pkg:
        names = list(pkg["manifest"]["files"])
        return [f"{n} (generated template, not activated)" for n in names]
    if d in ("KEY_USER_EXTENSION", "DEVELOPER_EXTENSION", "DATA_PRODUCT_EXTENSION"):
        return [f"custom field {row['customization'].split(' (')[0]} created or exposed through the supported extension (draft; propagation not verified)"] if row["customization"] != "-" else ["extension (draft)"]
    if d == "BW_DATA_PRODUCT_ROUTE":
        return ["BW Data Product Generator design (draft; eligibility to be verified)"]
    if d in ("MANUAL_BUSINESS_RULE", "EXECUTION_BLOCKED"):
        return ["nothing created: a rule approval or a missing release, authority or entitlement comes first"]
    if d == "DATASPHERE_ENRICHMENT":
        return ["Datasphere harmonization view and the approved business rule (synthetic scope)"]
    if d == "REUSE_STANDARD":
        return ["nothing created: the installed SAP product is reused"]
    if d == "CATALOG_REVIEW_REQUIRED":
        return ["nothing created yet: verify the catalog first"]
    return ["-"]


def build(res: dict, scn: str) -> dict:
    s = res["scenarios"][scn]
    rows = [r for r in delta.register(s) if r["requirement"] != "-"]
    objs = {a["requirement"]: a for a in s["analysis"]}
    pk = {p["manifest"]["requirement"]: p for p in s["packages"]}
    lay = s["model"]["layers"]
    acq = {a["requirement"]: a for a in lay["1_acquisition"]}
    views = {v["view"] for v in lay["2_harmonization"]} | {v["view"] for v in lay["3_transformation"]}
    sem = lay["4_semantic"]
    facts = {f["name"] for f in sem["facts"]}
    dims = set(sem["dimensions"]) if all(isinstance(x, str) for x in sem["dimensions"]) else {d.get("name") for d in sem["dimensions"]}
    bridges = {b["name"] for b in sem["bridges"]}
    models = sem["analytic_models"]
    lv = {k: (v or {}).get("status", "-") for k, v in s["recon"]["levels"].items()}
    lineage, edges = [], []
    for r in rows:
        a = objs[r["requirement"]]
        grp = a["group"]
        fact, harm, trans = GROUP_TARGET.get(grp, ("-", [], []))
        harm = [v for v in harm if v in views]
        trans = [v for v in trans if v in views]
        target_ok = fact in facts or fact in dims or fact in bridges
        mods = [m["name"] for m in models if fact in m["facts"]]
        ac = acq.get(r["requirement"], {})
        art = _artifacts(r, pk.get(r["requirement"]))
        proofs = ([k for k in ("L1", "L2", "L3") if lv.get(k, "-") != "-"] + [k for k in ("B1", "B4") if lv.get(k, "-") != "-"]) if ac else []
        lineage.append({
            "requirement": r["requirement"], "label": r["label"], "system": r["system"], "sap_object": r["sap_object"],
            "delta_type": r["delta_type"], "delta": r["delta"], "customization": r["customization"], "route": r["route"], "decision": r["decision"],
            "creates": art, "product": r["product"],
            "acquisition": ACQ_TEXT.get(ac.get("type", ""), "-"), "acq_type": ac.get("type", "-"),
            "harmonize": harm, "transform": trans, "target": fact if target_ok else "-", "models": mods, "proof": proofs,
        })
        rid = r["requirement"]
        edges.append({"from": r["sap_object"], "rel": "found_in", "to": r["delta_type"], "ref": rid})
        edges.append({"from": r["sap_object"], "rel": "compared_with", "to": r["product"], "ref": rid})
        edges.append({"from": r["delta_type"], "rel": "solved_by", "to": r["decision"], "ref": rid})
        if r["decision"] in ("KEY_USER_EXTENSION", "DATA_PRODUCT_EXTENSION"):
            edges.append({"from": r["decision"], "rel": "extends", "to": r["product"], "ref": rid})
        if r["decision"] == "CREATE_CUSTOMER_MANAGED_PRODUCT":
            for n in art:
                edges.append({"from": r["decision"], "rel": "creates", "to": n.split(" (")[0], "ref": rid})
        if ac:
            edges.append({"from": r["decision"], "rel": "acquired_as", "to": ac["type"], "ref": rid})
            for v in harm + trans:
                edges.append({"from": ac["type"], "rel": "feeds", "to": v, "ref": rid})
        for v in harm + trans:
            if target_ok:
                edges.append({"from": v, "rel": "modelled_in", "to": fact, "ref": rid})
        for m in mods:
            edges.append({"from": fact, "rel": "exposed_in", "to": m, "ref": rid})
            for k in proofs:
                edges.append({"from": m, "rel": "proven_by", "to": k, "ref": rid})
    by_rel = Counter(e["rel"] for e in edges)
    nodes = {x for e in edges for x in (e["from"], e["to"])}
    return {"scenario": scn, "lineage": lineage, "edges": edges, "nodes": len(nodes), "by_relation": dict(by_rel), "recon": lv,
            "counts": {"objects": len(lineage), "created": sum(1 for x in lineage if x["decision"] == "CREATE_CUSTOMER_MANAGED_PRODUCT"),
                       "extended": sum(1 for x in lineage if x["decision"] in ("KEY_USER_EXTENSION", "DEVELOPER_EXTENSION", "DATA_PRODUCT_EXTENSION")),
                       "reused": sum(1 for x in lineage if x["decision"] == "REUSE_STANDARD"),
                       "datasphere": sum(1 for x in lineage if x["decision"] == "DATASPHERE_ENRICHMENT"),
                       "unresolved": sum(1 for x in lineage if x["decision"] not in ("CREATE_CUSTOMER_MANAGED_PRODUCT", "KEY_USER_EXTENSION", "DEVELOPER_EXTENSION",
                                                                                      "DATA_PRODUCT_EXTENSION", "REUSE_STANDARD", "DATASPHERE_ENRICHMENT")),
                       "views": len(views), "facts": len(facts), "models": len(models)}}


def relations_table() -> list[dict]:
    return [{"relation": k, "from": v[0], "to": v[1]} for k, v in RELATIONS.items()]
