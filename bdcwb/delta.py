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
     "question": "Once the solution is established, do two independent calculations agree?",
     "how": ["Technical validation of the generated artifacts and model (offline checks; live-only checks are reported as not run).",
             "Three reconciliation levels: source to acquisition, acquisition to semantic model, authoritative SAP result vs BDC result.",
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
}
CUSTOMIZATION_KIND = {"CUSTOM_FIELD": "Customization", "CUSTOM_OBJECT": "Customization", "SEMANTIC_RULE": "Business rule difference", "NO_DELTA": "None"}
ROUTES = {"REUSE_STANDARD": "Reuse the standard product", "KEY_USER_EXTENSION": "Extend the SAP product (key-user extension)",
          "DATA_PRODUCT_EXTENSION": "Extend the SAP product (data-product extension)",
          "CREATE_CUSTOMER_MANAGED_PRODUCT": "New backend CDS view + customer-managed data model",
          "DATASPHERE_ENRICHMENT": "Solve in Datasphere (stage 3)", "CATALOG_REVIEW_REQUIRED": "Verify the catalog first"}
STRUCTURAL = {"KEY_GAP", "GRANULARITY_GAP", "RELATIONSHIP_GAP", "EXTRACTION_GAP"}


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
        return "NO_STANDARD_PRODUCT", [], notes
    if "CATALOG_UNVERIFIED" in g:
        return "UNKNOWN_CATALOG", [], notes
    if g & STRUCTURAL:
        notes = [f"{x['class'].replace('_', ' ').lower()}: {_fmt(x['detail'])}" for x in a["gaps"] if x["class"] in STRUCTURAL]
        return "STRUCTURAL", cust, notes
    if "FIELD_GAP" in g:
        return ("CUSTOM_FIELD", cust, [f"standard fields also missing: {', '.join(std)}"] if std else []) if cust and not std else ("FIELD_GAP_STANDARD", cust, [f"standard fields missing: {', '.join(std)}"])
    if "SEMANTIC_GAP" in g:
        return "SEMANTIC_RULE", [], [f"{x['dimension']}: {_fmt(x['detail'])}" for x in a["gaps"] if x["class"] == "SEMANTIC_GAP"]
    if "SECURITY_GAP" in g:
        return "SECURITY", [], [f"{x['dimension']}: {_fmt(x['detail'])}" for x in a["gaps"] if x["class"] == "SECURITY_GAP"]
    other = [x for x in a["gaps"] if x["class"] != "NO_GAP"]
    if other:
        return "SEMANTIC_RULE", [], [f"{x['dimension']}: {_fmt(x['detail'])}" for x in other]
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
        how = f"{first['dimension']} check: {_fmt(first['detail'])}" if first else "all assessed dimensions match the delivered entity"
        if cust:
            how = f"field(s) {', '.join(cust)} carry the custom flag in the discovered object metadata and are not in the delivered entity; " + how
        steps = d.get("implementation_steps", [])
        rows.append({
            "requirement": a["requirement"], "label": a["label"], "sap_object": a["object"], "system": a["system"],
            "product": (f"{cand['product']} / {cand['entity']}" if cand else "none"), "catalog_state": a["catalog_state"],
            "delta_type": dtype, "delta": DELTA_TYPES[dtype][0], "kind": CUSTOMIZATION_KIND.get(dtype, "Product coverage gap"),
            "customization": ", ".join(cust) or "-", "notes": notes, "how_found": how,
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
    routes = Counter(r["route"] for r in rows if r["decision"] != "-")
    return {"objects": len([r for r in rows if r["requirement"] != "-"]), "rows": len(rows), "by_type": dict(by),
            "customizations": sum(1 for r in rows if r["kind"] == "Customization"),
            "rule_differences": sum(1 for r in rows if r["kind"] == "Business rule difference"),
            "coverage_gaps": sum(1 for r in rows if r["kind"] == "Product coverage gap"),
            "logic_markers": len(s["logic_discovery"]["category_B"]),
            "no_delta": by.get("NO_DELTA", 0), "routes": dict(routes)}


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
