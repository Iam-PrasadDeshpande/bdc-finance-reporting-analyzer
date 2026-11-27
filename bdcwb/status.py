"""Release status dimensions and the G01-G15 acceptance gates, evaluated from persisted run results only."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .core import resolve_dependencies, SapObject

EVIDENCE_FILE = Path(__file__).with_name("release_evidence.json")
LIVE_HOLD = {"LIVE_SAP_VALIDATION": "HOLD", "LIVE_BDC_VALIDATION": "HOLD", "FINANCE_VALIDATION": "HOLD / INSUFFICIENT_EVIDENCE",
             "PUBLICATION_AUTHORIZATION": "NOT_GRANTED"}
_LEAK_PATTERN = re.compile(r"(?i)(password\s*[=:]|client[_]secret|bearer\s+[a-z0-9]{12,}|BEGIN [A-Z ]*PRIVATE KEY|eyJ[A-Za-z0-9_\-]{20,})")


def load_evidence() -> dict:
    try:
        return json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def release_status(res: dict) -> dict:
    """Independent status dimensions. Synthetic success never promotes a live dimension."""
    ev = load_evidence()
    scs = res["scenarios"].values()
    syn_tech = "PASS" if all(s["validation"]["offline_status"] == "OFFLINE_VALIDATED" for s in scs) else "FAIL"
    syn_fin = "PASS" if all(s["recon"]["overall"] == "SYNTHETIC_PASS" and s["recon"]["golden"]["status"] == "SYNTHETIC_PASS" for s in scs) else "FAIL"
    return {"engineering_acceptance": "PENDING_GATES", "synthetic_technical_validation": syn_tech, "synthetic_finance_validation": syn_fin,
            "connected_sap_validation": "NOT_RUN", "bdc_runtime_validation": "HOLD", "live_finance_validation": "HOLD / INSUFFICIENT_EVIDENCE",
            "architect_review": "AI_REVIEWS_DONE_HUMAN_REVIEW_PENDING", "synthetic_demo_publication": ev.get("publication_approval", "NOT_GRANTED"), **LIVE_HOLD}


def _g(id_, name, ok, evidence, not_run=False):
    return {"id": id_, "name": name, "status": "NOT_RUN" if not_run else ("PASS" if ok else "FAIL"), "evidence": evidence}


def _scenario_ok(s):
    r = s["recon"]
    return (r["overall"] == "SYNTHETIC_PASS" and r["golden"]["status"] == "SYNTHETIC_PASS" and s["metrics"]["generated_artifacts"] > 0
            and s["sqlite"]["status"] == "OFFLINE_VALIDATED" and s["grain"]["status"] == "PASS")


def evaluate_gates(res: dict) -> list[dict]:
    ev = load_evidence()
    A, B = res["scenarios"].get("A"), res["scenarios"].get("B")
    both = [s for s in (A, B) if s]
    g = []
    reg = res.get("regression", {})
    reg = reg if "failures" in reg else ev.get("regression_v012", {})
    g.append(_g("G01", "Existing v0.12 functionality remains operational", reg.get("failures") == 0 and reg.get("ran", 0) > 0,
                f"v0.12 regression: ran={reg.get('ran')} failures={reg.get('failures')} (recorded {reg.get('recorded', 'n/a')})", not_run="ran" not in reg))
    g.append(_g("G02", "Scenario A works end-to-end in synthetic mode", bool(A) and _scenario_ok(A),
                f"A: recon {A and A['recon']['overall']}, golden {A and A['recon']['golden']['status']}, artifacts {A and A['metrics']['generated_artifacts']}"))
    g.append(_g("G03", "Scenario B works end-to-end in synthetic mode", bool(B) and _scenario_ok(B),
                f"B: recon {B and B['recon']['overall']}, systems {B and B['metrics']['landscape_systems']}"))
    cyc = resolve_dependencies({"X:A": SapObject("X", "1", "A", "T", "r", depends_on=["B"]), "X:B": SapObject("X", "1", "B", "T", "r", depends_on=["A"])}, ["X:A"])
    g.append(_g("G04", "Multi-object dependency discovery is demonstrable",
                all(len(s["dependencies"]["nodes"]) > 10 and s["dependencies"]["unresolved"] for s in both) and bool(cyc["cycles"]),
                f"nodes {[len(s['dependencies']['nodes']) for s in both]}, unresolved reported, cycle self-test found {len(cyc['cycles'])}"))
    states = {a["catalog_state"] for s in both for a in s["analysis"]}
    prods = {p["evidence"] for s in both for p in s["catalog"]["products"]}
    rv = [d["decision"] for s in both for d in s["decisions"]]
    g.append(_g("G05", "Catalog evidence and unknown states are correctly classified",
                "UNKNOWN" in states and "CANDIDATE_UNVERIFIED" in prods and "CATALOG_REVIEW_REQUIRED" in rv and
                all(s["metrics"]["verified_sap_managed_products"] == 0 for s in both),
                f"catalog states {sorted(states)}; evidence classes {sorted(prods)}; no product claimed verified"))
    g.append(_g("G06", "Reuse, extension and customer-managed routes are demonstrated",
                {"REUSE_STANDARD", "KEY_USER_EXTENSION", "CREATE_CUSTOMER_MANAGED_PRODUCT", "DATASPHERE_ENRICHMENT"} <= set(rv), f"decisions {sorted(set(rv))}"))
    un = [u for s in both for u in s["unsupported_requests"]]
    ok7 = bool(un) and all((u["decision"] == "EXECUTION_BLOCKED") if "expected_not" not in u else u["decision"] != u["expected_not"] for u in un)
    g.append(_g("G07", "Unsupported extension and extraction requests are blocked", ok7, "; ".join(f"{u['case']} -> {u['decision']}" for u in un[:3])))
    g.append(_g("G08", "Generated artifacts are inspectable and traceable",
                all(s["packages"] and all(p["manifest"]["state"] == "GENERATED" and not p["manifest"]["activated"] and not p["manifest"]["published"] for p in s["packages"])
                    and any(p["manifest"]["traceability"] for p in s["packages"]) for s in both),
                f"packages {[len(s['packages']) for s in both]}, all GENERATED, none activated or published"))
    g.append(_g("G09", "Business rules are explicit and approval-aware",
                all(s["rules"]["ai_approval_refused"] and s["metrics"]["unresolved_business_rules_before"] > 0 and s["metrics"]["unresolved_business_rules_after"] == 0
                    and s["recon"]["l3_before_rules"]["status"] == "BLOCKED_UNAPPROVED_RULE" for s in both),
                "AI approval refused; unapproved material rules blocked reconciliation; approved rules (synthetic scope) unblock it"))
    g.append(_g("G10", "Datasphere modelling preserves grain and measure correctness",
                all(s["grain"]["status"] == "PASS" and s["sqlite"]["status"] == "OFFLINE_VALIDATED" and s["sqlite"]["fan_out_demonstration"]["multiplied"] for s in both),
                "grain PASS; generated SQL reproduces measures; naive fact join demonstrably multiplies PO value"))
    g.append(_g("G11", "Independent golden Finance reconciliation passes", all(s["recon"]["golden"]["status"] == "SYNTHETIC_PASS" for s in both),
                "hand-authored expectations matched by BOTH the reference path and the BDC path (SYNTHETIC_PASS)"))
    g.append(_g("G12", "Injected reconciliation differences are detected", all(r["detected"] for s in both for r in s["recon"]["defect_matrix"]),
                f"{sum(len(s['recon']['defect_matrix']) for s in both)} injected defects, all detected"))
    nv = B and B["recon"]["naive_double_count"]
    g.append(_g("G13", "Cross-system duplicate accounting is prevented", bool(nv) and nv["status"] == "FAIL" and B["recon"]["levels"]["L3"]["status"] == "SYNTHETIC_PASS",
                "summing source FI and replicated Central Finance FI is detected (FAIL); single-source rule passes"))
    plan_bad = [p["state"] for s in both for m in s["plan"].values() for p in m if p["state"] in ("DEPLOYED", "RUNTIME_VERIFIED")]
    g.append(_g("G14", "Synthetic and live evidence remain separate",
                all(s["evidence_mode"] == "SYNTHETIC" and s["mode"] == "DEMO" and s["metrics"]["executed_artifacts"] == 0 for s in both) and not plan_bad,
                "all results tagged SYNTHETIC/DEMO; no step DEPLOYED or RUNTIME_VERIFIED; live dimensions stay HOLD"))
    leaked = bool(_LEAK_PATTERN.search(json.dumps(res, default=str)))
    ctl = all(p["state"] == "BLOCKED" for s in both for p in s["plan"]["CONTROLLED_EXECUTION"] if p["kind"] in ("WRITE", "RUN", "READ"))
    ro = all(p["state"] == "BLOCKED" for s in both for p in s["plan"]["CONNECTED_READ_ONLY"] if p["kind"] in ("WRITE", "RUN"))
    pub = ev.get("public_build_audit")
    g.append(_g("G15", "Security, regression and repository publication restrictions are preserved",
                not leaked and ctl and ro and res["mode"] == "DEMO" and pub == "PASS",
                f"no credential patterns in results: {not leaked}; controlled-execution blocked without authorization: {ctl}; read-only blocks writes: {ro}; "
                f"public build audit (recorded evidence, not a live check; recorded {ev.get('recorded', 'unknown')}): {pub}", not_run=pub is None))
    return g
