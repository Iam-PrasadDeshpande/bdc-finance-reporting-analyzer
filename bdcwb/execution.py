"""Dependency-aware execution plan, mode gating, idempotency, bounded retries and a credential-safe audit log.

Real execution needs a verified interface. This build ships none, so no step can reach DEPLOYED or RUNTIME_VERIFIED: those
states are reserved for live evidence and cannot be set by the synthetic flow.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .core import MODES, STATES

STEPS = [
    (1, "Validate connectivity and permissions", [], "READ"), (2, "Discover source metadata", [1], "READ"),
    (3, "Validate catalog evidence", [2], "READ"), (4, "Approve mapping decisions", [3], "HUMAN"),
    (5, "Generate source-side artifacts", [4], "LOCAL"), (6, "Validate generated artifacts", [5], "LOCAL"),
    (7, "Execute authorized source-side changes", [6], "WRITE"), (8, "Activate source artifacts where authorized", [7], "WRITE"),
    (9, "Install or publish eligible data products", [8], "WRITE"), (10, "Create Datasphere acquisition objects", [9], "WRITE"),
    (11, "Create transformations and semantic models", [10], "LOCAL"), (12, "Deploy authorized Datasphere artifacts", [11], "WRITE"),
    (13, "Execute initial and delta loads", [12], "RUN"), (14, "Validate technical runtime results", [13], "RUN"),
    (15, "Execute source-to-target reconciliation", [14], "RUN"),
]
_SECRET_KEY = re.compile(r"(pass|tok|sec|key|cred|auth)", re.I)
_SECRET_VAL = re.compile(r"(?i)(bearer\s+\S+|eyJ[A-Za-z0-9_\-]{10,})")


class RetryableError(Exception):
    pass


class AuthorizationFailure(Exception):
    """Authorization/configuration failures are never retried."""


@dataclass
class ExecutionAuthorization:
    approver: str
    systems: list[str]
    non_production_confirmed: bool
    expires: str
    scope: str = "ENGINEERING_CHANGES"
    production_systems: list[str] = field(default_factory=list)

    def valid_for(self, system_ids: list[str], now: str) -> tuple[bool, str]:
        if not self.approver or not self.non_production_confirmed:
            return False, "approver and non-production confirmation required"
        if set(system_ids) & set(self.production_systems):
            return False, "production systems are never authorized by this build"
        if not set(system_ids) <= set(self.systems):
            return False, "systems outside the authorized list"
        if self.expires < now:
            return False, "authorization expired"
        return True, "ok"


def redact(obj):
    if isinstance(obj, dict):
        return {k: ("[REDACTED]" if _SECRET_KEY.search(str(k)) and not isinstance(v, (dict, list)) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    if isinstance(obj, str):
        return _SECRET_VAL.sub("[REDACTED]", obj)
    return obj


class AuditLog:
    def __init__(self):
        self.entries: list[dict] = []

    def add(self, actor: str, action: str, mode: str, detail: dict | None = None) -> None:
        self.entries.append(redact({"seq": len(self.entries) + 1, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "actor": actor, "action": action, "mode": mode, "detail": detail or {}}))


def idempotency_key(step: int, payload) -> str:
    return hashlib.sha256((str(step) + json.dumps(payload, sort_keys=True, default=str)).encode()).hexdigest()[:16]


def run_with_retry(fn, max_attempts: int = 3):
    """Bounded retries for transient errors only. Returns (result, attempts)."""
    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(), attempt
        except RetryableError as e:
            last = e
        except AuthorizationFailure:
            raise
    raise RetryableError(f"gave up after {max_attempts} attempts: {last}")


def build_plan(mode: str, facts: dict, auth: ExecutionAuthorization | None = None, store: dict | None = None,
               audit: AuditLog | None = None) -> list[dict]:
    """facts: counts and flags derived from the persisted run (objects, packages, lint, model, recon...)."""
    assert mode in MODES
    audit = audit or AuditLog()
    store = store if store is not None else {}
    state: dict[int, str] = {}
    out = []
    synthetic_ok = {2: facts.get("objects", 0) > 0, 3: facts.get("catalog_ok", False), 5: facts.get("packages", 0) > 0,
                    6: facts.get("lint_ok", False), 11: facts.get("model_ok", False), 13: facts.get("recon_ran", False),
                    14: facts.get("recon_ran", False), 15: facts.get("recon_ran", False)}
    for n, name, deps, kind in STEPS:
        detail, st = "", "PROPOSED"
        if any(state.get(d) in ("BLOCKED", "FAILED") for d in deps):
            st, detail = "BLOCKED", "dependency blocked"
        elif mode == "DEMO":
            if n in (2, 3, 5, 6, 11, 13, 14, 15):
                if synthetic_ok.get(n):
                    st = {5: "GENERATED", 11: "GENERATED"}.get(n, "OFFLINE_VALIDATED")
                    if n == 11 and facts.get("model_ok"):
                        st = "OFFLINE_VALIDATED"
                    detail = "synthetic / offline only"
                else:
                    st, detail = "BLOCKED", "prerequisite evidence missing"
            elif n == 4:
                st, detail = "PROPOSED", "awaiting named human approver (approval queue)"
            elif kind == "WRITE":
                st, detail = ("READY_FOR_AUTHORIZED_EXECUTION", "runbook generated; not executed in DEMO") if facts.get("lint_ok") else ("BLOCKED", "artifacts not validated")
            else:
                st, detail = "PROPOSED", "NOT_EXECUTED_IN_DEMO (no connection by design)"
        elif mode == "CONNECTED_READ_ONLY":
            if kind in ("WRITE", "RUN"):
                st, detail = "BLOCKED", "mode forbids changes and loads"
            elif n in (1, 2, 3):
                st, detail = "BLOCKED", "no verified live interface configured in this build (ADT/catalog adapters unavailable)"
            else:
                st, detail = "PROPOSED", "local step; run in DEMO or after live metadata is imported"
        else:  # CONTROLLED_EXECUTION
            ok, why = (auth.valid_for(facts.get("systems", []), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")) if auth else (False, "no execution authorization supplied"))
            if not ok:
                st, detail = "BLOCKED", f"authorization: {why}"
            elif kind in ("WRITE", "RUN", "READ"):
                st, detail = "BLOCKED", "no verified executor/interface in this build; manual runbook only"
            else:
                st, detail = "PROPOSED", "local step"
        assert st in STATES
        key = idempotency_key(n, {"mode": mode, "facts": {k: facts[k] for k in sorted(facts) if k != "systems"}})
        prev = store.get(n)
        resumed = bool(prev and prev["key"] == key and prev["state"] == st)
        store[n] = {"key": key, "state": st}
        state[n] = st
        audit.add("orchestrator", f"STEP_{n}", mode, {"state": st, "resumed": resumed})
        out.append({"step": n, "name": name, "depends_on": deps, "kind": kind, "state": st, "detail": detail, "idempotency_key": key,
                    "resumed_from_store": resumed, "mode": mode})
    return out
