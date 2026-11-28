"""The delta journey: what the customer changed in standard SAP, how it was found, how it is solved, and how the result is proven.

Five stages, three agents:
  1 Find the delta          S/4HANA agent   (customizations in standard SAP vs the SAP-delivered data products)
  2 Solution the delta      S/4HANA agent   (extend the SAP product, or a new backend CDS view + customer-managed data model)
  3 Datasphere activities   BDC & Datasphere agent (replication flows, transformation, semantic model, offline simulation)
  4 Compare and reconcile   Utility agent   (technical validation, three-level Finance reconciliation, injected-defect proof)
  5 End-to-end result       Utility agent   (scorecard, execution plan, gates, what is still HOLD)

Everything is derived from the synthetic scenario run; nothing here is a live finding.
"""
from __future__ import annotations

from collections import Counter

from .decision import STRUCTURAL  # one definition shared with the decision engine

STAGES = [
    {"id": 1, "name": "Find the delta", "agent": "s4", "support": "bdc",
     "question": "What did the customer change in standard SAP, and does the SAP-delivered data product already cover it?",
     "how": ["Discover the standard objects behind the report and their dependencies (read-only metadata).",
             "Flag customizations: fields marked custom, customer (Z) objects and custom logic markers.",
             "Map each standard object to the SAP-delivered data-product entity in the catalog, keeping the evidence class.",
             "Compare field by field and across 16 dimensions (keys, grain, relationships, extraction, rules, authorization) to get a gap class."],
     "output": "Delta register: one row per SAP object with the customization, how it was found and the next step."},
    {"id": 2, "name": "Solution the delta", "agent": "s4", "support": "bdc",
     "question": "For each delta: extend the SAP-delivered product, or build a new backend CDS view and a customer-managed data model?",
     "how": ["A deterministic decision engine picks the route; the number of missing fields never decides by itself.",
             "Extend the SAP product when the missing fields are eligible custom attributes and the product supports key-user or data-product extension.",
             "Build a new backend CDS view and a customer-managed data model when the structure differs or no product exists (generated as inspectable templates, never activated).",
             "Solve in Datasphere when a business rule or enrichment is enough (stage 3)."],
     "output": "A solution route per delta, its implementation steps, approvals and generated package templates."},
    {"id": 3, "name": "Datasphere activities", "agent": "bdc", "support": "s4",
     "question": "Which replication flows, transformations and semantic models are needed so the solved deltas reach the report?",
     "how": ["Acquire: installed products, replication flows for customer-managed products, enrichment sources.",
             "Harmonize and transform: system-qualified keys, currency and fiscal alignment, PO-history pre-aggregation (prevents fan-out).",
             "Model: facts, dimensions, bridges and analytic models at an explicit grain.",
             "Simulate offline: grain validator and SQL functional check (nothing is deployed to Datasphere)."],
     "output": "Datasphere plan: flows, views, semantic model and the offline simulation result."},
    {"id": 4, "name": "Compare and reconcile", "agent": "utility", "support": "bdc",
     "question": "Once the solution is established, do the technical comparison and the data-level comparison agree?",
     "how": ["Technical comparison (metadata level): validate the generated artifacts and model offline; live-only checks are reported as not run.",
             "Data-level comparison in three reconciliation levels: source to acquisition, acquisition to semantic model, authoritative SAP result vs BDC result.",
             "Central Finance guard: source FI and replicated FI are never summed.",
             "Injected-defect proof: every seeded difference must be detected."],
     "output": "Verdicts per level, the golden transaction check and the detection matrix (synthetic)."},
    {"id": 5, "name": "End-to-end result", "agent": "utility", "support": "s4",
     "question": "What is the answer for the SAP team, and what is still open?",
     "how": ["Roll up: deltas found, solutions chosen, Datasphere objects, reconciliation verdicts.",
             "Show the execution plan per mode; writes stay blocked and need separate human authorization.",
             "Evaluate the acceptance gates and keep synthetic and live status separate."],
     "output": "End-to-end scorecard, next steps and the live validation that is still HOLD."},
]
AGENT3 = [
    {"id": "s4", "name": "S/4HANA agent", "icon": "◆", "stages": [1, 2],
     "blurb": "Everything specific to the customer's S/4HANA: objects, dependencies, customizations, the delta register and the solution (extend, or new backend CDS view).",
     "authority": "LOCAL_DRAFT"},
    {"id": "bdc", "name": "BDC & Datasphere agent", "icon": "▦", "stages": [3],
     "blurb": "What SAP delivers and what is built on it: the data-product catalog, comparison with SAP objects, replication flows, transformation and semantic modelling.",
     "authority": "LOCAL_DRAFT"},
    {"id": "utility", "name": "Utility agent", "icon": "⬡", "stages": [4, 5],
     "blurb": "Shared utilities: business rules and approvals, validation, reconciliation, execution plan, gates, the end-to-end result and the refusal of write actions.",
     "authority": "DRAFT_ONLY"},
]

DELTA_TYPES = {
    "NO_DELTA": ("No delta", "The SAP-delivered product covers the object."),
    "CUSTOM_FIELD": ("Customer field on a standard object", "A field the customer added (custom flag) is missing from the delivered product."),
    "CUSTOM_OBJECT": ("Customer-created object", "A Z object in the report's dependency chain; no standard product can contain it."),
    "FIELD_GAP_STANDARD": ("Standard fields not exposed", "Standard SAP fields exist on the object but not in the delivered product entity."),
    "STRUCTURAL": ("Structure differs", "Key, grain, relationships or extraction differ from the delivered product."),
    "SEMANTIC_RULE": ("Meaning differs", "Same data, different business meaning (for example the amount basis); needs an approved rule."),
    "SECURITY": ("Authorization not enforced", "The product does not enforce the authorization objects the report needs."),
    "NO_STANDARD_PRODUCT": ("No SAP-delivered product", "The catalog is complete for the domain and has no product for this object."),
    "UNKNOWN_CATALOG": ("Catalog evidence incomplete", "Cannot conclude: the product may exist but is not established."),
    "FIDELITY_LOSS": ("Extension degraded in the product", "The delivered product carries the field, but with a different data type, no business name, or no currency or unit reference."),
    "OTHER_GAP": ("Other product gap", "A gap class without its own delta type (for example availability); see the gap classes of the row."),
}
DETECTION_SCOPE = {
    "detected": ["Fields flagged custom in the discovered object metadata (customer append and extension fields).",
                 "Customer-namespace CDS views in the report's dependency chain.",
                 "Custom-logic markers found by a lexical scan of source text (AMDP, ABAP routines, BAdI, calls to customer classes)."],
    "not_detected": ["Implicit enhancements, enhancement spots and BAdI implementations that leave no marker in the scanned source.",
                     "Append structures and modifications on objects that were not read.",
                     "IMG configuration (document types, valuation, account determination) that changes meaning without changing structure.",
                     "Runtime behaviour: the scan is lexical, not a parser."]}
CUSTOMIZATION_KIND = {"CUSTOM_FIELD": "Customization", "CUSTOM_OBJECT": "Customization", "SEMANTIC_RULE": "Business rule difference", "NO_DELTA": "None"}
ROUTES = {"REUSE_STANDARD": "Reuse the standard product", "KEY_USER_EXTENSION": "Extend the SAP product (key-user extension)",
          "DATA_PRODUCT_EXTENSION": "Extend the SAP product (data-product extension)",
          "DEVELOPER_EXTENSION": "Extend the SAP product (developer extension)",
          "CREATE_CUSTOMER_MANAGED_PRODUCT": "New backend CDS view + customer-managed data model",
          "BW_DATA_PRODUCT_ROUTE": "BW Data Product Generator route",
          "DATASPHERE_ENRICHMENT": "Solve in Datasphere (stage 3)", "CATALOG_REVIEW_REQUIRED": "Verify the catalog first",
          "MANUAL_BUSINESS_RULE": "Record and approve a business rule first", "EXECUTION_BLOCKED": "Blocked: needs a release, authority or entitlement"}


def _fmt(detail) -> str:
    """Plain-text rendering of a gap detail (dict / list / str)."""
    if isinstance(detail, dict):
        parts = []
        for k, v in detail.items():
            if isinstance(v, dict):
                v = ", ".join(f"{a} {b}" for a, b in v.items())
            elif isinstance(v, (list, tuple)):
                v = ", ".join(str(x) for x in v) or "none"
            parts.append(f"{k.replace('_', ' ')}: {v}")
        return "; ".join(parts)
    if isinstance(detail, (list, tuple)):
        return ", ".join(str(x) for x in detail)
    return str(detail)


def _classify(a: dict, custom_names: set[str]) -> tuple[str, list[str], list[str]]:
    g = {x["class"] for x in a["gaps"]}
    miss = a.get("missing_fields") or []
    cust = [f for f in miss if f in custom_names]
    std = [f for f in miss if f not in custom_names]
    notes: list[str] = []
    if "PRODUCT_NOT_AVAILABLE" in g:
        return "NO_STANDARD_PRODUCT", cust, notes
    if "CATALOG_UNVERIFIED" in g:
        return "UNKNOWN_CATALOG", cust, notes
    if g & STRUCTURAL:
        notes = [f"{x['class'].replace('_', ' ').lower()}: {_fmt(x['detail'])}" for x in a["gaps"] if x["class"] in STRUCTURAL]
        return "STRUCTURAL", cust, notes
    if "FIELD_GAP" in g:
        if cust and not std:
            return "CUSTOM_FIELD", cust, []
        return "FIELD_GAP_STANDARD", cust, [f"standard fields missing: {', '.join(std)}"]
    if g & {"SEMANTIC_GAP", "BUSINESS_LOGIC_GAP"}:
        return "SEMANTIC_RULE", [], [f"{x['dimension']}: {_fmt(x['detail'])}" for x in a["gaps"] if x["class"] in ("SEMANTIC_GAP", "BUSINESS_LOGIC_GAP")]
    if "SECURITY_GAP" in g:
        return "SECURITY", [], [f"{x['dimension']}: {_fmt(x['detail'])}" for x in a["gaps"] if x["class"] == "SECURITY_GAP"]
    other = [x for x in a["gaps"] if x["class"] != "NO_GAP"]
    if other:
        return "OTHER_GAP", [], [f"{x['class'].replace('_', ' ').lower()}: {_fmt(x['detail'])}" for x in other]
    return "NO_DELTA", [], notes


def register(s: dict) -> list[dict]:
    """The delta register: one row per standard SAP object compared with its delivered data product, plus customer-created objects."""
    objs = {o["id"]: o for o in s["objects"]}
    dec = {d["requirement"]: d for d in s["decisions"]}
    rows = []
    for a in s["analysis"]:
        o = objs.get(a["object"], {})
        custom_names = set(o.get("custom_fields") or [])
        dtype, cust, notes = _classify(a, custom_names)
        d = dec.get(a["requirement"], {})
        cand = a["candidates"][0] if a["candidates"] else None
        first = next((x for x in a["gaps"] if x["class"] != "NO_GAP"), None)
        miss = set(a.get("missing_fields") or [])
        present = sorted(custom_names)  # customization is recorded whatever the delta type is
        cust_txt = ", ".join(f"{n} ({'not in the delivered product' if n in miss else 'covered by the product'})" for n in present) or "-"
        how = f"{first['dimension']} check: {_fmt(first['detail'])}" if first else "all assessed dimensions match the delivered entity"
        if present:
            how = f"field(s) {', '.join(present)} carry the custom flag in the discovered object metadata; " + how
        kind = "Customization" if present else ("None" if dtype == "NO_DELTA" else "Business rule difference" if dtype == "SEMANTIC_RULE" else "Product coverage gap")
        steps = d.get("implementation_steps", [])
        rows.append({
            "requirement": a["requirement"], "label": a["label"], "sap_object": a["object"], "system": a["system"],
            "product": (f"{cand['product']} / {cand['entity']}" if cand else "none"), "catalog_state": a["catalog_state"],
            "delta_type": dtype, "delta": DELTA_TYPES[dtype][0], "kind": kind,
            "customization": cust_txt, "notes": notes, "how_found": how,
            "gap_classes": [x["class"] for x in a["gaps"]], "coverage": f"{a['coverage']['numerator']}/{a['coverage']['denominator']}",
            "decision": d.get("decision", "-"), "route": ROUTES.get(d.get("decision", ""), d.get("decision", "-")),
            "next_step": steps[0] if steps else (d.get("reason") or "-"), "steps": steps, "approvals": d.get("approvals", []), "reason": d.get("reason", ""),
        })
    for o in s["objects"]:
        if o["obj_type"] == "CDS_CUSTOM_VIEW":
            rows.append({"requirement": "-", "label": o["name"], "sap_object": o["id"], "system": o["system"], "product": "none (customer object)", "catalog_state": "NOT_APPLICABLE",
                         "delta_type": "CUSTOM_OBJECT", "delta": DELTA_TYPES["CUSTOM_OBJECT"][0], "kind": "Customization", "customization": o["name"], "notes": [],
                         "how_found": "object type CDS_CUSTOM_VIEW (customer namespace) found in the dependency chain of the report", "gap_classes": [], "coverage": "-",
                         "decision": "-", "route": "Replace with a standard view, or carry it into the customer-managed model", "next_step": "Confirm with the report owner whether the object is still needed",
                         "steps": [], "approvals": ["Report owner"], "reason": ""})
    return rows


def customizations(s: dict) -> dict:
    """Customizations found in standard SAP: custom fields, customer objects and custom logic markers."""
    fields = [{"object": o["id"], "field": f["name"], "type": f["type"], "length": f["length"]} for o in s["objects"] for f in o["fields"] if f["custom"]]
    custom_objs = [{"object": o["id"], "type": o["obj_type"], "release": o["release"]} for o in s["objects"] if o["obj_type"] == "CDS_CUSTOM_VIEW"]
    ld = s["logic_discovery"]
    markers = Counter(x.get("evidence") or x.get("kind") for x in ld["category_B"])
    return {"fields": fields, "objects": custom_objs, "logic_A": ld["category_A"], "logic_B": ld["category_B"], "logic_B_kinds": dict(markers), "logic_C": ld["category_C"], "note": ld["note"]}


def summary(s: dict) -> dict:
    rows = register(s)
    by = Counter(r["delta_type"] for r in rows)
    kinds = Counter(r["kind"] for r in rows)
    routes = Counter(r["route"] for r in rows if r["decision"] != "-")
    return {"objects": len([r for r in rows if r["requirement"] != "-"]), "rows": len(rows), "by_type": dict(by),
            "customizations": kinds.get("Customization", 0), "rule_differences": kinds.get("Business rule difference", 0), "coverage_gaps": kinds.get("Product coverage gap", 0),
            "logic_markers": len(s["logic_discovery"]["category_B"]),
            "no_delta": kinds.get("None", 0), "routes": dict(routes)}


def dsp_plan(s: dict) -> dict:
    lay = s["model"]["layers"]
    acq = lay["1_acquisition"]
    flows = [a for a in acq if str(a.get("replication_flow")) == "True" or a.get("type") == "REPLICATION_FLOW"]
    sem = lay["4_semantic"]
    return {"acquisition": acq, "replication_flows": flows, "acq_types": dict(Counter(a["type"] for a in acq)),
            "harmonization": lay["2_harmonization"], "transformation": lay["3_transformation"], "semantic": sem, "consumption": lay["5_consumption"],
            "simulation": {"grain": s["grain"]["status"], "sql": s["sqlite"]["status"], "mode": s["sqlite"]["mode"], "fan_out": s["sqlite"]["fan_out_demonstration"]}}


def journey(res: dict, scn: str) -> dict:
    s = res["scenarios"][scn]
    sm = summary(s)
    p = dsp_plan(s)
    lv = s["recon"]["levels"]
    det = s["recon"]["defect_matrix"]
    gates = res["gates"]
    return {
        "scenario": scn, "delta": sm, "plan": p,
        "recon": {k: (v or {}).get("status", "-") for k, v in lv.items()},
        "golden": s["recon"]["golden"]["status"], "golden_rows": f"{sum(1 for r in s['recon']['golden']['rows'] if r['status'] == 'PASS')}/{len(s['recon']['golden']['rows'])}",
        "defects": f"{sum(1 for d in det if d['detected'])}/{len(det)}", "overall": s["recon"]["overall"],
        "packages": len(s["packages"]), "gates": f"{sum(1 for g in gates if g['status'] == 'PASS')}/{len(gates)}", "release": res["overall_release"],
        "status": res["status"],
        "next_steps": ["Authorize read-only metadata access to the customer's S/4HANA system and re-run Stage 1 on the real objects.",
                       "Capture the full SAP data-product catalog from the tenant so 'catalog incomplete' rows can be concluded.",
                       "Finance owner approves the business rules and tolerance policy used in Stage 3 and 4.",
                       "Run Stage 4 on aggregated extracts from S/4HANA and BDC for the same scope and key date."],
    }


def by_product(s: dict) -> dict:
    """The delta seen from the data product: each SAP-delivered product with the customer objects mapped to it and what differs."""
    rows = register(s)
    prods = {p["product_id"]: {"product_id": p["product_id"], "name": p["name"], "version": p["version"], "evidence": p["evidence"], "entities": list(p["entities"]),
                               "extension": p.get("extension") or {}, "objects": []} for p in s["catalog"]["products"]}
    unmapped = []
    for r in rows:
        pid = r["product"].split(" / ")[0]
        (prods[pid]["objects"] if pid in prods else unmapped).append(r)
    for p in prods.values():
        objs = p["objects"]
        kinds = Counter(o["kind"] for o in objs)
        p["counts"] = {"objects": len(objs), "no_delta": kinds.get("None", 0), "customizations": kinds.get("Customization", 0),
                       "rule_differences": kinds.get("Business rule difference", 0), "coverage_gaps": kinds.get("Product coverage gap", 0)}
        p["routes"] = dict(Counter(o["route"] for o in objs if o["decision"] != "-"))
        used = sorted({o["product"].split(" / ")[1] for o in objs if " / " in o["product"]})
        p["entities_used"] = used
        p["entities_unused"] = [e for e in p["entities"] if e not in used]
        p["status"] = "NOT_USED" if not objs else "COVERS_AS_IS" if all(o["delta_type"] == "NO_DELTA" for o in objs) else "COVERS_WITH_DELTA"
    return {"products": prods, "unmapped": unmapped}
