"""SAP-published data product catalog (a read-only snapshot) and its link to the synthetic delta register.

The snapshot holds what SAP's public hub states for each product: name, id, version, process tags, S/4HANA editions, the S/4 and ODM business
objects and the responsible component. It does NOT hold field lists, CDS views or tenant state, so a comparison with backend standard is made
at product / business-object level only. Everything here is evidence class PUBLIC_SAP_CATALOG_SNAPSHOT: published by SAP, not verified in any tenant.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import lookup

SNAPSHOT = Path(__file__).resolve().parents[1] / "data" / "public_demo" / "sap_hub_finance_SNAPSHOT.json"
BADGE = "SAP-PUBLISHED CATALOG SNAPSHOT (READ 2026-11-28) - NOT TENANT-VERIFIED"
CDS_NOTE = ("CDS views are matched to the product by name (I_<S/4 object>, optionally with an API suffix); SAP does not publish which view feeds a data product. "
            "The release state is SAP's state for ABAP Cloud (clean-core) use per edition, not a statement that the view is extraction-enabled or activated in a tenant.")
PROCESS_TAGS = ["Record to Report", "Procure to Pay", "Hire to Retire"]          # the only process tags SAP puts on Finance products
HUB_TAG_FOR = {"P2P": "Procure to Pay", "R2R": "Record to Report"}              # our taxonomy id -> SAP's process tag (others have no equivalent tag)

# Our synthetic object groups -> SAP-published products that carry that object. A group with no entry has no product in the snapshot.
GROUP_TO_HUB = {
    "PR": ["Purchase Requisition"], "PRACC": ["Purchase Requisition"], "POH": ["Purchase Order"], "POI": ["Purchase Order"], "POACC": ["Purchase Order"],
    "POHIST": ["Purchase Order"], "POSCH": ["Purchase Scheduling Agreement"], "INVH": ["Supplier Invoice"], "INVI": ["Supplier Invoice"],
    "BKPF": ["Journal Entry Header"], "BSEG": ["Entry View Journal Entry"], "ACDOCA": ["Journal Entry Header", "Entry View Journal Entry"],
    "BP": ["Customer", "Supplier"], "MAT": ["Product"], "GL": ["General Ledger Account"], "CC": ["Cost Center"],
}
# Our synthetic catalog products -> the SAP-published product(s) they stand in for. Matched by name by this build, not by SAP.
SIM_EQUIV = {
    "SIM_DP_PURCHASE_REQUISITION": ["Purchase Requisition"], "SIM_DP_PURCHASE_ORDER": ["Purchase Order"], "SIM_DP_SUPPLIER_INVOICE": ["Supplier Invoice"],
    "SIM_DP_JOURNAL_ENTRY": ["Journal Entry Header", "Entry View Journal Entry"], "SIM_DP_BUSINESS_PARTNER": ["Customer", "Supplier"], "SIM_DP_PRODUCT": ["Product"],
}


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def products(finance_only: bool = False) -> list[dict]:
    return [p for p in load()["products"] if p["finance_tagged"] or not finance_only]


def by_name(name: str) -> dict | None:
    return next((p for p in load()["products"] if p["name"].lower() == (name or "").lower()), None)


def area(p: dict) -> str:
    """Responsible component reduced to its application area, e.g. FI-GL-IS -> FI-GL, FIN-CS-MD -> FIN-CS."""
    return "-".join(p["component"].split("-")[:2]) or "-"


def areas() -> list[str]:
    return sorted({area(p) for p in products()})


def stats() -> dict:
    fin = products(True)
    tags = {t: sum(1 for p in fin if t in p["processes"]) for t in PROCESS_TAGS}
    return {"hub_total": load()["hub_total_products"], "finance": len(fin), "adjacent": len(products()) - len(fin), "process_tags": tags,
            "untagged": sum(1 for p in fin if not p["processes"]), "business_object_products": sum(1 for p in fin if p["category"] == "business-object"),
            "with_s4_object": sum(1 for p in fin if p["s4_objects"]), "with_cds_view": sum(1 for p in fin if p.get("cds_views")),
            "cds_not_released_somewhere": sum(1 for p in fin if any(v["cloud_erp"] != "released" or v["private_edition"] != "released" for v in p.get("cds_views", []))), "components": len({p["component"] for p in fin})}


def browse(process: str = "", area_: str = "", text: str = "", include_adjacent: bool = False) -> list[dict]:
    t = re.sub(r"\s+", " ", (text or "").lower()).strip()
    out = []
    for p in products(not include_adjacent):
        if process == "(no process tag)":
            if p["processes"]:
                continue
        elif process and process != "All" and process not in p["processes"]:
            continue
        if area_ and area_ != "All" and area(p) != area_:
            continue
        if t and t not in (p["name"] + " " + p["id"] + " " + p["component"] + " " + " ".join(p["s4_objects"] + p["odm_objects"])).lower():
            continue
        out.append(p)
    return out


def for_process(pid: str) -> dict:
    """What SAP publishes for one of our taxonomy processes: tagged products (where SAP has an equivalent tag) and, step by step, the products that carry our objects."""
    tag = HUB_TAG_FOR.get(pid)
    proc = lookup.PROCESSES[pid]
    tagged = [p for p in products(True) if tag and tag in p["processes"]]
    steps = []
    for step, groups in proc["steps"]:
        names = sorted({n for g in groups for n in GROUP_TO_HUB.get(g, [])})
        steps.append({"step": step, "products": [by_name(n) for n in names if by_name(n)], "published": bool(names)})
    return {"process": pid, "name": proc["name"], "tag": tag, "tagged": tagged, "steps": steps,
            "note": (f"SAP tags {len(tagged)} Finance products with the process '{tag}'." if tag else
                     "SAP's Finance products carry only the tags " + ", ".join(PROCESS_TAGS) + "; none is equivalent to this process, so it is read from the objects each step uses."),
            "unpublished_steps": [s["step"] for s in steps if not s["published"]]}


def equivalents(sim_id: str) -> dict:
    names = SIM_EQUIV.get(sim_id, [])
    ps = [by_name(n) for n in names if by_name(n)]
    return {"product_id": sim_id, "products": ps,
            "processes": sorted({t for p in ps for t in p["processes"]}),
            "note": ("Matched by name by this build. " if ps else "No product with this scope is in the SAP-published snapshot (Finance list plus the adjacent products). ")}


def detail(res: dict, scn: str, name: str) -> dict:
    """One SAP-published product, and the objects of the synthetic delta register that map to it: the comparison with backend standard."""
    p = by_name(name)
    if not p:
        return {"found": False, "name": name}
    groups = sorted(g for g, ns in GROUP_TO_HUB.items() if p["name"] in ns)
    rows_by_group = lookup._group_rows(res["scenarios"][scn])
    rows = [{"object": lookup._grain(g), "system": r["system"], "sap_object": r["sap_object"], "our product": r["product"], "delta": r["delta_type"],
             "solution": r["route"], "customization": r["kind"] == "Customization"} for g in groups for r in rows_by_group.get(g, [])]
    return {"found": True, "product": p, "groups": groups, "rows": rows, "cds_views": p.get("cds_views", []),
            "summary": (f"{p['name']} v{p['version']} ({p['ord_id']}) is published by SAP for " + ", ".join(p["editions"]) + ". Backend standard anchor: " +
                        (", ".join(p["s4_objects"]) or "none stated") + "." +
                        (f" {len(rows)} object(s) in the scenario map to it; {sum(1 for r in rows if r['delta'] != 'NO_DELTA')} differ." if rows else
                         " No object in the synthetic scenario maps to it.") + " " + BADGE + ".")}
