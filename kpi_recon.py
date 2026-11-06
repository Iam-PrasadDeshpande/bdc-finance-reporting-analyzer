"""v0.4 KPI reconciliation: compares two result sets only when their context is demonstrably equal.

PASS requires RUNTIME_EXTRACT data on both sides. Synthetic data yields SYNTHETIC_PASS at most.
Catalog metadata is never a data origin; it yields NOT_RUN.
"""
from __future__ import annotations

import csv
import hashlib
from datetime import date, timedelta
from pathlib import Path
from typing import Any

CONTEXT_KEYS = ("company_code", "ledger", "currency", "key_date", "aging_basis", "filters", "sign_convention")
MEASURES = ("open_ar", "overdue_ar", "overdue_ratio")
DEFAULT_TOLERANCE = {"abs": 0.01, "rel": 0.0, "ratio_abs": 1e-6}
# Synthetic-only rule for the alternative aging basis; not an SAP definition.
POSTING_DATE_TERMS_DAYS = 30


def synthetic_side(csv_path: str | Path, *, key_date: str, company_code: str = "1000", ledger: str = "0L",
                   currency: str = "EUR", aging_basis: str = "NET_DUE_DATE", include_special_gl: bool = False,
                   sign: int = 1, bucket_definitions: list[dict[str, Any]] | None = None,
                   columns: dict[str, str] | None = None, special_gl_flag: str = "Y") -> dict[str, Any]:
    """Build one result side from a CSV. `columns` maps canonical names to the file's own column names so an
    independently structured dataset can be read; `special_gl_flag` is that file's special-G/L marker value."""
    col = {k: k for k in ("company_code", "ledger", "currency", "posting_date", "due_date", "clearing_date", "special_gl", "open_amount")}
    col.update(columns or {})
    raw_bytes = Path(csv_path).read_bytes()
    kd = date.fromisoformat(key_date)
    open_total = overdue = 0.0
    buckets = {b["name"]: 0.0 for b in bucket_definitions or []}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r[col["company_code"]], r[col["ledger"]], r[col["currency"]]) != (company_code, ledger, currency):
                continue
            if r[col["special_gl"]] == special_gl_flag and not include_special_gl:
                continue
            clearing = r[col["clearing_date"]]
            if date.fromisoformat(r[col["posting_date"]]) > kd or (clearing and date.fromisoformat(clearing) <= kd):
                continue
            amt = float(r[col["open_amount"]]) * sign
            ref = date.fromisoformat(r[col["due_date"]]) if aging_basis == "NET_DUE_DATE" \
                else date.fromisoformat(r[col["posting_date"]]) + timedelta(days=POSTING_DATE_TERMS_DAYS)
            days = (kd - ref).days
            open_total += amt
            if days > 0:
                overdue += amt
            for b in bucket_definitions or []:
                if days >= b["from"] and (b.get("to") is None or days <= b["to"]):
                    buckets[b["name"]] += amt
    return {
        "origin": "SYNTHETIC", "dataset_id": hashlib.sha256(raw_bytes).hexdigest(),
        "context": {"company_code": company_code, "ledger": ledger, "currency": currency, "key_date": key_date,
                    "aging_basis": aging_basis, "filters": ["no_special_gl"] if not include_special_gl else [],
                    "sign_convention": "NATURAL" if sign == 1 else "INVERTED"},
        "measures": {"open_ar": open_total, "overdue_ar": overdue,
                     "overdue_ratio": overdue / open_total if open_total else None},
        "buckets": buckets if bucket_definitions else None, "bucket_definitions": bucket_definitions,
    }


def _norm(ctx: dict[str, Any]) -> dict[str, Any]:
    out = {k: ctx.get(k) for k in CONTEXT_KEYS}
    out["filters"] = sorted(map(str, out["filters"])) if out["filters"] is not None else None
    return out


def _within(a: float, b: float, tol: dict[str, float], ratio: bool) -> bool:
    diff = abs(a - b)
    if ratio:
        return diff <= tol["ratio_abs"]
    return diff <= max(tol["abs"], tol["rel"] * max(abs(a), abs(b)))


def reconcile(left: dict[str, Any] | None, right: dict[str, Any] | None, tolerance: dict[str, float] | None = None) -> dict[str, Any]:
    tol = {**DEFAULT_TOLERANCE, **(tolerance or {})}
    base = {"tolerance": tol, "measures": [], "buckets": [], "blocking": []}
    if not left or not right:
        return {**base, "status": "NOT_RUN", "reason": "Both result sets are required; none derived from catalog metadata"}
    origins = {left.get("origin"), right.get("origin")}
    if not origins <= {"SYNTHETIC", "RUNTIME_EXTRACT"}:
        return {**base, "status": "NOT_RUN", "reason": f"Data origin not reconcilable: {sorted(map(str, origins))}"}
    ids = (left.get("dataset_id"), right.get("dataset_id"))
    if not all(ids):
        return {**base, "status": "BLOCKED", "reason": "Independence cannot be established: dataset_id missing on a side",
                "blocking": ["missing dataset_id"]}
    if ids[0] == ids[1]:
        return {**base, "status": "BLOCKED", "reason": "Not independent: both sides were built from the same dataset",
                "blocking": ["identical dataset_id"]}
    lc, rc = _norm(left.get("context") or {}), _norm(right.get("context") or {})
    missing = sorted(k for k in CONTEXT_KEYS if lc[k] is None or rc[k] is None)
    if missing:
        return {**base, "status": "BLOCKED", "reason": "Reconciliation context incomplete", "blocking": [f"missing context: {k}" for k in missing]}
    diffs = [f"{k}: {lc[k]!r} != {rc[k]!r}" for k in CONTEXT_KEYS if lc[k] != rc[k]]
    if diffs:
        return {**base, "status": "BLOCKED", "reason": "Context differs; results are not comparable", "blocking": diffs}
    lm, rm = dict(left.get("measures") or {}), dict(right.get("measures") or {})
    for m in (lm, rm):  # derive ratio only from supplied measures
        if m.get("overdue_ratio") is None and m.get("open_ar") and m.get("overdue_ar") is not None:
            m["overdue_ratio"] = m["overdue_ar"] / m["open_ar"]
    rows = []
    for k in MEASURES:
        a, b = lm.get(k), rm.get(k)
        if a is None or b is None:
            rows.append({"measure": k, "left": a, "right": b, "result": "NOT_RUN", "reason": "measure unavailable on a side"})
        else:
            ok = _within(a, b, tol, k == "overdue_ratio")
            rows.append({"measure": k, "left": a, "right": b, "difference": a - b, "result": "PASS" if ok else "FAIL"})
    lb, rb = left.get("buckets"), right.get("buckets")
    if lb is not None or rb is not None:
        if lb is None or rb is None or left.get("bucket_definitions") != right.get("bucket_definitions") or not left.get("bucket_definitions"):
            base["buckets"] = [{"result": "BLOCKED", "reason": "bucket definitions missing or not identical"}]
        else:
            base["buckets"] = [{"bucket": n, "left": lb.get(n), "right": rb.get(n),
                                "result": "PASS" if _within(lb.get(n, 0.0), rb.get(n, 0.0), tol, False) else "FAIL"} for n in lb]
    results = [r["result"] for r in rows + base["buckets"]]
    if "FAIL" in results:
        status = "FAIL"
    elif "PASS" not in results:
        status = "NOT_RUN"
    elif "BLOCKED" in results or "NOT_RUN" in results:
        status = "PARTIAL"
    else:
        status = "PASS" if origins == {"RUNTIME_EXTRACT"} else "SYNTHETIC_PASS"
    return {**base, "status": status, "measures": rows, "origins": sorted(origins)}
