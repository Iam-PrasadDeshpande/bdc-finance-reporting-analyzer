"""Public AR Aging method demonstration (SYNTHETIC; project-authored rules only).

Provenance (recorded in the project's release records):
- Calculation: `kpi_recon.synthetic_side` and `kpi_recon.reconcile`, written in this project on 2026-11-05 (v0.4),
  before any SAP Business Data Cloud trial content was accessed (2026-11-06).
- Decision points: the project's AR Aging requirements contract (2026-11-05) and Finance-owner validation matrix
  (2026-11-06, written before trial access): ledger, aging basis, special G/L, buckets.
- Data: generated here with neutral, project-chosen field names. Not SAP data, not customer data.
This module does NOT implement, reproduce or approximate SAP-delivered BDC/Datasphere content. The "target" side is a
configurable candidate rule set used to demonstrate how source and target definitions are compared and reconciled.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from kpi_recon import reconcile, synthetic_side

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data/public_demo"
SOURCE_FILE = "source_report_extract_SYNTHETIC.csv"
TARGET_FILE = "target_model_extract_SYNTHETIC.csv"
COMPANY_CODES = {"1000": "EUR", "2000": "USD"}
LEDGERS = ("0L", "2L")
SOURCE_COLUMNS = ["company_code", "ledger", "currency", "posting_date", "due_date", "clearing_date", "special_gl", "open_amount"]
# The target extract is structured differently on purpose (independent layout), mapped onto the canonical names.
TARGET_COLUMNS = ["entity", "ledger_id", "ccy", "post_dt", "due_dt", "clear_dt", "sgl", "amt"]
TARGET_MAP = dict(zip(SOURCE_COLUMNS, TARGET_COLUMNS))
REFERENCE_RULES = {"ledger": "0L", "aging_basis": "NET_DUE_DATE", "include_special_gl": False}
RULE_LABELS = {
    "ledger": ("Ledger", {"0L": "Primary ledger (0L)", "2L": "Secondary ledger (2L)"}),
    "aging_basis": ("Aging basis", {"NET_DUE_DATE": "Net due date", "POSTING_DATE_PLUS_30": "Posting date + 30 days"}),
    "include_special_gl": ("Special G/L items", {False: "Excluded", True: "Included"}),
}


def default_buckets(limits: tuple[int, ...] = (30, 60, 90)) -> list[dict[str, Any]]:
    """Overdue-day buckets: not due, 1-a, a+1-b, ..., over last limit (days = key date - aging date)."""
    out, lo = [{"name": "not due", "from": -99999, "to": 0}], 1
    for b in limits:
        out.append({"name": f"{lo}-{b}", "from": lo, "to": b})
        lo = b + 1
    out.append({"name": f"over {limits[-1]}", "from": lo, "to": None})
    return out


def generate(seed: int = 2026, n: int = 360, key_date: str = "2026-09-30") -> list[dict[str, Any]]:
    """Neutral synthetic AR items: invoices, partial payments, credit memos, special G/L items, cleared items."""
    rng, kd, rows = random.Random(seed), date.fromisoformat(key_date), []
    for _ in range(n):
        cc = rng.choice(list(COMPANY_CODES))
        post = kd - timedelta(days=rng.randint(1, 120))
        kind = rng.choices(["invoice", "partial_payment", "credit_memo", "special_gl", "cleared_before", "cleared_after",
                            "posted_after"], [52, 10, 8, 6, 12, 8, 4])[0]
        amt = round(rng.uniform(150, 18000), 2)
        due, clear, sgl = post + timedelta(days=rng.choice([14, 30, 45, 60])), None, ""
        if kind in ("partial_payment", "credit_memo"):
            amt, due = -round(amt * rng.uniform(0.1, 0.6), 2), post
        elif kind == "special_gl":
            amt, due, sgl = -amt, post, "Y"
        elif kind == "cleared_before":
            clear = min(kd, post + timedelta(days=rng.randint(1, 60)))
        elif kind == "cleared_after":
            clear = kd + timedelta(days=rng.randint(1, 30))
        elif kind == "posted_after":
            post = kd + timedelta(days=rng.randint(1, 15))
            due = post + timedelta(days=30)
        for led in LEDGERS:  # secondary ledger carries a small valuation difference on some items
            a = amt if led == "0L" or rng.random() > 0.15 else round(amt * 1.02, 2)
            rows.append({"company_code": cc, "ledger": led, "currency": COMPANY_CODES[cc], "posting_date": post.isoformat(),
                         "due_date": due.isoformat(), "clearing_date": clear.isoformat() if clear else "",
                         "special_gl": sgl, "open_amount": f"{a:.2f}", "kind": kind})
    return rows


def write_dataset(out_dir: str | Path = DATA, seed: int = 2026, n: int = 360, key_date: str = "2026-09-30") -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = generate(seed, n, key_date)
    with open(out / SOURCE_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SOURCE_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(out / TARGET_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(TARGET_COLUMNS)
        for r in rows:
            w.writerow([r["company_code"], r["ledger"], r["currency"], r["posting_date"], r["due_date"], r["clearing_date"],
                        "X" if r["special_gl"] == "Y" else "", r["open_amount"]])
    manifest = {"origin": "SYNTHETIC", "generator": "ar_aging_demo.generate", "seed": seed, "items": n, "rows": len(rows),
                "note": "Neutral synthetic AR items. Both extracts derive from one synthetic ledger; their independence is simulated.",
                "files_sha256": {p: hashlib.sha256((out / p).read_bytes()).hexdigest() for p in (SOURCE_FILE, TARGET_FILE)}}
    (out / "manifest_SYNTHETIC.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def _side(path: Path, key_date: str, company_code: str, rules: dict[str, Any], buckets: list[dict[str, Any]],
          target: bool) -> dict[str, Any]:
    side = synthetic_side(path, key_date=key_date, company_code=company_code, ledger=rules["ledger"],
                          currency=COMPANY_CODES[company_code], aging_basis=rules["aging_basis"],
                          include_special_gl=rules["include_special_gl"], bucket_definitions=buckets,
                          columns=TARGET_MAP if target else None, special_gl_flag="X" if target else "Y")
    side["rules"] = dict(rules)
    return side


def run(key_date: str = "2026-09-30", company_code: str = "1000", buckets: list[dict[str, Any]] | None = None,
        target_rules: dict[str, Any] | None = None, data_dir: str | Path = DATA) -> dict[str, Any]:
    """Reference (source report rules) vs candidate target rules, reconciled with kpi_recon; plus sensitivities."""
    d, buckets = Path(data_dir), buckets or default_buckets()
    rules = {**REFERENCE_RULES, **(target_rules or {})}
    src = _side(d / SOURCE_FILE, key_date, company_code, REFERENCE_RULES, buckets, target=False)
    tgt = _side(d / TARGET_FILE, key_date, company_code, rules, buckets, target=True)
    sens = []
    for key, (label, values) in RULE_LABELS.items():
        for value in values:
            if value == REFERENCE_RULES[key]:
                continue
            alt = _side(d / TARGET_FILE, key_date, company_code, {**REFERENCE_RULES, key: value}, buckets, target=True)
            sens.append({"decision": label, "alternative": values[value], "reference": values[REFERENCE_RULES[key]],
                         "open_ar_delta": round(alt["measures"]["open_ar"] - src["measures"]["open_ar"], 2),
                         "overdue_ar_delta": round(alt["measures"]["overdue_ar"] - src["measures"]["overdue_ar"], 2),
                         "reconciliation": reconcile(src, alt)["status"]})
    return {"origin": "SYNTHETIC", "publication": "PUBLIC_METHOD_DEMONSTRATION",
            "warning": "Synthetic method demonstration with project-authored rules. Not SAP content logic, not customer data, "
                       "not evidence of customer compatibility. Finance assessment: HOLD / INSUFFICIENT_EVIDENCE.",
            "key_date": key_date, "company_code": company_code, "currency": COMPANY_CODES[company_code],
            "reference_rules": REFERENCE_RULES, "target_rules": rules, "buckets": buckets,
            "source": src, "target": tgt, "reconciliation": reconcile(src, tgt), "sensitivities": sens}


def summary() -> dict[str, Any]:
    """Headline figures for the homepage, computed by this engine."""
    statuses = {cc: run(company_code=cc)["reconciliation"]["status"] for cc in COMPANY_CODES}
    return {"public": True, "company_codes": len(COMPANY_CODES), "status": "/".join(sorted(set(statuses.values()))),
            "sensitivities": len(run()["sensitivities"])}


if __name__ == "__main__":
    print(json.dumps(write_dataset(), indent=1))
