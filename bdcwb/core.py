"""BDC workbench v0.13 - shared vocabulary, decimal helpers, generic metadata model and dependency resolver.

Everything here is metadata-driven and synthetic-safe. Nothing in this package connects to SAP.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

VERSION = "0.13"

EVIDENCE = ("PUBLISHED_VERIFIED", "TENANT_VERIFIED", "CUSTOMER_PROVIDED", "CANDIDATE_UNVERIFIED", "SYNTHETIC_FIXTURE", "UNKNOWN")
VERIFIED_EVIDENCE = ("PUBLISHED_VERIFIED", "TENANT_VERIFIED", "CUSTOMER_PROVIDED")
MODES = ("DEMO", "CONNECTED_READ_ONLY", "CONTROLLED_EXECUTION")
DEFAULT_MODE = "DEMO"
STATES = ("PROPOSED", "GENERATED", "OFFLINE_VALIDATED", "READY_FOR_AUTHORIZED_EXECUTION", "DEPLOYED",
          "RUNTIME_VERIFIED", "BLOCKED", "FAILED")
GAPS = ("NO_GAP", "FIELD_GAP", "KEY_GAP", "RELATIONSHIP_GAP", "GRANULARITY_GAP", "SEMANTIC_GAP", "BUSINESS_LOGIC_GAP",
        "EXTRACTION_GAP", "SECURITY_GAP", "VERSION_GAP", "PRODUCT_NOT_AVAILABLE", "CATALOG_UNVERIFIED")
DECISIONS = ("REUSE_STANDARD", "KEY_USER_EXTENSION", "DEVELOPER_EXTENSION", "DATA_PRODUCT_EXTENSION",
             "CREATE_CUSTOMER_MANAGED_PRODUCT", "DATASPHERE_ENRICHMENT", "BW_DATA_PRODUCT_ROUTE", "MANUAL_BUSINESS_RULE",
             "CATALOG_REVIEW_REQUIRED", "EXECUTION_BLOCKED")

CCY_DECIMALS = {"INR": 2, "USD": 2, "EUR": 2, "JPY": 0}
# Synthetic fixed rates to local company-code currency INR (illustrative only, not market data).
FX_TO_INR = {"INR": Decimal("1"), "USD": Decimal("83.00"), "EUR": Decimal("90.00")}


def D(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def qccy(x: Any, ccy: str) -> Decimal:
    """Quantize to the currency's decimals using ROUND_HALF_UP."""
    n = CCY_DECIMALS.get(ccy, 2)
    return D(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)


def qqty(x: Any) -> Decimal:
    return D(x).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def dec_str(x: Any) -> str:
    return format(D(x), "f")


@dataclass
class Field_:
    name: str
    type: str = "CHAR"
    length: int = 10
    decimals: int = 0
    key: bool = False
    custom: bool = False
    currency_ref: str | None = None
    unit_ref: str | None = None


@dataclass
class SapObject:
    system: str
    client: str
    name: str
    obj_type: str  # CDS_INTERFACE_VIEW, CDS_COMPOSITE_VIEW, CUBE, QUERY, DDIC_TABLE, ODP_DATASOURCE, ADSO, ...
    release: str
    api_state: str = "UNKNOWN"  # RELEASED / NOT_RELEASED / UNKNOWN (never inferred from the name)
    domain: str = "UNKNOWN"
    fields: list[Field_] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    grain: str = "UNKNOWN"
    associations: list[dict] = field(default_factory=list)  # {target, cardinality}
    depends_on: list[str] = field(default_factory=list)  # "NAME" (same system) or "SYS:NAME"
    currency_refs: list[str] = field(default_factory=list)
    measures: list[dict] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    authorization: list[str] = field(default_factory=list)
    extraction: dict = field(default_factory=lambda: {"initial": False, "delta": False, "mechanism": "UNKNOWN"})
    custom_fields: list[str] = field(default_factory=list)
    evidence: str = "SYNTHETIC_FIXTURE"
    discovered_at: str = "2026-11-26T00:00:00Z"
    group: str = ""

    @property
    def id(self) -> str:
        return f"{self.system}:{self.name}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d


def resolve_dependencies(objects: dict[str, SapObject], roots: list[str], max_depth: int = 8, max_nodes: int = 500) -> dict:
    """Bounded recursive dependency resolution with cycle detection and explicit unresolved reporting.

    `objects` is keyed by object id "SYS:NAME". Dependencies resolve within the same system unless written "SYS:NAME".
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    cycles: list[list[str]] = []
    unresolved: list[dict] = []
    truncated = False

    def qualify(owner: SapObject, dep: str) -> str:
        return dep if ":" in dep else f"{owner.system}:{dep}"

    def visit(oid: str, depth: int, path: list[str]) -> None:
        nonlocal truncated
        if oid in path:
            cyc = path[path.index(oid):] + [oid]
            if cyc not in cycles:
                cycles.append(cyc)
            return
        if oid in nodes:
            nodes[oid]["depth"] = min(nodes[oid]["depth"], depth)
            return
        if len(nodes) >= max_nodes:
            truncated = True
            return
        obj = objects.get(oid)
        if obj is None:
            nodes[oid] = {"id": oid, "depth": depth, "resolved": False}
            return
        nodes[oid] = {"id": oid, "depth": depth, "resolved": True, "type": obj.obj_type, "system": obj.system,
                      "evidence": obj.evidence, "group": obj.group}
        if depth >= max_depth:
            if obj.depends_on:
                truncated = True
            return
        for dep in obj.depends_on:
            did = qualify(obj, dep)
            edges.append({"from": oid, "to": did})
            if did not in objects:
                unresolved.append({"object": did, "required_by": oid, "reason": "NOT_IN_DISCOVERED_METADATA"})
            visit(did, depth + 1, path + [oid])

    for r in roots:
        if r not in objects:
            unresolved.append({"object": r, "required_by": "ROOT", "reason": "NOT_IN_DISCOVERED_METADATA"})
            nodes.setdefault(r, {"id": r, "depth": 0, "resolved": False})
        else:
            visit(r, 0, [])
    seen = set()
    uniq_unres = []
    for u in unresolved:
        k = (u["object"], u["required_by"])
        if k not in seen:
            seen.add(k)
            uniq_unres.append(u)
    uniq_edges = [dict(t) for t in {tuple(sorted(e.items())) for e in edges}]
    uniq_edges.sort(key=lambda e: (e["from"], e["to"]))
    return {"roots": roots, "nodes": nodes, "edges": uniq_edges, "cycles": cycles, "unresolved": uniq_unres,
            "truncated": truncated, "max_depth": max_depth, "max_nodes": max_nodes}
