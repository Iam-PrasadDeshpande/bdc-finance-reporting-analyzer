"""Pluggable data-product catalog discovery with evidence classification.

Sources: Business Accelerator Hub metadata, BDC cockpit metadata, approved imports, verified snapshots, synthetic fixtures.
Only the import and fixture sources work offline; the Hub and cockpit adapters report UNAVAILABLE until a verified
interface is configured. A product absent from an accessible catalog is UNKNOWN unless completeness is established.
"""
from __future__ import annotations

from typing import Any

from .core import EVIDENCE, VERIFIED_EVIDENCE


class CatalogError(ValueError):
    pass


def validate_product(p: dict) -> list[str]:
    """Return problems. SAP-managed product ids are never invented: a verified class needs provenance."""
    errs = []
    if p.get("evidence") not in EVIDENCE:
        errs.append(f"evidence class {p.get('evidence')!r} not in {EVIDENCE}")
    if p.get("evidence") in ("PUBLISHED_VERIFIED", "TENANT_VERIFIED"):
        if not p.get("product_id"):
            errs.append("verified evidence requires a product_id")
        if not str(p.get("source_reference_url", "")).startswith("https://"):
            errs.append("verified evidence requires an https source_reference_url")
        if not p.get("last_verified"):
            errs.append("verified evidence requires last_verified")
    if p.get("evidence") == "SYNTHETIC_FIXTURE" and not str(p.get("product_id", "")).startswith("SIM_"):
        errs.append("synthetic fixture product ids must start with SIM_")
    return errs


class Catalog:
    def __init__(self, snapshot: dict):
        bad = {p.get("product_id", "?"): validate_product(p) for p in snapshot.get("products", [])}
        bad = {k: v for k, v in bad.items() if v}
        if bad:
            raise CatalogError(f"invalid catalog products: {bad}")
        self.snapshot = snapshot
        self.products = {p["product_id"]: p for p in snapshot["products"]}

    # evidence ---------------------------------------------------------------------------------------------------------
    def effective_evidence(self, product: dict, mode: str) -> str:
        """SYNTHETIC_FIXTURE content may drive decisions in DEMO only; elsewhere it is not usable evidence."""
        ev = product.get("evidence", "UNKNOWN")
        if ev == "SYNTHETIC_FIXTURE" and mode != "DEMO":
            return "UNKNOWN"
        return ev

    def usable(self, product: dict, mode: str) -> bool:
        ev = self.effective_evidence(product, mode)
        return ev in VERIFIED_EVIDENCE or (ev == "SYNTHETIC_FIXTURE" and mode == "DEMO")

    def domain_complete(self, domain: str) -> bool:
        return bool(self.snapshot.get("domain_completeness", {}).get(domain))

    # lookup -----------------------------------------------------------------------------------------------------------
    def find(self, group: str) -> list[tuple[dict, dict]]:
        out = []
        for pid in sorted(self.products):
            p = self.products[pid]
            for e in p["entities"]:
                if group in e["covers_objects"]:
                    out.append((p, e))
        return out

    @staticmethod
    def availability(p: dict) -> dict:
        """The seven distinct availability dimensions; none implies another."""
        return {k: p.get(k, "UNKNOWN") for k in ("published_availability", "tenant_availability", "entitlement",
                                                 "technical_compatibility", "activation", "installation", "consumption")}


def from_import(payload: dict) -> Catalog:
    """Approved metadata import. Evidence classes are taken from the payload and validated, never upgraded."""
    if "products" not in payload:
        raise CatalogError("import must contain 'products'")
    return Catalog(payload)


class UnavailableAdapter:
    """Hub / BDC cockpit adapters: no verified interface is configured in this build, so they never return data."""

    def __init__(self, name: str):
        self.name = name

    def fetch(self) -> dict[str, Any]:
        return {"source": self.name, "status": "UNAVAILABLE", "reason": "no verified interface configured; "
                "use an approved metadata import or the synthetic fixture", "products": []}


HUB_ADAPTER = UnavailableAdapter("SAP Business Accelerator Hub")
COCKPIT_ADAPTER = UnavailableAdapter("SAP BDC Cockpit")
