"""Deterministic extensibility and remediation decision engine.

Equivalent verified inputs always give identical output. The NUMBER of missing fields never changes eligibility:
a single ineligible field blocks key-user extension, ten eligible fields do not.
"""
from __future__ import annotations

from .core import DECISIONS
from .rules import RuleBook
from .scenarios import SYSTEMS

KEY_USER_TYPES = {"CHAR", "NUMC", "DATS", "DEC"}  # simple attribute types; amounts/quantities need reference fields
DEFAULT_PREFS = {"prefer_key_user_for_simple_fields": True}
STRUCTURAL = {"KEY_GAP", "GRANULARITY_GAP", "RELATIONSHIP_GAP", "VERSION_GAP", "EXTRACTION_GAP"}

ALTERNATIVE = {
    "REUSE_STANDARD": "Retain the existing backend report for the affected scope until reconciliation passes.",
    "KEY_USER_EXTENSION": "Developer extension or Datasphere enrichment if the key-user custom field is not eligible in the business context.",
    "DEVELOPER_EXTENSION": "Customer-managed data product if the released extension point is not available.",
    "DATA_PRODUCT_EXTENSION": "Datasphere enrichment joining a customer-managed source on the shared key.",
    "CREATE_CUSTOMER_MANAGED_PRODUCT": "Keep the objects in the existing BW/ODP reporting path until extraction is engineered.",
    "DATASPHERE_ENRICHMENT": "Customer-managed data product if the enrichment source cannot be acquired.",
    "BW_DATA_PRODUCT_ROUTE": "ODP extraction from BW or a customer-managed Datasphere replication if the Data Product Generator is ineligible.",
    "MANUAL_BUSINESS_RULE": "Retain the existing backend logic and reconcile on the covered subset only.",
    "CATALOG_REVIEW_REQUIRED": "Obtain an approved catalog import or tenant verification for the product.",
    "EXECUTION_BLOCKED": "Generate a manual implementation runbook and request the missing release, authority or entitlement.",
}


def _adapter_for(system: str) -> dict:
    s = SYSTEMS[system]
    caps = s["caps"]
    if s["type"] == "BW":
        return {"route": "BW_DPG", "supported": bool(caps.get("dpg")), "delta": True}
    if caps.get("cds_extraction"):
        return {"route": "CDS_EXTRACTION", "supported": True, "delta": True}
    if caps.get("odp"):
        return {"route": "ODP_DATASOURCE", "supported": True, "delta": True}
    return {"route": "NONE", "supported": False, "delta": False}


def _steps(decision: str, req: dict, analysis: dict, extra: dict) -> dict:
    obj, sysid = req["object"], req["system"]
    prods = analysis.get("affected_products", [])
    base = {"required_objects": [obj], "affected_products": prods, "security": [], "approvals": [], "prerequisites": [],
            "validation": ["Field-by-field comparison re-run", "Level 1 source-to-acquisition reconciliation"]}
    t = {
        "REUSE_STANDARD": dict(steps=["Install/activate the verified product if not installed", "Consume entity in the Datasphere acquisition layer",
                                      "Do not create an additional replication flow for an installed SAP-managed product"],
                               prerequisites=["Entitlement and activation confirmed in the tenant"], approvals=["Architect review"]),
        "KEY_USER_EXTENSION": dict(steps=[f"Create custom field(s) {extra.get('fields')} in the supported key-user app for the business context",
                                          "Publish the field to the data product extension", "Re-run delta analysis"],
                                   prerequisites=["Field eligible in the business context", "Product extension capability verified"],
                                   approvals=["Key-user owner", "Change management"],
                                   security=["Confirm authorization coverage for the new field"]),
        "DEVELOPER_EXTENSION": dict(steps=["Create the released extension via developer extensibility in ADT", "Activate in a non-production system",
                                           "Re-run delta analysis"],
                                    prerequisites=["Developer extensibility available for the release", "Released extension point verified"],
                                    approvals=["Development lead", "Transport owner"]),
        "DATA_PRODUCT_EXTENSION": dict(steps=["Extend the verified product with the supported customer extension", "Validate schema and version change"],
                                       prerequisites=["Product supports customer extension"], approvals=["Data product owner"]),
        "CREATE_CUSTOMER_MANAGED_PRODUCT": dict(
            steps=[f"Engineer extraction via {extra.get('route')}", "Generate and validate artifacts offline",
                   "Authorized activation in a non-production system", "Model and publish through supported BDC mechanisms"],
            prerequisites=[f"Source release supports {extra.get('route')}", "Metadata verified before deployable code is generated"],
            approvals=["Architect", "Source-system owner", "Transport owner"],
            security=["Define data ownership and access restrictions for the new product"]),
        "DATASPHERE_ENRICHMENT": dict(steps=["Acquire the enrichment source", "Create a harmonization view on the conformed key",
                                             "Document the business rule applied"], prerequisites=["Enrichment source available in Datasphere"],
                                      approvals=["Finance owner for business rules"]),
        "BW_DATA_PRODUCT_ROUTE": dict(steps=["Verify Data Product Generator eligibility (version, deployment, licence)",
                                             "Publish eligible BW provider as a data product"],
                                      prerequisites=["System version, deployment model and licence eligibility verified"],
                                      approvals=["BW owner", "Licence owner"]),
        "MANUAL_BUSINESS_RULE": dict(steps=["Record the rule in the business-rule editor with examples", "Finance owner approves",
                                            "Re-run reconciliation for dependent measures"],
                                     prerequisites=["Named human approver"], approvals=["Finance owner"]),
        "CATALOG_REVIEW_REQUIRED": dict(steps=["Import an approved catalog snapshot or verify the product in the tenant", "Re-run analysis"],
                                        prerequisites=["Catalog evidence"], approvals=["Architect"]),
        "EXECUTION_BLOCKED": dict(steps=["Do not execute", "Provide manual runbook", "Escalate the blocker"],
                                  prerequisites=[extra.get("blocker", "authority/release/entitlement")], approvals=["Owner"]),
    }[decision]
    out = {**base, **t, "implementation_steps": t["steps"]}
    out.pop("steps", None)
    for k in ("security", "approvals", "prerequisites"):
        out[k] = t.get(k, base[k])
    return out


def decide(analysis: dict, req: dict, rulebook: RuleBook | None = None, prefs: dict | None = None) -> dict:
    prefs = {**DEFAULT_PREFS, **(prefs or {})}
    system = req["system"]
    caps = SYSTEMS[system]["caps"]
    classes = sorted({g["class"] for g in analysis["gaps"]})
    cset = set(classes)
    evidence = {"gaps": analysis["gaps"], "coverage": analysis["coverage"], "catalog_state": analysis["catalog_state"]}
    extra: dict = {}
    adapter = _adapter_for(system)
    fields = sorted(analysis.get("missing_fields", []))

    def result(decision: str, reason: str, secondary: list[str] | None = None) -> dict:
        assert decision in DECISIONS
        d = _steps(decision, req, analysis, extra)
        return {"requirement": req["id"], "object": req["object"], "system": system, "decision": decision, "reason": reason,
                "supporting_evidence": evidence, "gap_classes": classes, "secondary_findings": sorted(secondary or []),
                "alternative": ALTERNATIVE[decision], **d}

    if req.get("unsupported_request"):
        extra["blocker"] = req["unsupported_request"]
        return result("EXECUTION_BLOCKED", f"unsupported request: {req['unsupported_request']}")
    if "CATALOG_UNVERIFIED" in cset:
        return result("CATALOG_REVIEW_REQUIRED", "product evidence is incomplete or unverified; no completeness claim is made")
    if cset == {"NO_GAP"}:
        return result("REUSE_STANDARD", "verified standard product satisfies all assessed requirements")
    if "PRODUCT_NOT_AVAILABLE" in cset:
        if req["alt_sources"]:
            return result("DATASPHERE_ENRICHMENT", f"no product; data can be combined in Datasphere from {req['alt_sources']}")
        return _create(result, adapter, extra, system, "no SAP-managed product covers the object", cset, req)
    structural = cset & STRUCTURAL
    if structural:
        return _create(result, adapter, extra, system, f"structural gap(s): {sorted(structural)}", cset, req)
    if cset & {"SEMANTIC_GAP", "BUSINESS_LOGIC_GAP"}:
        rules = [r for r in [req.get("semantic_rule")] + req["logic"] if r]
        unresolved = rulebook.unresolved(rules) if rulebook else rules
        if unresolved:
            extra["rules"] = unresolved
            return result("MANUAL_BUSINESS_RULE", f"semantics/logic not determinable until rule(s) approved: {unresolved}",
                          sorted(cset - {"SEMANTIC_GAP", "BUSINESS_LOGIC_GAP"}))
        return result("DATASPHERE_ENRICHMENT", "approved explicit rule(s) can be applied in Datasphere", sorted(cset))
    if "FIELD_GAP" in cset:
        product_ext = _product_extension(analysis)
        fdefs = {n: req["fields"][n] for n in fields if n in req["fields"]}
        eligible = [n for n, f in fdefs.items() if f["custom"] and f["type"] in KEY_USER_TYPES and not f["key"]]
        all_eligible = bool(fdefs) and len(eligible) == len(fdefs)
        ku_ok = caps.get("key_user_ext") and product_ext["key_user"] and all_eligible
        dev_ok = caps.get("developer_ext") and product_ext["developer"]
        dpe_ok = product_ext["data_product_extension"]
        order = (["KEY_USER_EXTENSION", "DEVELOPER_EXTENSION", "DATA_PRODUCT_EXTENSION"] if prefs["prefer_key_user_for_simple_fields"]
                 else ["DATA_PRODUCT_EXTENSION", "DEVELOPER_EXTENSION", "KEY_USER_EXTENSION"])
        ok = {"KEY_USER_EXTENSION": ku_ok, "DEVELOPER_EXTENSION": dev_ok, "DATA_PRODUCT_EXTENSION": dpe_ok}
        extra["fields"] = fields
        for d in order:
            if ok[d]:
                why = {"KEY_USER_EXTENSION": f"all {len(fields)} missing field(s) are eligible custom attributes and the product supports key-user extension",
                       "DEVELOPER_EXTENSION": "supported developer extensibility is required for the missing field(s)",
                       "DATA_PRODUCT_EXTENSION": "the product supports customer extension for the missing field(s)"}[d]
                return result(d, why, sorted(cset - {"FIELD_GAP"}))
        if cset == {"FIELD_GAP"} and req["alt_sources"]:
            return result("DATASPHERE_ENRICHMENT", "fields available from another acquired source")
        reason = "no supported extension route for the missing field(s)" + ("" if all_eligible else
                                                                          "; at least one field is not eligible for key-user extension")
        return _create(result, adapter, extra, system, reason, cset, req)
    if "SECURITY_GAP" in cset:
        return result("DATASPHERE_ENRICHMENT", "product does not enforce required authorization objects; apply Datasphere data access controls")
    return result("CATALOG_REVIEW_REQUIRED", "unclassified gap; manual review")


def _product_extension(analysis: dict) -> dict:
    """Extension capabilities come from the analysed (primary) catalog candidate, never from product names."""
    for c in analysis["candidates"]:
        if c["product"] == analysis.get("primary_product"):
            return c["extension"]
    return {"key_user": False, "developer": False, "data_product_extension": False}


def _create(result, adapter, extra, system, reason, cset, req):
    if SYSTEMS[system]["type"] == "BW":
        elig = SYSTEMS[system]["caps"].get("dpg_eligibility", {})
        if SYSTEMS[system]["caps"].get("dpg") and elig.get("version_ok") and elig.get("deployment_ok"):
            extra["route"] = "BW_DPG"
            return result("BW_DATA_PRODUCT_ROUTE", f"{reason}; BW Data Product Generator eligibility indicators positive "
                          f"(licence {elig.get('license')}) - to be verified")
        extra["blocker"] = "BW Data Product Generator not eligible"
        return result("EXECUTION_BLOCKED", f"{reason}; BW route ineligible")
    if not adapter["supported"]:
        extra["blocker"] = f"no supported extraction mechanism for {system}"
        return result("EXECUTION_BLOCKED", f"{reason}; no supported extraction mechanism")
    extra["route"] = adapter["route"]
    return result("CREATE_CUSTOMER_MANAGED_PRODUCT", reason, sorted(cset))


def decide_all(analyses: list[dict], rulebook: RuleBook | None, prefs: dict | None = None) -> list[dict]:
    return [decide(a["analysis"], a["req"], rulebook, prefs) for a in analyses]
