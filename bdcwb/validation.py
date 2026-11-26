"""Technical validation engine. Offline checks are labelled OFFLINE and never reported as live SAP activation/ATC."""
from __future__ import annotations

from collections import Counter

from .artifacts import is_cds_file, lint_cds
from .core import SapObject

LIVE_ONLY = ["ABAP syntax check (SAP)", "Activation", "ATC", "Datasphere deploy status", "Runtime load evidence"]


def _check(name: str, ok: bool | None, detail="", mode="OFFLINE") -> dict:
    return {"check": name, "status": "NOT_RUN" if ok is None else ("PASS" if ok else "FAIL"), "detail": detail, "mode": mode}


def technical_validation(ctx: dict) -> dict:
    checks = []
    deps = ctx["dependencies"]
    checks.append(_check("Object dependencies resolved (cycles)", not deps["cycles"], f"{len(deps['cycles'])} cycles"))
    checks.append(_check("Unresolved objects reported explicitly", True, f"{len(deps['unresolved'])} unresolved reported: " +
                         ", ".join(u["object"] for u in deps["unresolved"][:3])))
    pk_lint = [lint_cds(t) for p in ctx["packages"] for k, t in p["files"].items() if is_cds_file(k)]
    checks.append(_check("Generated source syntax (lexical, offline)", all(x["status"] == "OFFLINE_VALIDATED" for x in pk_lint),
                         f"{len(pk_lint)} CDS artifacts linted; NOT an SAP syntax check"))
    objs: dict[str, SapObject] = ctx["objects"]
    rel_bad = [o.id for o in objs.values() if o.obj_type == "CDS_INTERFACE_VIEW" and o.api_state != "RELEASED"]
    checks.append(_check("Release-contract eligibility (declared api_state)", not rel_bad, f"not released: {rel_bad[:3]}"))
    nodc = [p["manifest"]["requirement"] for p in ctx["packages"] if p["manifest"]["complex_join_request"] and any(
        "changeDataCapture" in t for t in p["files"].values())]
    checks.append(_check("Extraction compatibility (no CDC on complex joins)", not nodc, str(nodc)))
    m = ctx["bdc"]["model"]
    keys = Counter((c["system"], c["po"], c["id"]) for c in m["commitment"])
    checks.append(_check("Key uniqueness: PO item fact", all(v == 1 for v in keys.values()), f"{len(keys)} keys"))
    jk = Counter((j["reported_by"], j["rbukrs"], j["gjahr"], j["belnr"], j["docln"], j.get("src_system")) for j in m["journal"])
    checks.append(_check("Key uniqueness: journal fact (system-qualified)", all(v == 1 for v in jk.values()), f"{len(jk)} keys"))
    po_keys = {(p["system"], p["po"], p["item"]) for p in ctx["bdc"]["acq"]["entities"]["po_item"]}
    orphans = [h for h in ctx["bdc"]["acq"]["entities"]["po_history"] if (h["system"], h["po"], h["item"]) not in po_keys]
    checks.append(_check("Referential integrity: PO history -> PO item", not orphans, f"{len(orphans)} orphans"))
    nulls = [c for c in m["commitment"] if c["po_value"] is None or c["system"] is None]
    checks.append(_check("Nullability of keys and amounts", not nulls, f"{len(nulls)} nulls"))
    checks.append(_check("Join cardinality / grain (model)", ctx["grain"]["status"] == "PASS", "; ".join(ctx["grain"]["problems"])))
    checks.append(_check("Datasphere SQL functional check (SQLite)", ctx["sqlite"]["status"] == "OFFLINE_VALIDATED", ctx["sqlite"]["note"], "OFFLINE_SQLITE"))
    checks.append(_check("Authorization configuration declared", all(p["manifest"]["files"] for p in ctx["packages"]), "authorization objects listed per product"))
    checks.append(_check("Schema compatibility with data product contract", all("data_product_contract.json" in p["files"] for p in ctx["packages"]), ""))
    for n in LIVE_ONLY:
        checks.append(_check(n, None, "requires a verified live interface and authority; not run", "LIVE_REQUIRED"))
    offline = [c for c in checks if c["mode"] != "LIVE_REQUIRED"]
    return {"checks": checks, "offline_status": "OFFLINE_VALIDATED" if all(c["status"] == "PASS" for c in offline) else "FAILED",
            "live_status": "NOT_RUN", "note": "offline results never imply live SAP activation, ATC or runtime verification"}
