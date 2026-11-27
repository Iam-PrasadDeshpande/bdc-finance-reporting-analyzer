"""Adapter layer: how the agents would get live evidence from each system, and what makes multi-system comparison hard.

Nothing here connects to anything. The registry is a PROPOSED DESIGN derived from the scenario topology: one read-only adapter per system, a common
contract, the evidence each would return, and the cross-system rules that make a comparison valid. Every adapter is NOT CONFIGURED in this build
(see catalog.UnavailableAdapter for the catalog adapters that report UNAVAILABLE).
"""
from __future__ import annotations

BADGE = "PROPOSED DESIGN - NO ADAPTER IS CONFIGURED IN THIS BUILD"
CONTRACT = [
    ("describe()", "Capabilities, system id, client, release and the authority granted (read only). Used to decide which stages can run live."),
    ("read_metadata(scope)", "Objects, fields (with the custom flag), keys, associations, extraction capability, release state. Returns records tagged with an evidence class."),
    ("read_catalog()", "Data-product catalog and tenant state (installed, entitled, activated) for BDC and Datasphere; completeness declared or UNKNOWN."),
    ("read_aggregate(query)", "Aggregated figures for reconciliation (never document-level personal data), with scope, key date and timestamp."),
    ("(no write method)", "There is no write, activate, transport or deploy operation in the contract. Changes go through the approval queue and a separately authorized executor (P3, not built)."),
]
PROVENANCE = "Every returned record carries system id, client, release, read timestamp, adapter version and a content hash, so a result can be traced and re-run."
SPECS = {
    "ECC": ("SAP backend metadata adapter", "ADT / DDIC and ODP metadata services; approved reporting reads", ["Object and field metadata", "Custom-field and customer-object flags", "ODP data source list", "Aggregated FI and procurement figures"], "1 find the delta; 4 reconcile"),
    "S4": ("SAP backend metadata adapter", "ADT metadata services (CDS, DDIC, released-object lists); approved reporting reads", ["Object and field metadata", "Custom-field and customer-object flags", "Released API state", "Aggregated figures (ACDOCA based)"], "1 find the delta; 4 reconcile"),
    "CFIN": ("Central Finance adapter", "ADT metadata plus replication and mapping configuration reads", ["FI replication scope per company code", "Mapping tables (supplier, company code, G/L)", "Aggregated replicated FI figures"], "4 reconcile (source to Central Finance)"),
    "BW": ("BW metadata adapter", "BW modelling metadata (ADSO, queries) and reference-output reads", ["ADSO and query metadata", "Transformation logic references", "Reference report output (aggregated)"], "1 find the delta (logic); 4 reconcile (BW to BDC)"),
    "BDC": ("BDC catalog adapter", "Business Accelerator Hub and tenant data-product catalog", ["Full catalog from skip=0 with the total recorded", "Installed / entitled / activated state", "Data-product contracts (CSN) when available"], "1 find the delta (product side); 2 solution"),
    "DATASPHERE": ("Datasphere adapter", "Datasphere repository and object metadata (spaces, connections, flows, models)", ["Spaces and connections", "Replication flows and their state", "Models, views and deployment status"], "3 Datasphere activities; 4 reconcile"),
    "DATABRICKS": ("Consumer adapter (optional)", "Downstream read of exposed data products", ["Shared data products", "Consumption status"], "5 end-to-end result (optional)"),
}
CHALLENGES = [
    ("Identity and access", "Each system has its own identity provider, roles and approval path; read access must be granted per system, least privilege, by the customer."),
    ("Network zones", "Systems sit in different zones (private cloud, on premise, cloud tenants); connectivity needs customer-approved gateways such as Cloud Connector."),
    ("Release differences", "ECC 6.0, S/4HANA 2022 and 2023 and Central Finance expose different metadata shapes and released-object sets; adapters must normalise without guessing."),
    ("System-qualified keys", "Document numbers repeat across systems and clients; every key must carry system and client, or a duplicate will look like a match."),
    ("Source of truth for FI", "Exactly one authoritative FI source per company code (source or Central Finance); source and replicated FI are never summed."),
    ("Time alignment", "Source and BDC extracts must use the same scope, period and key date, with timestamps, or reconciliation differences are meaningless."),
    ("Data protection", "Reconciliation uses aggregated figures only; no document-level personal data leaves a system."),
    ("Evidence class", "A live read upgrades evidence only for that system, client and moment; it never upgrades another system or a later date."),
]


def registry(res: dict, scn: str) -> list[dict]:
    systems = res["scenarios"][scn]["topology"]["systems"]
    rows = []
    for sid, v in systems.items():
        name, iface, returns, stages = SPECS.get(v["type"], ("Adapter", "to be defined", [], "-"))
        rows.append({"system": sid, "type": v["type"], "release": v["release"], "adapter": name, "interface (proposed)": iface, "operations": "read only",
                     "returns when connected": "; ".join(returns), "used in": stages, "status": "NOT CONFIGURED",
                     "customer must provide": "read role, network path, approval, owner contact"})
    return rows


PLANNER_CONTRACT = [
    ("Input", "The plain request plus the allowlist of typed tools (name, authority, input schema). Tool output is data, never instructions."),
    ("Output", "A plan: intent, lead agent and an ordered list of tool names. Nothing else."),
    ("Validation (deterministic, outside the model)", "Every tool must exist; every tool authority must be allowed (read, read simulated, local draft, draft only); write-like requests are refused first; "
                                                      "an unrecognised plan executes nothing."),
    ("Demo planner", "Deterministic, so every answer is reproducible and testable (golden transaction, injected defects, routing table). It is the planner used in this build."),
    ("LLM planner", "Not configured. It would replace only the planning step behind the same contract and the same validation; tools, authority gates, approvals and the audit trail stay in deterministic code."),
]
