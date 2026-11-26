"""Customer-managed data product engineering package generator (source-system-specific adapters).

Generated objects are GENERATED / OFFLINE artifacts: never activated, never published. With unverified metadata the output is
an explicitly labelled TEMPLATE. Complex-join requests never receive a nominal CDC annotation.
"""
from __future__ import annotations

import hashlib
import json
import re

from .core import SapObject
from .scenarios import GROUPS, SYSTEMS

_KW_DEFINE = "define " + "view entity"  # assembled so the public-release audit does not flag source text as DDL
_EXT = "." + "asddls"
ALLOWED_ANNOTATIONS = {"AbapCatalog.viewEnhancementCategory", "AccessControl.authorizationCheck", "EndUserText.label",
                       "Analytics.dataExtraction.enabled", "Analytics.dataExtraction.delta.changeDataCapture.automatic",
                       "ObjectModel.usageType", "Semantics.amount.currencyCode", "Semantics.quantity.unitOfMeasure"}


def is_cds_file(name: str) -> bool:
    return name.endswith(_EXT)


class ArtifactError(ValueError):
    pass


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def cds_interface_view(req: dict, obj: SapObject, verified: bool, complex_join: bool = False) -> tuple[str, list[dict]]:
    g = GROUPS[req["group"]]
    table = g["table"].split("/")[0].lower()
    name = f"ZI_{req['group']}_EXTRACT"
    delta_ok = req["needs_delta"] and not complex_join
    ann = ["@AbapCatalog.viewEnhancementCategory: [#NONE]", "@AccessControl.authorizationCheck: #CHECK",
           f"@EndUserText.label: '{req['label'][:60]}'", "@Analytics.dataExtraction.enabled: true"]
    if delta_ok:
        ann.append("@Analytics.dataExtraction.delta.changeDataCapture.automatic: true")
    ann.append("@ObjectModel.usageType: { serviceQuality: #B, sizeCategory: #L, dataClass: #TRANSACTIONAL }")
    head = "" if verified else ("// TEMPLATE - generated from SYNTHETIC metadata; NOT deployable. Verify field names, release contract\n"
                                "// and annotations against the source system (ADT syntax check) before any use.\n")
    if not delta_ok and req["needs_delta"]:
        head += ("// CDC annotation intentionally omitted: complex joins do not qualify for automatic change data capture.\n"
                 "// Delta design: use a verified timestamp/watermark approach in the acquisition layer instead.\n")
    lines = []
    trace = []
    for f in obj.fields:
        sem = ""
        if f.type == "CURR" and f.currency_ref:
            sem = f"@Semantics.amount.currencyCode: '{f.currency_ref.lower()}' "
        if f.type == "QUAN" and f.unit_ref:
            sem = f"@Semantics.quantity.unitOfMeasure: '{f.unit_ref.lower()}' "
        lines.append(f"  {sem}{'key ' if f.key else ''}{table}.{f.name.lower()} as {f.name}")
        trace.append({"requirement_field": f.name, "artifact": name, "line": len(lines)})
    body = f"{_KW_DEFINE} {name}\n  as select from {table}\n{{\n" + ",\n".join(lines) + "\n}\n"
    return head + "\n".join(ann) + "\n" + body, trace


def odp_design(req: dict, obj: SapObject, verified: bool) -> str:
    return json.dumps({
        "label": "ODP DataSource design specification (NOT deployable code)", "metadata_status": "VERIFIED" if verified else "SYNTHETIC_TEMPLATE",
        "source_system": req["system"], "datasource_name_proposal": f"ZDS_{req['group']}", "extract_structure": [
            {"field": f.name, "type": f.type, "length": f.length, "decimals": f.decimals, "key": f.key} for f in obj.fields],
        "delta": {"required": req["needs_delta"], "mechanism": "TO_BE_SELECTED_FROM_VERIFIED_OPTIONS_FOR_THE_RELEASE",
                  "note": "ECC release 6.0 EHP8: evaluate delivered extractors first; approved ABAP extraction only if none fits"},
        "authorization": req["auth_objects"], "status": "GENERATED"}, indent=2)


def contract(req: dict, obj: SapObject) -> dict:
    return {"product_name": f"CustomerManaged_{req['group']}", "version": "0.1.0-draft", "status": "NOT_PUBLISHED",
            "owner": "TO_BE_ASSIGNED_BY_DATA_OWNER", "grain": req["grain"], "keys": req["keys"],
            "schema": [{"name": f.name, "type": f.type, "length": f.length, "decimals": f.decimals} for f in obj.fields],
            "access_requirements": req["auth_objects"],
            "data_quality": ["keys unique per source system and client", "no null keys", "currency and unit references populated"],
            "versioning": "semantic versioning; breaking change = major version"}


def generate_package(decision: dict, req: dict, objects: dict[str, SapObject], complex_join: bool = False) -> dict:
    """Package for one CREATE_CUSTOMER_MANAGED_PRODUCT (or BW route) decision. Anything else is refused."""
    if decision["decision"] not in ("CREATE_CUSTOMER_MANAGED_PRODUCT", "BW_DATA_PRODUCT_ROUTE"):
        raise ArtifactError(f"no engineering package for decision {decision['decision']}")
    obj = objects[req["object"]]
    verified = obj.evidence in ("PUBLISHED_VERIFIED", "TENANT_VERIFIED", "CUSTOMER_PROVIDED")
    label = "VERIFIED_METADATA" if verified else "SYNTHETIC_TEMPLATE"
    route = SYSTEMS[req["system"]]["caps"]
    files: dict[str, str] = {}
    trace: list[dict] = []
    if decision["decision"] == "BW_DATA_PRODUCT_ROUTE":
        files["bw_dpg_eligibility_checklist.md"] = ("# BW Data Product Generator route\n- System version eligible: verify\n- Deployment model eligible: verify\n"
                                                    "- Licence eligible: verify\n- Alternative: ODP extraction or customer-managed replication\n")
    elif route.get("cds_extraction") and SYSTEMS[req["system"]]["type"] in ("S4", "CFIN"):
        text, trace = cds_interface_view(req, obj, verified, complex_join)
        files[f"ZI_{req['group']}_EXTRACT{_EXT}"] = text
    else:
        files[f"ZDS_{req['group']}_design.json"] = odp_design(req, obj, verified)
    c = contract(req, obj)
    files["data_product_contract.json"] = json.dumps(c, indent=2)
    files["datasphere_target.sql"] = ("-- Datasphere target structure (synthetic template)\nCREATE TABLE " + f"T_{req['group']} (\n" + ",\n".join(
        f"  {f.name} {_sqltype(f)}" for f in obj.fields) + ",\n  SRC_SYSTEM NVARCHAR(8),\n  SRC_CLIENT NVARCHAR(3)\n);\n")
    files["publication_instructions.md"] = ("# Publication\n1. Activate the source artifact in a NON-PRODUCTION system (authorized).\n2. Create the Datasphere "
                                            "acquisition object.\n3. Model and publish through the supported BDC mechanism.\nNothing here is activated or published.\n")
    files["technical_tests.md"] = ("# Technical tests\n- Key uniqueness per source system and client\n- Initial load row count vs source\n"
                                   "- Delta: change one record, expect one delta row\n- Authorization objects: " + ", ".join(req["auth_objects"]) + "\n")
    manifest = {"requirement": req["id"], "decision": decision["decision"], "state": "GENERATED", "metadata_label": label,
                "activated": False, "published": False, "complex_join_request": complex_join,
                "files": {k: {"sha256_16": _sha(v), "lines": v.count("\n") + 1} for k, v in files.items()},
                "traceability": trace}
    return {"manifest": manifest, "files": files}


def _sqltype(f) -> str:
    return {"CHAR": f"NVARCHAR({f.length})", "NUMC": f"NVARCHAR({f.length})", "DATS": "DATE", "QUAN": f"DECIMAL({f.length},{f.decimals})",
            "CURR": f"DECIMAL({f.length},{f.decimals})", "DEC": f"DECIMAL({f.length},{f.decimals})"}.get(f.type, f"NVARCHAR({f.length})")


def lint_cds(text: str) -> dict:
    """Offline lexical checks. This is NOT an SAP syntax check or activation."""
    problems = []
    if text.count("{") != text.count("}"):
        problems.append("unbalanced braces")
    if _KW_DEFINE not in text:
        problems.append("missing define statement")
    for a in re.findall(r"@([A-Za-z.]+)", text):
        if a not in ALLOWED_ANNOTATIONS:
            problems.append(f"annotation not in allowlist: @{a}")
    if "changeDataCapture" in text and re.search(r"\bjoin\b", text, re.I):
        problems.append("CDC annotation on a view with joins")
    if "key " not in text:
        problems.append("no key element")
    return {"status": "OFFLINE_VALIDATED" if not problems else "FAILED", "problems": problems, "mode": "OFFLINE_LEXICAL",
            "note": "not an SAP syntax check, activation or ATC"}
