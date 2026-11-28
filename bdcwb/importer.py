"""Import-assisted delta: run the same delta engine on two customer-supplied exports instead of the synthetic fixtures.

This is the implementable path that needs no live connector. Two JSON files, each small and inspectable:
  1. an extension inventory (what the customer's S/4HANA objects contain, custom fields flagged) - produced by a read-only collector
     inside the customer system, or exported by an authorised person;
  2. a data-product catalog export (what the SAP-delivered products expose) - from the BDC cockpit or an approved metadata export.
Nothing is connected, written or stored; files are parsed, validated, compared in memory and discarded. Imported evidence is CUSTOMER_PROVIDED
and is never upgraded; a file that claims a stronger class is rejected.
"""
from __future__ import annotations

import json
from typing import Any

from . import decision as dec, mapping
from .catalog import Catalog, CatalogError
from .core import EVIDENCE
from .scenarios import SYSTEMS
from .delta import DELTA_TYPES, ROUTES, _classify, _fmt

INVENTORY_SCHEMA = "bdc-delta-inventory/1"
CATALOG_SCHEMA = "bdc-delta-catalog/1"
LIMITS = {"max_bytes": 1_000_000, "max_objects": 200, "max_fields_per_object": 600, "max_products": 150, "max_entities_per_product": 60,
          "max_fields_per_entity": 400, "max_entities_per_business_object": 10, "max_depth": 40}
CAP_KEYS = {"key_user_ext", "developer_ext", "odp", "cds_extraction"}  # capabilities a file may declare (dpg is never declarable)
PROFILE = {"S4_2023": "S4A", "S4_2022": "S4B", "ECC_6_0_EHP8": "ECC01"}  # release family -> built-in capability profile
IMPORT_EVIDENCE = "CUSTOMER_PROVIDED"
FIELD_TYPES = {"CHAR", "NUMC", "DATS", "TIMS", "CURR", "QUAN", "DEC", "INT4", "CUKY", "UNIT", "LANG", "STRING", "CLNT", "TIMESTAMP", "BOOL", "UUID", "FLTP", "RAW"}
FIDELITY_ROUTE = ("Correct the extension so the delivered product carries the field with its original type, business name and unit or currency reference, "
                  "then re-activate and re-check the catalog entry; until then restore meaning in the Datasphere semantic layer. "
                  "Procedure per product and release must be confirmed in SAP documentation.")


def _no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup:
        raise ValueError(f"duplicate key {sorted(dup)[0]!r}")
    return dict(pairs)


def _depth(x, d: int = 0) -> int:
    """Nesting depth without recursion into hostile structures beyond the limit."""
    stack, deepest = [(x, 1)], 0
    while stack:
        v, n = stack.pop()
        deepest = max(deepest, n)
        if deepest > LIMITS["max_depth"]:
            return deepest
        if isinstance(v, dict):
            stack += [(c, n + 1) for c in v.values() if isinstance(c, (dict, list))]
        elif isinstance(v, list):
            stack += [(c, n + 1) for c in v if isinstance(c, (dict, list))]
    return deepest


def parse(text: str | bytes, what: str) -> tuple[dict | None, list[str]]:
    raw = text if isinstance(text, (bytes, bytearray)) else text.encode("utf-8")
    if len(raw) > LIMITS["max_bytes"]:
        return None, [f"{what}: file is larger than {LIMITS['max_bytes']} bytes"]
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except RecursionError:
        return None, [f"{what}: nested too deeply"]
    except (UnicodeDecodeError, ValueError) as e:
        return None, [f"{what}: not valid UTF-8 JSON ({str(e)[:80]})"]
    except Exception:  # noqa: BLE001 - a hostile file must produce a message, never an exception
        return None, [f"{what}: could not be read as JSON"]
    if not isinstance(doc, dict):
        return None, [f"{what}: the top level must be a JSON object"]
    if _depth(doc) > LIMITS["max_depth"]:
        return None, [f"{what}: nested deeper than {LIMITS['max_depth']} levels"]
    return doc, []


def _bool_errors(where: str, d: dict, keys: tuple) -> list[str]:
    return [f"{where}: '{k}' must be true or false (not {d[k]!r})" for k in keys if k in d and not isinstance(d[k], bool)]


def _field_errors(where: str, f: Any) -> list[str]:
    if not isinstance(f, dict) or not isinstance(f.get("name"), str) or not f["name"].strip():
        return [f"{where}: each field needs a text 'name'"]
    errs = _bool_errors(f"{where}.{f['name']}", f, ("custom", "key"))
    for k in ("label", "currency_ref", "unit_ref"):
        if k in f and f[k] is not None and not isinstance(f[k], str):
            errs.append(f"{where}.{f['name']}: '{k}' must be text")
    if str(f.get("type", "CHAR")).upper() not in FIELD_TYPES:
        errs.append(f"{where}.{f['name']}: type {f.get('type')!r} is not one of {sorted(FIELD_TYPES)}")
    for k in ("length", "decimals"):
        if k in f and not (isinstance(f[k], int) and not isinstance(f[k], bool) and 0 <= f[k] <= 1000):
            errs.append(f"{where}.{f['name']}: {k} must be a whole number from 0 to 1000")
    return errs


def validate_inventory(doc: dict) -> list[str]:
    errs: list[str] = []
    if doc.get("schema") != INVENTORY_SCHEMA:
        errs.append(f"inventory: schema must be {INVENTORY_SCHEMA!r}")
    src = doc.get("source")
    if not isinstance(src, dict) or not isinstance(src.get("release_family"), str) or src.get("release_family") not in PROFILE:
        errs.append(f"inventory: source.release_family must be one of {sorted(PROFILE)} (these select the capability profile)")
    caps = src.get("capabilities") if isinstance(src, dict) else None
    if caps is not None:
        if not isinstance(caps, dict) or set(caps) - CAP_KEYS or any(not isinstance(v, bool) for v in caps.values()):
            errs.append(f"inventory: source.capabilities must be an object with only these true/false keys: {sorted(CAP_KEYS)}")
    if doc.get("evidence", IMPORT_EVIDENCE) != IMPORT_EVIDENCE:
        errs.append(f"inventory: evidence must be {IMPORT_EVIDENCE} (imports are never upgraded)")
    objs = doc.get("objects")
    if not isinstance(objs, list) or not objs:
        return errs + ["inventory: 'objects' must be a non-empty list"]
    if len(objs) > LIMITS["max_objects"]:
        return errs + [f"inventory: more than {LIMITS['max_objects']} objects"]
    seen = set()
    for i, o in enumerate(objs):
        w = f"objects[{i}]"
        if not isinstance(o, dict) or not isinstance(o.get("name"), str) or not isinstance(o.get("business_object"), str):
            errs.append(f"{w}: needs text 'name' and 'business_object'")
            continue
        for k in ("keys", "relationships", "auth_objects", "logic", "alt_sources"):
            if k in o and o[k] is not None and not (isinstance(o[k], list) and all(isinstance(x, str) for x in o[k])):
                errs.append(f"{w} {o['name']}: '{k}' must be a list of text")
        if "semantics" in o and o["semantics"] is not None and not isinstance(o["semantics"], dict):
            errs.append(f"{w} {o['name']}: 'semantics' must be an object")
        errs += _bool_errors(f"{w} {o['name']}", o, ("needs_delta",))
        if o["name"] in seen:
            errs.append(f"{w}: duplicate object name {o['name']}")
        seen.add(o["name"])
        fl = o.get("fields")
        if not isinstance(fl, list) or not fl:
            errs.append(f"{w} {o['name']}: 'fields' must be a non-empty list")
            continue
        if len(fl) > LIMITS["max_fields_per_object"]:
            errs.append(f"{w} {o['name']}: more than {LIMITS['max_fields_per_object']} fields")
            continue
        names = [f.get("name") for f in fl if isinstance(f, dict)]
        if len(set(names)) != len(names):
            errs.append(f"{w} {o['name']}: duplicate field names")
        for f in fl:
            errs += _field_errors(f"{w} {o['name']}", f)
    return errs


def validate_catalog(doc: dict, example: bool = False) -> list[str]:
    errs: list[str] = []
    if doc.get("schema") != CATALOG_SCHEMA:
        errs.append(f"catalog: schema must be {CATALOG_SCHEMA!r}")
    prods = doc.get("products")
    if not isinstance(prods, list) or not prods:
        return errs + ["catalog: 'products' must be a non-empty list"]
    if len(prods) > LIMITS["max_products"]:
        return errs + [f"catalog: more than {LIMITS['max_products']} products"]
    comp = doc.get("domain_completeness")
    if comp is not None and (not isinstance(comp, dict) or not all(isinstance(v, bool) for v in comp.values())):
        errs.append("catalog: 'domain_completeness' must map each domain to true or false")
    seen_pid: set = set()
    per_group: dict = {}
    for i, p in enumerate(prods):
        w = f"products[{i}]"
        if not isinstance(p, dict) or not isinstance(p.get("product_id"), str):
            errs.append(f"{w}: needs a text 'product_id'")
            continue
        if p["product_id"] in seen_pid:
            errs.append(f"{w}: duplicate product_id {p['product_id']}")
        seen_pid.add(p["product_id"])
        ev = p.get("evidence", IMPORT_EVIDENCE)
        if ev not in EVIDENCE:
            errs.append(f"{w} {p['product_id']}: unknown evidence class {ev!r}")
        elif ev != IMPORT_EVIDENCE and not example:
            errs.append(f"{w} {p['product_id']}: evidence {ev!r} cannot be imported; an imported catalog is {IMPORT_EVIDENCE} (never upgraded)")
        if "extension" in p and p["extension"] is not None:
            if not isinstance(p["extension"], dict):
                errs.append(f"{w} {p['product_id']}: 'extension' must be an object")
            else:
                errs += _bool_errors(f"{w} {p['product_id']}.extension", p["extension"], ("key_user", "developer", "data_product_extension"))
        if "supported_releases" in p and p["supported_releases"] is not None and not (isinstance(p["supported_releases"], list) and all(isinstance(x, str) for x in p["supported_releases"])):
            errs.append(f"{w} {p['product_id']}: 'supported_releases' must be a list of text")
        ents = p.get("entities")
        if not isinstance(ents, list) or not ents or len(ents) > LIMITS["max_entities_per_product"]:
            errs.append(f"{w} {p['product_id']}: 'entities' must be a list of 1 to {LIMITS['max_entities_per_product']}")
            continue
        seen_ent: set = set()
        for j, e in enumerate(ents):
            if (not isinstance(e, dict) or not isinstance(e.get("entity"), str) or not isinstance(e.get("covers"), list)
                    or not all(isinstance(c, str) for c in e["covers"]) or not isinstance(e.get("fields"), dict)):
                errs.append(f"{w}.entities[{j}]: needs 'entity', a 'covers' list of business objects and a 'fields' object")
                continue
            if e["entity"] in seen_ent:
                errs.append(f"{w}.entities[{j}]: duplicate entity {e['entity']}")
            seen_ent.add(e["entity"])
            if len(e["fields"]) > LIMITS["max_fields_per_entity"]:
                errs.append(f"{w}.{e['entity']}: more than {LIMITS['max_fields_per_entity']} fields")
                continue
            for k in ("keys", "relationships", "auth_objects", "logic_supported"):
                if k in e and e[k] is not None and not (isinstance(e[k], list) and all(isinstance(x, str) for x in e[k])):
                    errs.append(f"{w}.{e['entity']}: '{k}' must be a list of text")
            if "semantics" in e and e["semantics"] is not None and not isinstance(e["semantics"], dict):
                errs.append(f"{w}.{e['entity']}: 'semantics' must be an object")
            errs += _bool_errors(f"{w}.{e['entity']}", e, ("delta",))
            for c in e["covers"]:
                per_group[c] = per_group.get(c, 0) + 1
            for n, f in e["fields"].items():
                errs += _field_errors(f"{w}.{e['entity']}", {**(f if isinstance(f, dict) else {}), "name": n})
    crowded = sorted(g for g, n in per_group.items() if n > LIMITS["max_entities_per_business_object"])
    if crowded:
        errs.append(f"catalog: more than {LIMITS['max_entities_per_business_object']} entities cover the business object(s) {', '.join(crowded[:3])}")
    return errs


def _profile_for(src: dict) -> tuple[str, bool]:
    """Capability profile for the route. A file that declares source.capabilities gets a derived profile (bounded set, idempotent);
    otherwise the built-in profile of the release family. Returns (system key, declared_by_file)."""
    base = PROFILE[src["release_family"]]
    caps = src.get("capabilities")
    if not caps:
        return base, False
    merged = {**SYSTEMS[base]["caps"], **caps, "dpg": False}
    key = "IMP_" + base + "_" + "".join("1" if merged.get(k) else "0" for k in sorted(CAP_KEYS))
    if key not in SYSTEMS:
        SYSTEMS[key] = {**SYSTEMS[base], "caps": merged, "role": "Declared in the imported inventory (not verified)"}
    return key, True


def _req(inv: dict, o: dict) -> dict:
    src = inv["source"]
    profile, _ = _profile_for(src)
    fields = {}
    for f in o["fields"]:
        fields[f["name"]] = {"type": str(f.get("type", "CHAR")).upper(), "length": f.get("length", 10), "decimals": f.get("decimals", 0),
                             "stated": {"type": "type" in f, "length": "length" in f, "decimals": "decimals" in f},
                             "custom": f.get("custom", False) is True, "key": f.get("key", False) is True,
                             "currency_ref": f.get("currency_ref"), "unit_ref": f.get("unit_ref"), "label": f.get("label", "")}
    keys = list(o.get("keys") or [n for n, f in fields.items() if f["key"]])
    return {"id": f"REQ-IMP-{o['name']}", "group": o["business_object"], "label": o.get("label", o["name"]), "system": profile,
            "object": f"{src.get('system_id', profile)}:{o['name']}", "object_type": o.get("obj_type", "CDS_VIEW"),
            "release_family": src["release_family"], "domain": o.get("domain", "UNKNOWN"), "fields": fields, "keys": keys, "grain": o.get("grain", "UNKNOWN"),
            "relationships": list(o.get("relationships") or []), "needs_delta": o.get("needs_delta", False) is True, "auth_objects": list(o.get("auth_objects") or []),
            "logic": list(o.get("logic") or []), "semantics": dict(o.get("semantics") or {}), "semantic_rule": None, "alt_sources": list(o.get("alt_sources") or []),
            "evidence": IMPORT_EVIDENCE}


def _catalog(doc: dict, example: bool = False) -> Catalog:
    prods = []
    for p in doc["products"]:
        ents = []
        for e in p["entities"]:
            ents.append({"entity": e["entity"], "covers_objects": list(e["covers"]),
                         "fields": {n: {"type": str(f.get("type", "CHAR")).upper(), "length": f.get("length", 10), "decimals": f.get("decimals", 0),
                                        "stated": {"type": "type" in f, "length": "length" in f, "decimals": "decimals" in f},
                                        "label": f.get("label", ""), "currency_ref": f.get("currency_ref"), "unit_ref": f.get("unit_ref")}
                                    for n, f in e["fields"].items()},
                         "keys": list(e.get("keys") or []), "grain": e.get("grain", "UNKNOWN"), "relationships": list(e.get("relationships") or []),
                         "delta": e.get("delta", False) is True, "auth_objects": list(e.get("auth_objects") or []),
                         "logic_supported": list(e.get("logic_supported") or []), "semantics": dict(e.get("semantics") or {})})
        ext = p.get("extension") or {}
        prods.append({"product_id": p["product_id"], "name": p.get("name", p["product_id"]), "version": p.get("version", "n/a"),
                      "source_application": p.get("source_application", "n/a"), "supported_releases": list(p.get("supported_releases") or list(PROFILE)),
                      "data_package": p.get("data_package", "n/a"), "entities": ents, "evidence": p.get("evidence", IMPORT_EVIDENCE) if example else IMPORT_EVIDENCE,
                      "domain": p.get("domain", "UNKNOWN"),
                      "extension": {"key_user": ext.get("key_user") is True, "developer": ext.get("developer") is True, "data_product_extension": ext.get("data_product_extension") is True},
                      "activation": p.get("activation", "UNKNOWN"), "entitlement": p.get("entitlement", "UNKNOWN"),
                      "installation": p.get("installation", "UNKNOWN"), "published_availability": "UNKNOWN", "tenant_availability": "UNKNOWN",
                      "technical_compatibility": "UNKNOWN", "consumption": "NOT_ATTEMPTED",
                      "source_reference_url": p.get("source_reference_url", ""), "last_verified": p.get("last_verified", doc.get("source", {}).get("captured_at", ""))})
    return Catalog({"products": prods, "domain_completeness": dict(doc.get("domain_completeness") or {})})


def fidelity(req: dict, entity: dict | None) -> list[dict]:
    """Fields the product carries but degraded: type narrower than the source, business name lost, currency or unit reference lost."""
    if not entity:
        return []
    out = []
    for n, f in req["fields"].items():
        p = entity["fields"].get(n)
        if p is None:
            continue
        why = []
        sf, pf = f.get("stated", {}), p.get("stated", {})
        narrower = ((sf.get("type") and pf.get("type") and p["type"] != f["type"])
                    or (sf.get("length") and pf.get("length") and p["length"] < f["length"])
                    or (sf.get("decimals") and pf.get("decimals") and p["decimals"] < f["decimals"]))
        if narrower:   # a size or type that either file does not state is unknown, never a finding
            why.append(f"type {f['type']}({f['length']},{f['decimals']}) in the source, {p['type']}({p['length']},{p['decimals']}) in the product")
        if f.get("label") and not p.get("label"):
            why.append(f"business name '{f['label']}' is empty in the product")
        if f.get("currency_ref") and not p.get("currency_ref"):
            why.append(f"currency reference {f['currency_ref']} not carried")
        if f.get("unit_ref") and not p.get("unit_ref"):
            why.append(f"unit reference {f['unit_ref']} not carried")
        if why:
            out.append({"field": n, "custom": f["custom"], "problems": why})
    return out


def run(inventory: dict, catalog_doc: dict, example: bool = False) -> dict:
    """Validate both files, run the delta engine, return the register. Never raises for bad input: returns errors instead."""
    try:
        return _run(inventory, catalog_doc, example)
    except RecursionError:
        return {"ok": False, "errors": ["the files are nested too deeply"], "rows": [], "summary": {}}
    except Exception:  # noqa: BLE001 - validation is the contract; anything that slips past it must still not take the page down
        return {"ok": False, "errors": ["the files could not be processed: check the schema and field types against the example files"], "rows": [], "summary": {}}


def _run(inventory: dict, catalog_doc: dict, example: bool) -> dict:
    if not isinstance(inventory, dict) or not isinstance(catalog_doc, dict):
        return {"ok": False, "errors": ["both files must be JSON objects"], "rows": [], "summary": {}}
    errs = validate_inventory(inventory) + validate_catalog(catalog_doc, example)
    if errs:
        return {"ok": False, "errors": errs, "rows": [], "summary": {}}
    try:
        cat = _catalog(catalog_doc, example)
    except CatalogError as e:
        return {"ok": False, "errors": [f"catalog: {e}"], "rows": [], "summary": {}}
    mode = "DEMO" if example else "IMPORT"
    rows = []
    for o in inventory["objects"]:
        req = _req(inventory, o)
        a = mapping.analyze(req, cat, mode)
        custom_names = {n for n, f in req["fields"].items() if f["custom"]}
        dtype, cust, notes = _classify(a, custom_names)
        cand = next((c for c in a["candidates"] if c["product"] == a.get("primary_product")), None)
        entity = None
        if cand:
            entity = next((e for p in cat.products.values() if p["product_id"] == cand["product"] for e in p["entities"] if e["entity"] == cand["entity"]), None)
        fid = fidelity(req, entity) if (cand and cat.usable(cat.products[cand["product"]], mode)) else []
        miss = set(a.get("missing_fields") or [])
        if dtype in ("FIELD_GAP_STANDARD", "NO_DELTA") and not miss and fid:
            dtype = "FIDELITY_LOSS"
        d = dec.decide(a, req, None)
        route = FIDELITY_ROUTE if dtype == "FIDELITY_LOSS" else (ROUTES.get(d["decision"], d["decision"]) +
                                                                  ("" if example else (" [capabilities as declared in your inventory file; not verified against your system]" if _profile_for(inventory["source"])[1]
                                                                                       else f" [capabilities assumed from the built-in {PROFILE[inventory['source']['release_family']]} profile, not read from your system]")))
        first = next((x for x in a["gaps"] if x["class"] != "NO_GAP"), None)
        cust_txt = ", ".join(f"{n} ({'not in the delivered product' if n in miss else 'covered by the product'})" for n in sorted(custom_names)) or "-"
        rows.append({"object": req["object"], "business_object": req["group"], "product": (f"{cand['product']} / {cand['entity']}" if cand else "none"),
                     "catalog_state": a["catalog_state"], "delta_type": dtype,
                     "delta": (("Extension degraded in the product" if all(x["custom"] for x in fid) else "Field degraded in the product") if dtype == "FIDELITY_LOSS" else DELTA_TYPES[dtype][0]),
                     "customization": cust_txt, "fidelity": [f"{x['field']}: " + "; ".join(x["problems"]) for x in fid], "notes": notes,
                     "how_found": (f"{first['dimension']} check: {_fmt(first['detail'])}" if first else "all assessed dimensions match the delivered entity"),
                     "coverage": f"{a['coverage']['numerator']}/{a['coverage']['denominator']}", "route": route,
                     "next_step": (d.get("implementation_steps") or [d.get("reason", "-")])[0] if dtype != "FIDELITY_LOSS" else FIDELITY_ROUTE,
                     "approvals": ([] if dtype == "FIDELITY_LOSS" else d.get("approvals", [])), "evidence": "SYNTHETIC EXAMPLE" if example else IMPORT_EVIDENCE})
    by = {}
    for r in rows:
        by[r["delta_type"]] = by.get(r["delta_type"], 0) + 1
    return {"ok": True, "errors": [], "rows": rows, "mode": mode,
            "summary": {"objects": len(rows), "by_delta_type": by, "with_customization": sum(1 for r in rows if r["customization"] != "-"),
                        "with_fidelity_findings": sum(1 for r in rows if r["fidelity"])},
            "note": ("Example files are synthetic and illustrate the format." if example else
                     "Results rest only on the two files you supplied (CUSTOMER_PROVIDED). Catalog completeness is UNKNOWN unless the file declares it; "
                     "nothing was read from or written to any SAP system.")}


# ---- synthetic example files that document the format -----------------------------------------------------------------------------
EXAMPLE_INVENTORY = {
    "schema": INVENTORY_SCHEMA, "evidence": IMPORT_EVIDENCE,
    "source": {"system_id": "SIM_S4", "client": "100", "release_family": "S4_2023", "collector": "synthetic example", "collected_at": "2026-11-28T00:00:00Z"},
    "objects": [
        {"name": "SIM_PO_ITEM", "business_object": "PO_ITEM", "obj_type": "CDS_COMPOSITE_VIEW", "domain": "PROCUREMENT", "keys": ["EBELN", "EBELP"],
         "grain": "PO item", "relationships": ["SUPPLIER"], "needs_delta": True,
         "fields": [{"name": "EBELN", "type": "CHAR", "length": 10, "key": True, "label": "Purchase order"},
                    {"name": "EBELP", "type": "NUMC", "length": 5, "key": True, "label": "Item"},
                    {"name": "NETWR", "type": "CURR", "length": 13, "decimals": 2, "currency_ref": "WAERS", "label": "Net value"},
                    {"name": "WAERS", "type": "CUKY", "length": 5},
                    {"name": "ZZ_SAFETY_CLASS", "type": "CHAR", "length": 2, "custom": True, "label": "Safety class"},
                    {"name": "ZZ_NET_ADJ", "type": "CURR", "length": 13, "decimals": 2, "custom": True, "currency_ref": "WAERS", "label": "Adjusted net value"}]},
        {"name": "SIM_PR_ITEM", "business_object": "PR_ITEM", "obj_type": "CDS_COMPOSITE_VIEW", "domain": "PROCUREMENT", "keys": ["BANFN", "BNFPO"],
         "grain": "PR item", "relationships": [], "needs_delta": True,
         "fields": [{"name": "BANFN", "type": "CHAR", "length": 10, "key": True, "label": "Requisition"},
                    {"name": "BNFPO", "type": "NUMC", "length": 5, "key": True, "label": "Item"},
                    {"name": "MENGE", "type": "QUAN", "length": 13, "decimals": 3, "unit_ref": "MEINS", "label": "Quantity"},
                    {"name": "MEINS", "type": "UNIT", "length": 3},
                    {"name": "ZZ_PRIORITY", "type": "CHAR", "length": 1, "custom": True, "label": "Priority"}]},
        {"name": "SIM_Z_QUALITY_NOTE", "business_object": "QUALITY_NOTE", "obj_type": "CDS_CUSTOM_VIEW", "domain": "QUALITY", "keys": ["QNNUM"],
         "grain": "Quality note", "relationships": [], "needs_delta": False,
         "fields": [{"name": "QNNUM", "type": "CHAR", "length": 12, "key": True}, {"name": "QNTXT", "type": "CHAR", "length": 40}]}]}
EXAMPLE_CATALOG = {
    "schema": CATALOG_SCHEMA, "source": {"kind": "synthetic example of a cockpit export", "captured_at": "2026-11-28T00:00:00Z"},
    "domain_completeness": {"PROCUREMENT": True},
    "products": [
        {"product_id": "SIM_DP_PO", "name": "Purchase order (synthetic)", "evidence": "SYNTHETIC_FIXTURE", "domain": "PROCUREMENT", "supported_releases": ["S4_2023"],
         "entitlement": "ENTITLED", "activation": "ACTIVATED", "installation": "INSTALLED", "extension": {"key_user": True, "developer": True},
         "source_reference_url": "SYNTHETIC_FIXTURE_NO_URL",
         "entities": [{"entity": "po_item", "covers": ["PO_ITEM"], "keys": ["EBELN", "EBELP"], "grain": "PO item", "relationships": ["SUPPLIER"], "delta": True,
                       "fields": {"EBELN": {"type": "CHAR", "length": 10, "label": "Purchase order"}, "EBELP": {"type": "NUMC", "length": 5, "label": "Item"},
                                  "NETWR": {"type": "CURR", "length": 13, "decimals": 2, "currency_ref": "WAERS", "label": "Net value"},
                                  "WAERS": {"type": "CUKY", "length": 5},
                                  "ZZ_NET_ADJ": {"type": "CHAR", "length": 128, "label": ""}}}]},
        {"product_id": "SIM_DP_PR", "name": "Purchase requisition (synthetic)", "evidence": "SYNTHETIC_FIXTURE", "domain": "PROCUREMENT", "supported_releases": ["S4_2023"],
         "entitlement": "ENTITLED", "activation": "ACTIVATED", "installation": "INSTALLED", "extension": {"key_user": True},
         "source_reference_url": "SYNTHETIC_FIXTURE_NO_URL",
         "entities": [{"entity": "pr_item", "covers": ["PR_ITEM"], "keys": ["BANFN", "BNFPO"], "grain": "PR item", "relationships": [], "delta": True,
                       "fields": {"BANFN": {"type": "CHAR", "length": 10, "label": "Requisition"}, "BNFPO": {"type": "NUMC", "length": 5, "label": "Item"},
                                  "MENGE": {"type": "QUAN", "length": 13, "decimals": 3, "unit_ref": "MEINS", "label": "Quantity"},
                                  "MEINS": {"type": "UNIT", "length": 3},
                                  "ZZ_PRIORITY": {"type": "CHAR", "length": 128, "label": ""}}}]}]}
