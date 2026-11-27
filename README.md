# BDC Finance Reporting Transition Analyzer

An independent assessment prototype showing how an architect can decide, with evidence rather than assumptions, whether
an existing SAP S/4HANA Finance report can move to SAP Business Data Cloud (BDC) managed data products and SAP Datasphere
content: **reuse** delivered content, **extend** Datasphere modeling, build a **customer-managed** data product, or
**retain** the existing report.

## What the site contains
- **Agent Suite** (default page): a synthetic-only agent cockpit for multi-object, multi-system SAP transition scenarios.
  Home "Ask the transition agents" (scenario, request, example chips), then three spaces: **Workbench apps** (14 apps from
  object discovery and the dependency graph to Finance reconciliation and release gates), **Agents** (23 agents in five
  families with typed tools; write requests are refused and turned into a draft-only proposal) and **Architecture &
  operations** (live run, complete architecture options, hosting, registry, selection, decision brief, ontology, diagrams).
  Three themes (SAP Quartz Light, Quartz Dark, Horizon Light). Scenario A is a single S/4HANA system; Scenario B is a
  multi-system landscape with Central Finance.
- **Old demo** (Menu -> Old demo, `?view=old-demo`): the earlier v0.12 analyzer on one page - Vision & Approach, AR Aging
  Scenario (interactive *method demonstration* on **synthetic** data), Architecture, Evidence & Limitations, Methodology.

## Restrictions and validation limits
- All figures are **SYNTHETIC**. `SYNTHETIC_PASS` means two calculations agree on generated data under the same
  definition. It is not a customer reconciliation and says nothing about compatibility.
- Real Finance assessment status: **HOLD / INSUFFICIENT_EVIDENCE**.
- The demonstration uses project-authored rules. It does not implement or reproduce SAP-delivered BDC or Datasphere
  content. No SAP system is connected; no customer, tenant or authentication data is used.

## Run
- Streamlit Community Cloud entrypoint: `app.py` (Python 3.12).
- Locally: `pip install -r requirements.txt` then `streamlit run app.py`.

## Attribution and licensing status
SAP, SAP S/4HANA, SAP Business Data Cloud, SAP Datasphere and other SAP products and services mentioned are trademarks
or registered trademarks of SAP SE (or an SAP affiliate company) in Germany and other countries. This project is not
sponsored, endorsed or affiliated with SAP SE. Object names cited on the site come from public SAP Help documentation.

No open-source licence is granted. The source is published for viewing; all rights are reserved by the author unless a
LICENSE file is added.

## v0.13 - Agent Suite (synthetic)

The **Agent Suite** section adds an orchestrated set of specialist agents (discovery, gap and decision, engineering, reconciliation, governance) over two synthetic scenarios: a single S/4HANA system and a multi-system landscape with Central Finance. Agents read persisted synthetic results or draft locally; none can write to SAP. It also shows proposed architecture options, an ontology and a live replay of the orchestrator trace.

- All data, system ids, objects and product ids are **synthetic**. No SAP, BDC or Datasphere system is connected (mode: DEMO).
- Synthetic success (SYNTHETIC_PASS) is not a live Finance validation. Live SAP validation, live BDC validation and Finance validation remain **HOLD / INSUFFICIENT_EVIDENCE**.
