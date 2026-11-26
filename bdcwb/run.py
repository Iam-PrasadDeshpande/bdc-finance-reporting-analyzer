"""End-to-end synthetic pipeline: discovery -> catalog -> mapping -> decisions -> artifacts -> model -> validation -> recon -> gates.

`run_all()` returns one JSON-serialisable result set. Every dashboard figure, agent answer and gate derives from it.
CLI:  python -m bdcwb.run --out <dir>   (persists results.json and a markdown summary; DEMO mode only)
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from . import artifacts as ar
from . import bdc as bdcmod
from . import catalog as catmod
from . import decision as dec
from . import dsp_model as dsp
from . import execution as ex
from . import mapping as mp
from . import recon as rc
from . import rules as rl
from . import scenarios as sc
from . import status as st
from . import synthetic as syn
from . import validation as val
from .core import VERSION, resolve_dependencies

DEFECT_LEVEL_SCOPE = {"A": ("LATE_ARRIVING_CHANGE", "AMOUNT_TAMPER", "DROPPED_INVOICE", "DUPLICATED_JOURNAL_LINE", "WRONG_CURRENCY"),
                      "B": bdcmod.DEFECTS}


def _levels(world, scenario, out, rb):
    l1 = rc.level1(world, out["acq"])
    l2 = rc.level2(out["acq"], out["model"], scenario)
    l3 = rc.level3(world, out, scenario, rb)
    b1 = rc.source_to_cfin(world, out["acq"], scenario, rb) if scenario == "B" else None
    return l1, l2, l3, b1


def _defect_matrix(world, scenario, rb):
    rows = []
    for d in DEFECT_LEVEL_SCOPE[scenario]:
        out = bdcmod.run_bdc(world, scenario, (d,))
        l1, l2, l3, b1 = _levels(world, scenario, out, rb)
        det = [n for n, r in (("L1", l1), ("L2", l2), ("L3", l3), ("B1", b1)) if r and r["status"] not in ("SYNTHETIC_PASS",)]
        rows.append({"defect": d, "detected": bool(det), "detected_by": det, "applied": out["acq"]["applied_defects"] + out["model"]["model_defects"],
                     "l3_differences": len(l3["differences"])})
    return rows


def _unsupported_demos(objects, an):
    out = []
    req = copy.deepcopy(next(a["req"] for a in an if a["req"]["group"] == "INVI"))
    req["unsupported_request"] = "automatic CDC annotation requested for a complex join"
    a = next(a["analysis"] for a in an if a["req"]["group"] == "INVI")
    out.append({"case": "CDC annotation on a complex join", "decision": dec.decide(a, req)["decision"]})
    poi = next(x for x in an if x["req"]["group"] == "POI")
    # Key-user extension requested for a non-eligible field (amount with currency reference) must not be offered.
    r2 = copy.deepcopy(poi["req"])
    r2["fields"]["ZZ_NET_AMOUNT"] = {"type": "CURR", "length": 13, "decimals": 2, "custom": True, "key": False}
    a2 = copy.deepcopy(poi["analysis"])
    a2["missing_fields"] = ["ZZ_NET_AMOUNT"]
    d2 = dec.decide(a2, r2)
    out.append({"case": "Key-user extension for an amount field (not eligible)", "decision": d2["decision"],
                "expected_not": "KEY_USER_EXTENSION"})
    saved = sc.SYSTEMS["BW401"]["caps"]["dpg_eligibility"]["deployment_ok"]
    try:
        sc.SYSTEMS["BW401"]["caps"]["dpg_eligibility"]["deployment_ok"] = False
        out.append({"case": "BW Data Product Generator on an ineligible deployment", "decision": dec.decide(_bw_analysis(), _bw_req())["decision"]})
    finally:
        sc.SYSTEMS["BW401"]["caps"]["dpg_eligibility"]["deployment_ok"] = saved
    return out


def _bw_req():
    return {"id": "REQ-BW401-GRIR", "group": "BW", "label": "BW GR/IR ADSO", "system": "BW401", "object": "BW401:SIM_ADSO_GRIR",
            "fields": {}, "keys": [], "grain": "G/L balance per period", "relationships": [], "needs_delta": True, "auth_objects": [],
            "logic": [], "semantics": {}, "alt_sources": [], "domain": "FINANCE"}


def _bw_analysis():
    return {"requirement": "REQ-BW401-GRIR", "gaps": [{"class": "PRODUCT_NOT_AVAILABLE", "dimension": "Business entity",
                                                         "detail": "existing BW provider has no SAP-managed product", "items": []}],
            "coverage": {"numerator": 0, "denominator": 0, "unassessed": [], "percent": None}, "catalog_state": "NOT_FOUND_COMPLETE",
            "candidates": [], "missing_fields": [], "affected_products": []}


def run_scenario(scenario: str, seed: int, n_po: dict | None = None) -> dict:
    cfg = sc.SCENARIOS[scenario]
    objects = sc.all_objects(scenario)
    deps = resolve_dependencies(objects, cfg["reporting_roots"])
    cat = catmod.Catalog(sc.catalog_fixture())
    rb0 = rl.default_rulebook(resolved=False)
    an = mp.analyze_scenario(cfg, objects, cat, "DEMO")
    dec_before = dec.decide_all(an, rb0)
    ai_refused = False
    try:
        rb0.approve("R-CLEARING-ALLOC-001", "Claude")
    except rl.RuleError:
        ai_refused = True
    world = syn.generate(scenario, seed, n_po)
    out0 = bdcmod.run_bdc(world, scenario)
    l3_before = rc.level3(world, out0, scenario, rb0)
    rb = rl.default_rulebook(resolved=True)
    decisions = dec.decide_all(an, rb)
    if scenario == "B":
        bw = dec.decide(_bw_analysis(), _bw_req())
        decisions.append(bw)
    out = bdcmod.run_bdc(world, scenario)
    l1, l2, l3, b1 = _levels(world, scenario, out, rb)
    gold_world = syn.generate("A", seed, {"S4A": 1})
    gold_out = bdcmod.run_bdc(gold_world, "A")
    golden = rc.golden_check(gold_out, rc.reference_measures(gold_world, "A"))
    naive = rc.naive_double_count_demo(world, scenario, rb) if scenario == "B" else None
    reqs = {a["req"]["id"]: a["req"] for a in an}
    reqs["REQ-BW401-GRIR"] = _bw_req()
    packages = []
    for d in decisions:
        if d["decision"] in ("CREATE_CUSTOMER_MANAGED_PRODUCT", "BW_DATA_PRODUCT_ROUTE"):
            packages.append(ar.generate_package(d, reqs[d["requirement"]], objects))
    model = dsp.build_model(scenario, decisions)
    grain = dsp.validate_grain(model)
    sql = dsp.sqlite_functional_check(out["acq"], out["measures"])
    tv = val.technical_validation({"dependencies": deps, "packages": packages, "objects": objects, "bdc": out, "grain": grain, "sqlite": sql})
    bw_cmp = rc.bw_vs_bdc(world, out, rb) if scenario == "B" else None
    matrix = _defect_matrix(world, scenario, rb)
    unsupported = _unsupported_demos(objects, an)
    facts = {"objects": len(objects), "catalog_ok": True, "packages": len(packages),
             "lint_ok": all(ar.lint_cds(t)["status"] == "OFFLINE_VALIDATED" for p in packages for k, t in p["files"].items() if ar.is_cds_file(k)),
             "model_ok": grain["status"] == "PASS" and sql["status"] == "OFFLINE_VALIDATED", "recon_ran": True, "systems": cfg["systems"]}
    audit = ex.AuditLog()
    plan = {m: ex.build_plan(m, facts, None, {}, audit) for m in ("DEMO", "CONNECTED_READ_ONLY", "CONTROLLED_EXECUTION")}
    covsum = mp.coverage_summary(an)
    levels = {"L1": l1, "L2": l2, "L3": l3, "B1": b1, "B4": bw_cmp}
    overall = "SYNTHETIC_PASS" if all(v["status"] == "SYNTHETIC_PASS" for v in levels.values() if v) else "FAIL"
    cnt = lambda key: sum(1 for d in decisions if d["decision"] == key)  # noqa: E731
    metrics = {"source_systems": len(cfg["sources"]), "landscape_systems": len(cfg["systems"]), "discovered_objects": len(objects),
               "dependent_objects": len(deps["nodes"]) - len(deps["roots"]), "assessed_requirements": len(an),
               "verified_sap_managed_products": sum(1 for p in cat.products.values() if p["evidence"] in ("PUBLISHED_VERIFIED", "TENANT_VERIFIED", "CUSTOMER_PROVIDED")),
               "synthetic_fixture_products": sum(1 for p in cat.products.values() if p["evidence"] == "SYNTHETIC_FIXTURE"),
               "unverified_product_candidates": sum(1 for p in cat.products.values() if p["evidence"] == "CANDIDATE_UNVERIFIED"),
               "reusable_products": cnt("REUSE_STANDARD"), "required_extensions": cnt("KEY_USER_EXTENSION") + cnt("DEVELOPER_EXTENSION") + cnt("DATA_PRODUCT_EXTENSION"),
               "proposed_customer_managed_products": cnt("CREATE_CUSTOMER_MANAGED_PRODUCT") + cnt("BW_DATA_PRODUCT_ROUTE"),
               "unresolved_business_rules_before": len(rb0.unresolved()), "unresolved_business_rules_after": len(rb.unresolved()),
               "generated_artifacts": sum(len(p["files"]) for p in packages), "executed_artifacts": 0,
               "technical_validation": tv["offline_status"], "finance_reconciliation": overall,
               "po_count": len({(p["system"], p["po"]) for p in out["acq"]["entities"]["po_item"]}),
               "journal_lines": len(out["model"]["journal"])}
    return {"scenario": scenario, "name": cfg["name"], "evidence_mode": "SYNTHETIC", "mode": "DEMO", "seed": seed,
            "topology": {"systems": {k: {kk: vv for kk, vv in sc.SYSTEMS[k].items() if kk in ("type", "release", "client", "role", "optional")}
                                     for k in cfg["systems"]}, "sources": cfg["sources"], "fi_authority": {f"{a}|{b}": c for (a, b), c in cfg.get("fi_authority", {}).items()}},
            "inventory": sc.inventory(), "objects": [o.to_dict() for o in objects.values()], "dependencies": deps,
            "catalog": {"snapshot": cat.snapshot["snapshot_id"], "products": [{k: v for k, v in p.items() if k != "entities"} | {"entities": [e["entity"] for e in p["entities"]]}
                                                                              for p in cat.products.values()], "domain_completeness": cat.snapshot["domain_completeness"]},
            "analysis": [{"requirement": a["req"]["id"], **{k: v for k, v in a["analysis"].items()}} for a in an], "coverage": covsum,
            "decisions_before_rules": [{"requirement": d["requirement"], "decision": d["decision"]} for d in dec_before], "decisions": decisions,
            "rules": {"before": rb0.snapshot(), "after": rb.snapshot(), "ai_approval_refused": ai_refused, "audit": rb.audit},
            "logic_discovery": rl.discover_logic(_logic_sample()),
            "packages": [{"manifest": p["manifest"], "files": p["files"]} for p in packages], "model": model, "grain": grain, "sqlite": sql,
            "validation": tv, "unsupported_requests": unsupported, "plan": plan, "audit": audit.entries,
            "recon": {"golden": golden, "levels": levels, "overall": overall, "l3_before_rules": {k: v for k, v in l3_before.items() if k != "differences"},
                      "naive_double_count": ({k: v for k, v in naive.items() if k != "differences"} | {"differences_count": len(naive["differences"])}) if naive else None,
                      "defect_matrix": matrix, "tolerance_policy": {k: str(v) for k, v in rc.TOLERANCE.items()},
                      "pending_replication": out["model"]["pending_replication"], "rejected": out["model"]["rejected"]},
            "metrics": metrics, "sample_documents": _samples(world, scenario)}


def _logic_sample() -> str:
    return (ar._KW_DEFINE + " SIM_Z_SAMPLE as select from ekpo inner join ekko on ekko.ebeln = ekpo.ebeln\n"
            "association [0..1] to I_Supplier as _Supplier on _Supplier.Supplier = ekko.lifnr\n"
            "{ key ekpo.ebeln, case when ekpo.elikz = 'X' then 'DONE' else 'OPEN' end as Status,\n"
            "  sum(ekpo.netwr) as NetValue }\nwhere ekpo.loekz = ''\n// AMDP marker and BAdI call below are Category B\n"
            "CLASS ZCL_CUSTOM_PRICE DEFINITION. METHOD calc. GET BADI lo_badi.")


def _samples(world, scenario):
    out = {}
    for sid, d in world["systems"].items():
        out[sid] = {"po_items": d["po_items"][:3], "gr": d["gr"][:3], "inv": d["inv"][:3], "bseg": d["bseg"][:4]}
    return json.loads(json.dumps(out, default=str))


def run_all(seed: int = 13, scenarios: tuple = ("A", "B"), regression: dict | None = None, n_po: dict | None = None) -> dict:
    res = {"version": VERSION, "mode": "DEMO", "seed": seed, "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "scenarios": {s: run_scenario(s, seed, (n_po or {}).get(s)) for s in scenarios}, "regression": regression or {"v012": "NOT_RECORDED"}}
    res["status"] = st.release_status(res)
    res["gates"] = st.evaluate_gates(res)
    res["overall_release"] = "ENGINEERING_ACCEPTED_SYNTHETIC" if all(g["status"] == "PASS" for g in res["gates"]) else "NOT_ACCEPTED"
    return res


def persist(res: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "results.json"
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs_v013")
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    res = run_all(a.seed)
    p = persist(res, Path(a.out))
    print(json.dumps({"results": str(p), "overall": res["overall_release"], "status": res["status"],
                      "gates": {g["id"]: g["status"] for g in res["gates"]}}, indent=1))
    return 0 if res["overall_release"] != "NOT_ACCEPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
