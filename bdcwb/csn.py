"""Read an Effective CSN Interop file (the format SAP uses to describe a data product's entities) and turn it into a bdc-delta-catalog/1 product.

Format source: the public CSN Interop specification, https://sap.github.io/csn-interop-specification/ (Effective flavour, csnInteropEffective 1.0 to 1.2,
$version 2.0). This reader follows the parts of the specification that were read for it; it has NOT been run against a real SAP data-product file yet,
because none has been supplied. Until then treat it as a tested reader of the published format.

Rules:
- A CSN file says nothing about which customer objects an entity covers. That mapping is supplied by the caller (`covers`), never guessed.
  `suggest_covers` only proposes candidates from shared key names, for a person to confirm.
- Only what the file states is carried over (a length or scale that is absent stays absent), so the comparison treats it as unknown, not as a difference.
- Imported catalogs are CUSTOMER_PROVIDED and never upgraded (the importer enforces it). Nothing here contacts SAP.
- Names: SAP data-product elements use CDS names (CamelCase). A customer inventory compared with them must list CDS view elements, not ABAP table fields.
"""
from __future__ import annotations

from . import importer

SUPPORTED_CSN = {"1.0", "1.1", "1.2"}
_INT = {"cds.Integer": 10, "cds.Int16": 5, "cds.Integer64": 19, "cds.UInt8": 3}
_SIMPLE = {"cds.Date": "DATS", "cds.Time": "TIMS", "cds.DateTime": "TIMESTAMP", "cds.Timestamp": "TIMESTAMP", "cds.Boolean": "BOOL", "cds.UUID": "UUID",
           "cds.Double": "FLTP", "cds.Binary": "RAW", "cds.LargeBinary": "RAW", "cds.LargeString": "STRING"}
LABEL = "@EndUserText.label"
CURRENCY_OF = "@Semantics.amount.currencyCode"
UNIT_OF = "@Semantics.quantity.unitOfMeasure"


def validate(doc) -> list[str]:
    """Structural checks from the specification's mandatory properties; consumers must ignore unknown properties, so those are not errors."""
    if not isinstance(doc, dict):
        return ["csn: the file must be a JSON object"]
    errs = []
    if doc.get("csnInteropEffective") not in SUPPORTED_CSN:
        errs.append(f"csn: csnInteropEffective must be one of {sorted(SUPPORTED_CSN)}")
    if doc.get("$version") != "2.0":
        errs.append("csn: $version must be '2.0'")
    defs = doc.get("definitions")
    if not isinstance(defs, dict) or not defs:
        return errs + ["csn: 'definitions' must be a non-empty object"]
    n_ent = 0
    for name, d in defs.items():
        if not isinstance(d, dict) or d.get("kind") not in ("entity", "type", "context", "service"):
            errs.append(f"csn: definition {str(name)[:60]!r} needs a kind of entity, type, context or service")
            continue
        if d["kind"] == "entity":
            n_ent += 1
            els = d.get("elements")
            if not isinstance(els, dict) or not els:
                errs.append(f"csn: entity {str(name)[:60]!r} needs at least one element")
            elif len(els) > importer.LIMITS["max_fields_per_entity"]:
                errs.append(f"csn: entity {str(name)[:60]!r} has more than {importer.LIMITS['max_fields_per_entity']} elements")
            else:
                for en, e in els.items():
                    if not isinstance(e, dict) or not isinstance(e.get("type"), str):
                        errs.append(f"csn: element {str(name)[:40]}.{str(en)[:40]} needs a text 'type'")
                        break
    if n_ent == 0:
        errs.append("csn: no entity definition found")
    if n_ent > importer.LIMITS["max_entities_per_product"]:
        errs.append(f"csn: more than {importer.LIMITS['max_entities_per_product']} entities")
    return errs


def _resolve(el: dict, defs: dict) -> dict:
    """Merge a custom type definition into the element (the element's own properties win)."""
    t = el.get("type", "")
    if isinstance(t, str) and not t.startswith("cds.") and isinstance(defs.get(t), dict) and defs[t].get("kind") == "type":
        base = {k: v for k, v in defs[t].items() if k != "kind"}
        return {**base, **{k: v for k, v in el.items() if k != "type"}} | {"type": base.get("type", t)}
    return el


def _ref(v):
    return v.get("=") if isinstance(v, dict) else None


def _field(el: dict, defs: dict) -> dict:
    el = _resolve(el, defs)
    t = el.get("type", "")
    f: dict = {}
    if t == "cds.String":
        f["type"] = "CUKY" if el.get("@Semantics.currencyCode") is True else "UNIT" if el.get("@Semantics.unitOfMeasure") is True else "CHAR"
        if "length" in el:
            f["length"] = el["length"]
    elif t == "cds.Decimal":
        cur, unit = _ref(el.get(CURRENCY_OF)), _ref(el.get(UNIT_OF))
        f["type"] = "CURR" if cur else "QUAN" if unit else "DEC"
        if "precision" in el:
            f["length"] = el["precision"]
        if isinstance(el.get("scale"), int):       # scale 'floating' is not a number of decimals: left unstated
            f["decimals"] = el["scale"]
        if cur:
            f["currency_ref"] = cur
        if unit:
            f["unit_ref"] = unit
    elif t in _INT:
        f["type"] = "INT4"
        f["length"] = _INT[t]
    elif t in _SIMPLE:
        f["type"] = _SIMPLE[t]
    else:
        f["type"] = "CHAR"                           # an unknown or custom type that did not resolve: type stated as text, no size
    if isinstance(el.get(LABEL), str):
        f["label"] = el[LABEL]
    return f


def entities(doc: dict) -> dict:
    """name -> {fields, keys, relationships}, from a validated Effective CSN."""
    defs = doc["definitions"]
    out = {}
    for name, d in defs.items():
        if d.get("kind") != "entity":
            continue
        fields, keys, rel = {}, [], []
        for en, e in d["elements"].items():
            if e.get("type") in ("cds.Association", "cds.Composition"):
                tgt = e.get("target")
                if isinstance(tgt, str):
                    rel.append(tgt.split(".")[-1])
                continue
            fields[en] = _field(e, defs)
            if e.get("key") is True:
                keys.append(en)
        out[name] = {"fields": fields, "keys": keys, "relationships": rel}
    return out


def to_product(doc: dict, product_id: str, name: str, covers: dict, *, version: str = "n/a", domain: str = "UNKNOWN", releases=None,
               extension: dict | None = None, source_reference: str = "", activation: str = "UNKNOWN", entitlement: str = "UNKNOWN",
               installation: str = "UNKNOWN", entity_info: dict | None = None) -> dict:
    """One bdc-delta-catalog/1 product.

    `covers` maps an entity name to the customer business objects it covers; an entity not in `covers` covers nothing.
    A CSN file does not state availability (activation, entitlement, installation), the grain of an entity or whether it supports delta extraction.
    Supply them from the cockpit export when known (`activation` etc., and `entity_info={"Entity": {"grain": "...", "delta": True}}`); left unknown,
    the delta engine reports the product as not available and the structure as differing, which means 'not established', not 'SAP delivers nothing'.
    """
    info = entity_info or {}
    ents = []
    for ename, e in entities(doc).items():
        short = ename.split(".")[-1]
        extra = info.get(ename) or info.get(short) or {}
        ent = {"entity": short, "covers": list(covers.get(ename, covers.get(short, []))), "fields": e["fields"], "keys": e["keys"], "relationships": e["relationships"]}
        if isinstance(extra.get("grain"), str):
            ent["grain"] = extra["grain"]
        if isinstance(extra.get("delta"), bool):
            ent["delta"] = extra["delta"]
        ents.append(ent)
    return {"product_id": product_id, "name": name, "version": version, "domain": domain, "evidence": importer.IMPORT_EVIDENCE, "supported_releases": list(releases or importer.PROFILE),
            "extension": extension or {}, "source_reference_url": source_reference, "activation": activation, "entitlement": entitlement, "installation": installation,
            "entities": ents}


def catalog(products: list, source: str = "converted from an SAP CSN Interop (Effective) file", completeness: dict | None = None) -> dict:
    return {"schema": importer.CATALOG_SCHEMA, "source": {"kind": source}, "domain_completeness": dict(completeness or {}), "products": products}


def suggest_covers(doc: dict, inventory: dict) -> dict:
    """Candidates only: inventory business objects that share at least one key element name with an entity. A person must confirm before use."""
    ents = entities(doc)
    out: dict = {}
    for o in (inventory.get("objects") or []):
        okeys = {k for k in (o.get("keys") or []) if isinstance(k, str)} or {f["name"] for f in o.get("fields", []) if f.get("key") is True}
        for ename, e in ents.items():
            shared = okeys & set(e["keys"])
            if shared and isinstance(o.get("business_object"), str):
                out.setdefault(ename, [])
                if o["business_object"] not in out[ename]:
                    out[ename].append(o["business_object"])
    return out


def compare(inventory: dict, csn_doc: dict, product_id: str, name: str, covers: dict, **meta) -> dict:
    """Validate the CSN, build the catalog and run the same delta engine as the file import. Never raises for bad input."""
    errs = validate(csn_doc)
    if errs:
        return {"ok": False, "errors": errs, "rows": [], "summary": {}}
    cat = catalog([to_product(csn_doc, product_id, name, covers, **meta)])
    return importer.run(inventory, cat)
