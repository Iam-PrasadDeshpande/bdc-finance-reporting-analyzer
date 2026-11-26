"""Explicit, approval-aware business-rule book and business-logic discovery (categories A / B / C).

AI may PROPOSE a rule; it can never approve one. Approval requires a named human approver. Unapproved material rules
block the Finance validation that depends on them. Formulas run in a restricted arithmetic evaluator (no eval of code).
"""
from __future__ import annotations

import ast
import re
from decimal import Decimal

from .core import D

STATUSES = ("DRAFT", "PROPOSED", "APPROVED", "REJECTED")
AI_ACTORS = {"ai", "claude", "assistant", "llm", "model", "bot", "system"}


class RuleError(ValueError):
    pass


_ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.BoolOp, ast.Name, ast.Load, ast.Constant,
            ast.Call, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq,
            ast.NotEq, ast.And, ast.Or, ast.Not)
_FUNCS = {"min": min, "max": max, "abs": abs}


def safe_eval(formula: str, variables: dict):
    """Evaluate a restricted arithmetic/comparison expression with Decimal values."""
    tree = ast.parse(formula, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise RuleError(f"disallowed construct {type(node).__name__} in formula")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in _FUNCS):
            raise RuleError("only min/max/abs calls are allowed")
        if isinstance(node, ast.Name) and node.id not in variables and node.id not in _FUNCS:
            raise RuleError(f"unknown variable {node.id}")
    env = {k: D(v) if isinstance(v, (int, float, str, Decimal)) and not isinstance(v, bool) else v for k, v in variables.items()}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return D(n.value) if isinstance(n.value, (int, float)) and not isinstance(n.value, bool) else n.value
        if isinstance(n, ast.Name):
            return env[n.id]
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else (not v if isinstance(n.op, ast.Not) else v)
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            return {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b, ast.Div: lambda: a / b}[type(n.op)]()
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, comp in zip(n.ops, n.comparators):
                right = ev(comp)
                ok = {ast.Lt: left < right, ast.LtE: left <= right, ast.Gt: left > right, ast.GtE: left >= right,
                      ast.Eq: left == right, ast.NotEq: left != right}[type(op)]
                if not ok:
                    return False
                left = right
            return True
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        if isinstance(n, ast.Call):
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise RuleError("unsupported node")
    return ev(tree)


class Rule:
    def __init__(self, rule_id: str, description: str, source_fields: list[str], target_fields: list[str], formula: str,
                 owner: str, effective_from: str = "2026-01-01", effective_to: str | None = None,
                 systems: list[str] | None = None, examples: list[dict] | None = None, category: str = "C",
                 material: bool = True, affects: list[str] | None = None, status: str = "PROPOSED",
                 proposed_by: str = "ai"):
        self.d = dict(rule_id=rule_id, description=description, source_fields=source_fields, target_fields=target_fields,
                      formula=formula, owner=owner, effective_from=effective_from, effective_to=effective_to,
                      systems=systems or ["*"], examples=examples or [], category=category, material=material,
                      affects=affects or [], status=status, proposed_by=proposed_by, approved_by=None, approval_scope=None,
                      test_results=[])

    def run_tests(self) -> list[dict]:
        res = []
        for i, ex in enumerate(self.d["examples"], 1):
            try:
                got = safe_eval(self.d["formula"], ex["inputs"])
                ok = D(got) == D(ex["expected"]) if not isinstance(got, bool) else got == ex["expected"]
                res.append({"case": i, "ok": bool(ok), "expected": str(ex["expected"]), "actual": str(got)})
            except Exception as e:  # noqa: BLE001 - reported as a failed case
                res.append({"case": i, "ok": False, "error": str(e)})
        self.d["test_results"] = res
        return res

    def tests_pass(self) -> bool:
        return bool(self.d["examples"]) and all(t["ok"] for t in self.run_tests())


class RuleBook:
    def __init__(self):
        self.rules: dict[str, Rule] = {}
        self.audit: list[dict] = []

    def add(self, rule: Rule) -> None:
        self.rules[rule.d["rule_id"]] = rule

    def approve(self, rule_id: str, approver: str, scope: str = "LIVE") -> None:
        r = self.rules[rule_id]
        if not approver or approver.strip().lower() in AI_ACTORS or approver.strip().lower() == r.d["proposed_by"].lower():
            raise RuleError("a rule must be approved by a named human approver; AI cannot approve accounting logic")
        if not r.tests_pass():
            raise RuleError("rule has no passing test cases; approval refused")
        r.d.update(status="APPROVED", approved_by=approver, approval_scope=scope)
        self.audit.append({"rule": rule_id, "action": "APPROVE", "by": approver, "scope": scope})

    def reject(self, rule_id: str, by: str) -> None:
        self.rules[rule_id].d["status"] = "REJECTED"
        self.audit.append({"rule": rule_id, "action": "REJECT", "by": by})

    def unresolved(self, required: list[str] | None = None) -> list[str]:
        """Material rules (optionally limited to `required`) that are not APPROVED. Unknown ids count as unresolved."""
        ids = required if required is not None else [k for k, r in self.rules.items() if r.d["material"]]
        out = []
        for i in ids:
            r = self.rules.get(i)
            if r is None or (r.d["material"] and r.d["status"] != "APPROVED"):
                out.append(i)
        return sorted(out)

    def blocks_finance_validation(self, measure_ids: list[str]) -> list[str]:
        needed = [k for k, r in self.rules.items() if r.d["material"] and set(r.d["affects"]) & set(measure_ids)]
        return self.unresolved(needed)

    def snapshot(self) -> list[dict]:
        return [dict(r.d) for _, r in sorted(self.rules.items())]


def default_rulebook(resolved: bool = False) -> RuleBook:
    """Rules for the Procure-to-Pay reference. Approvals here are SYNTHETIC-scope only and never count as live approval."""
    rb = RuleBook()
    rb.add(Rule("R-GRIR-001", "GR/IR balance = goods receipt value minus invoiced value at purchase-order price",
                ["gr_value", "inv_value_po_price"], ["grir_balance"], "gr_value - inv_value_po_price", "Finance owner (synthetic)",
                examples=[{"inputs": {"gr_value": 10000, "inv_value_po_price": 10000}, "expected": 0},
                          {"inputs": {"gr_value": 6000, "inv_value_po_price": 0}, "expected": 6000}],
                affects=["grir_balance"]))
    rb.add(Rule("R-FI-SOURCE-001", "Each company code is reported from exactly one FI source; replicated documents never add to totals",
                ["source_fi_total", "cfin_fi_total", "authority_is_cfin"], ["reported_fi_total"],
                "cfin_fi_total if authority_is_cfin else source_fi_total", "Finance owner (synthetic)",
                examples=[{"inputs": {"source_fi_total": 500, "cfin_fi_total": 500, "authority_is_cfin": True}, "expected": 500},
                          {"inputs": {"source_fi_total": 500, "cfin_fi_total": 500, "authority_is_cfin": False}, "expected": 500}],
                affects=["gl_balance", "debit_credit_balance", "journal_total"]))
    rb.add(Rule("R-CLEARING-ALLOC-001", "A supplier item is cleared when allocated payments reach the invoice gross amount",
                ["invoice_gross", "allocated_payments"], ["is_cleared"], "allocated_payments >= invoice_gross", "Finance owner (synthetic)",
                examples=[{"inputs": {"invoice_gross": 6000, "allocated_payments": 6000}, "expected": True},
                          {"inputs": {"invoice_gross": 4000, "allocated_payments": 0}, "expected": False}],
                affects=["supplier_open_items", "supplier_cleared_items"]))
    rb.add(Rule("R-AMOUNT-BASIS-001", "PO account-assignment amounts are reported in document currency",
                ["wrbtr"], ["amount_doc_ccy"], "wrbtr", "Finance owner (synthetic)",
                examples=[{"inputs": {"wrbtr": 100}, "expected": 100}], affects=["po_account_assignment_value"], material=True))
    rb.add(Rule("R-INV-EXCEPTION-001", "Supplier invoice exception classification (price/quantity/tax variance)",
                [], [], "0", "Finance owner (synthetic)", material=False, affects=["invoice_exceptions"]))
    if resolved:
        for rid in ("R-GRIR-001", "R-FI-SOURCE-001", "R-CLEARING-ALLOC-001", "R-AMOUNT-BASIS-001"):
            rb.approve(rid, "SYNTHETIC_OWNER_FIXTURE", scope="SYNTHETIC_ONLY")
    return rb


# ---- business-logic discovery (A / B / C) ---------------------------------------------------------------------------

_B_MARKERS = {"AMDP": r"(?i)AMDP|IF_AMDP_MARKER_HDB", "ABAP_ROUTINE": r"(?i)\bFORM\b|\bMETHOD\b|\bENDMETHOD\b",
              "BADI": r"(?i)\bBADI\b|CL_EXITHANDLER|GET BADI", "CUSTOM_CLASS": r"(?i)\bCL_[A-Z0-9_]*Z[A-Z0-9_]*\b|\bZCL_[A-Z0-9_]+"}


def discover_logic(source: str) -> dict:
    """Lexical logic discovery over CDS-like text. Category A is normalized; B yields a review package; C stays manual."""
    a: list[dict] = []
    for m in re.finditer(r"(?is)\bcase\b(.*?)\bend\b", source):
        a.append({"kind": "CASE", "text": " ".join(m.group(0).split())})
    for m in re.finditer(r"(?i)\b(inner|left outer|left|right outer)?\s*join\s+([A-Za-z0-9_./]+)\s+(?:as\s+(\w+)\s+)?on\s+([^\n{]+)", source):
        a.append({"kind": "JOIN", "type": (m.group(1) or "inner").lower(), "target": m.group(2), "on": m.group(4).strip()})
    for m in re.finditer(r"(?i)\bassociation\s*(\[[^\]]*\])?\s*to\s+([A-Za-z0-9_./]+)", source):
        a.append({"kind": "ASSOCIATION", "cardinality": m.group(1) or "[UNSPECIFIED]", "target": m.group(2)})
    for m in re.finditer(r"(?im)^\s*where\s+(.+)$", source):
        a.append({"kind": "FILTER", "text": m.group(1).strip()})
    for m in re.finditer(r"(?i)\b(sum|min|max|avg|count)\s*\(([^)]*)\)", source):
        a.append({"kind": "AGGREGATION", "function": m.group(1).lower(), "argument": m.group(2).strip()})
    for m in re.finditer(r"(?i)\bcast\s*\(([^)]*)\)|@Semantics\.(?:amount|quantity)\.\w+\s*:\s*'([^']+)'", source):
        a.append({"kind": "CURRENCY_UNIT_REF", "text": " ".join(x for x in m.groups() if x)})
    b = [{"kind": k, "evidence": m.group(0)} for k, rx in _B_MARKERS.items() for m in re.finditer(rx, source)]
    return {"category_A": a, "category_B": b,
            "category_B_review_package": ([{"action": "Obtain source of the referenced code, translate, then validate against "
                                            "approved examples before acceptance", "dependencies": sorted({x["kind"] for x in b})}]
                                          if b else []),
            "category_C": "Explicit business rules are maintained in the rule book; they are never inferred from source text.",
            "note": "Lexical analysis only; not a parser and not proof of runtime behaviour."}
