"""Many-to-many mapping of SAP objects to data-product entities and the delta (gap) analysis engine."""
from __future__ import annotations

from .catalog import Catalog
from .core import GAPS, SapObject
from .scenarios import GROUPS, SYSTEMS, TRANSACTIONAL

PRECEDENCE = ["CATALOG_UNVERIFIED", "PRODUCT_NOT_AVAILABLE", "VERSION_GAP", "KEY_GAP", "GRANULARITY_GAP", "RELATIONSHIP_GAP",
              "SEMANTIC_GAP", "BUSINESS_LOGIC_GAP", "EXTRACTION_GAP", "SECURITY_GAP", "FIELD_GAP", "NO_GAP"]
assert set(PRECEDENCE) == set(GAPS)
DIMENSIONS = ["Business entity", "Field coverage", "Field types", "Keys", "Grain", "Relationships", "Cardinality", "Measures",
              "Currency", "Units", "Filters", "Business logic", "Extraction", "Authorization", "Source compatibility",
              "Availability"]


def build_requirement(group: str, sys_id: str, objects: dict[str, SapObject]) -> dict | None:
    """Requirement derived from the discovered object metadata (not from names)."""
    g = GROUPS[group]
    obj = next((o for o in objects.values() if o.system == sys_id and o.group == group and o.obj_type != "DDIC_TABLE"), None)
    if obj is None:
        return None
    fields = {f.name: {"type": f.type, "length": f.length, "decimals": f.decimals, "custom": f.custom, "key": f.key,
                       "currency_ref": f.currency_ref, "unit_ref": f.unit_ref} for f in obj.fields}
    logic = list(g.get("logic", []))
    return {"id": f"REQ-{sys_id}-{group}", "group": group, "label": g["label"], "system": sys_id, "object": obj.id,
            "object_type": obj.obj_type, "release_family": SYSTEMS[sys_id].get("release_family", ""), "domain": g["dom"],
            "fields": fields, "keys": list(obj.keys), "grain": obj.grain,
            "relationships": [d for d in g["dep"]], "needs_delta": group in TRANSACTIONAL, "auth_objects": list(g["auth"]),
            "logic": logic, "semantics": dict(g.get("sem", {})),
            "semantic_rule": "R-AMOUNT-BASIS-001" if g.get("sem") else None,
            "alt_sources": list(g.get("alt", [])), "evidence": obj.evidence}


def _type_ok(req: dict, prod: dict) -> bool:
    return prod["type"] == req["type"] and prod["length"] >= req["length"] and prod["decimals"] >= req["decimals"]


def compare(req: dict, product: dict, entity: dict, catalog: Catalog, mode: str) -> dict:
    """One requirement vs one product entity, across the 16 dimensions."""
    dims: dict[str, dict] = {}
    gaps: list[dict] = []

    def gap(cls: str, dim: str, detail, items=None):
        gaps.append({"class": cls, "dimension": dim, "detail": detail, "items": sorted(items or [])})

    if not catalog.usable(product, mode):
        ev = catalog.effective_evidence(product, mode)
        for d in DIMENSIONS:
            dims[d] = {"status": "UNASSESSED", "detail": f"product evidence {ev} is not usable in {mode}"}
        gap("CATALOG_UNVERIFIED", "Availability", f"evidence {ev}")
        return {"product": product["product_id"], "entity": entity["entity"], "extension": product["extension"], "dimensions": dims, "gaps": gaps,
                "coverage": {"numerator": 0, "denominator": 0, "unassessed": sorted(req["fields"]), "percent": None},
                "missing_fields": [], "type_mismatches": []}
    dims["Business entity"] = {"status": "MATCH", "detail": f"entity {entity['entity']} declares coverage of {req['group']}"}
    pf = entity["fields"]
    missing = sorted(n for n in req["fields"] if n not in pf)
    mism = sorted(n for n in req["fields"] if n in pf and not _type_ok(req["fields"][n], pf[n]))
    covered = [n for n in req["fields"] if n in pf and n not in mism]
    dims["Field coverage"] = {"status": "GAP" if missing else "MATCH", "detail": f"{len(covered)}/{len(req['fields'])} fields",
                              "missing": missing}
    dims["Field types"] = {"status": "GAP" if mism else "MATCH", "detail": mism}
    if missing or mism:
        gap("FIELD_GAP", "Field coverage", {"missing": missing, "type_mismatch": mism}, missing + mism)
    kgap = any(k not in entity["keys"] for k in req["keys"])
    dims["Keys"] = {"status": "GAP" if kgap else "MATCH", "detail": sorted(set(req["keys"]) - set(entity["keys"]))}
    if kgap:
        gap("KEY_GAP", "Keys", f"required keys not in product keys: {sorted(set(req['keys']) - set(entity['keys']))}",
            set(req["keys"]) - set(entity["keys"]))
    ggap = req["grain"] != entity["grain"]
    dims["Grain"] = {"status": "GAP" if ggap else "MATCH", "detail": f"required '{req['grain']}' vs product '{entity['grain']}'"}
    if ggap:
        gap("GRANULARITY_GAP", "Grain", dims["Grain"]["detail"])
    rel_missing = sorted(set(req["relationships"]) - set(entity["relationships"]))
    dims["Relationships"] = {"status": "GAP" if rel_missing else "MATCH", "detail": rel_missing}
    if rel_missing:
        gap("RELATIONSHIP_GAP", "Relationships", f"missing associations to {rel_missing}", rel_missing)
    dims["Cardinality"] = {"status": "UNASSESSED", "detail": "catalog does not declare association cardinality"}
    meas = [n for n, f in req["fields"].items() if f["type"] in ("CURR", "QUAN")]
    dims["Measures"] = {"status": "MATCH" if all(m in pf for m in meas) else "GAP", "detail": f"{len(meas)} measure fields"}
    curr_req = any(f["type"] == "CURR" for f in req["fields"].values())
    dims["Currency"] = {"status": ("MATCH" if "WAERS" in pf else "GAP") if "WAERS" in req["fields"] else
                        ("UNASSESSED" if curr_req else "MATCH"),
                        "detail": "currency reference WAERS" if curr_req else "no currency amounts"}
    quan_req = any(f["type"] == "QUAN" for f in req["fields"].values())
    dims["Units"] = {"status": ("MATCH" if "MEINS" in pf else "GAP") if "MEINS" in req["fields"] else
                     ("UNASSESSED" if quan_req else "MATCH"), "detail": "unit reference MEINS" if quan_req else "no quantities"}
    dims["Filters"] = {"status": "UNASSESSED", "detail": "business scope filters are not declared by the catalog"}
    sem_bad = {k: (v, entity["semantics"].get(k)) for k, v in req["semantics"].items()
               if entity["semantics"].get(k) not in (None, v)}
    if sem_bad:
        gap("SEMANTIC_GAP", "Measures", {k: {"required": a, "product": b} for k, (a, b) in sem_bad.items()}, sem_bad)
        dims["Measures"]["status"] = "GAP"
    logic_missing = sorted(set(req["logic"]) - set(entity["logic_supported"]))
    dims["Business logic"] = {"status": "GAP" if logic_missing else "MATCH", "detail": logic_missing}
    if logic_missing:
        gap("BUSINESS_LOGIC_GAP", "Business logic", f"rules not carried by the product: {logic_missing}", logic_missing)
    xgap = req["needs_delta"] and not entity["delta"]
    dims["Extraction"] = {"status": "GAP" if xgap else "MATCH", "detail": "delta required" if req["needs_delta"] else "initial only"}
    if xgap:
        gap("EXTRACTION_GAP", "Extraction", "delta processing required but not provided by the product")
    auth_missing = sorted(set(req["auth_objects"]) - set(entity["auth_objects"]))
    dims["Authorization"] = {"status": "GAP" if auth_missing else "MATCH", "detail": auth_missing}
    if auth_missing:
        gap("SECURITY_GAP", "Authorization", f"authorization objects not enforced by the product: {auth_missing}", auth_missing)
    rel_ok = req["release_family"] in product["supported_releases"]
    dims["Source compatibility"] = {"status": "MATCH" if rel_ok else "GAP",
                                    "detail": f"{req['release_family']} vs {product['supported_releases']}"}
    if not rel_ok:
        gap("VERSION_GAP", "Source compatibility", dims["Source compatibility"]["detail"])
    avail = catalog.availability(product)
    if product["entitlement"] == "UNKNOWN":
        # not stated (for example a CSN file cannot say): this is 'not established', never 'SAP delivers nothing'
        dims["Availability"] = {"status": "UNASSESSED", "detail": avail}
        gap("CATALOG_UNVERIFIED", "Availability", "entitlement not stated by the source; availability is not established")
    else:
        dims["Availability"] = {"status": "MATCH" if product["entitlement"] == "ENTITLED" else "GAP", "detail": avail}
        if product["entitlement"] != "ENTITLED":
            gap("PRODUCT_NOT_AVAILABLE", "Availability", f"entitlement {product['entitlement']}")
    return {"product": product["product_id"], "entity": entity["entity"], "extension": product["extension"], "dimensions": dims, "gaps": gaps,
            "coverage": {"numerator": len(covered), "denominator": len(req["fields"]), "unassessed": [],
                         "percent": round(100.0 * len(covered) / len(req["fields"]), 1) if req["fields"] else None},
            "missing_fields": missing, "type_mismatches": mism}


def analyze(req: dict, catalog: Catalog, mode: str = "DEMO") -> dict:
    """Analyse one requirement against every catalog entity that declares coverage of it (many-to-many)."""
    cands = catalog.find(req["group"])
    base = {"requirement": req["id"], "group": req["group"], "label": req["label"], "system": req["system"],
            "object": req["object"], "release_family": req["release_family"]}
    if not cands:
        complete = catalog.domain_complete(req["domain"])
        cls = "PRODUCT_NOT_AVAILABLE" if complete else "CATALOG_UNVERIFIED"
        why = ("no product covers this object and catalog completeness for the domain is declared"
               if complete else "no product found in the accessible catalog; completeness not established, so state is UNKNOWN")
        return {**base, "candidates": [], "gaps": [{"class": cls, "dimension": "Business entity", "detail": why, "items": []}],
                "primary_gap": cls, "catalog_state": "NOT_FOUND_COMPLETE" if complete else "UNKNOWN",
                "coverage": {"numerator": 0, "denominator": 0, "unassessed": sorted(req["fields"]), "percent": None},
                "missing_fields": [], "affected_products": []}
    results = [compare(req, p, e, catalog, mode) for p, e in cands]
    # primary = best candidate: usable first, then fewest gaps by precedence, then id (deterministic)
    def rank(r):
        worst = min((PRECEDENCE.index(g["class"]) for g in r["gaps"]), default=len(PRECEDENCE))
        return (-worst, -r["coverage"]["numerator"], r["product"], r["entity"])  # least severe worst-gap first
    primary = sorted(results, key=rank)[0]
    # union coverage across all candidate entities (a field is covered if any usable entity carries it)
    usable = [(p, e) for p, e in cands if catalog.usable(p, mode)]
    union_fields = {n for _, e in usable for n in e["fields"]}
    union_missing = sorted(n for n in req["fields"] if n not in union_fields) if usable else []
    if usable:
        cov = {"numerator": len(req["fields"]) - len(union_missing), "denominator": len(req["fields"]), "unassessed": [],
               "percent": round(100.0 * (len(req["fields"]) - len(union_missing)) / len(req["fields"]), 1)}
    else:
        cov = primary["coverage"]
    gaps = [g for g in primary["gaps"]]
    classes = {g["class"] for g in gaps}
    if "FIELD_GAP" in classes and usable and not union_missing and not any(r["type_mismatches"] for r in results):
        gaps = [g for g in gaps if g["class"] != "FIELD_GAP"]  # another candidate entity covers the missing fields
    if not gaps:
        gaps = [{"class": "NO_GAP", "dimension": "all", "detail": "all assessed dimensions match", "items": []}]
    primary_gap = min((g["class"] for g in gaps), key=PRECEDENCE.index)
    return {**base, "candidates": results, "gaps": gaps, "primary_gap": primary_gap, "primary_product": primary["product"], "catalog_state": "FOUND",
            "coverage": cov, "missing_fields": union_missing if usable else primary["missing_fields"],
            "affected_products": sorted({p["product_id"] for p, _ in cands})}


def analyze_scenario(scenario_cfg: dict, objects: dict[str, SapObject], catalog: Catalog, mode: str = "DEMO") -> list[dict]:
    out = []
    for sid in scenario_cfg["sources"]:
        for gid in sorted(GROUPS, key=lambda k: GROUPS[k]["n"]):
            req = build_requirement(gid, sid, objects)
            if req is not None:
                out.append({"req": req, "analysis": analyze(req, catalog, mode)})
    return out


def coverage_summary(results: list[dict]) -> dict:
    num = sum(r["analysis"]["coverage"]["numerator"] for r in results)
    den = sum(r["analysis"]["coverage"]["denominator"] for r in results)
    unassessed = sum(len(r["analysis"]["coverage"]["unassessed"]) for r in results)
    return {"numerator": num, "denominator": den, "unassessed": unassessed,
            "percent": round(100.0 * num / den, 1) if den else None,
            "note": "coverage uses only comparable requirements; unassessed fields are excluded from the denominator"}
