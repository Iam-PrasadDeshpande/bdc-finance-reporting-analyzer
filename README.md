# BDC Finance Reporting Transition Analyzer

An independent assessment prototype showing how an architect can decide, with evidence rather than assumptions, whether
an existing SAP S/4HANA Finance report can move to SAP Business Data Cloud (BDC) managed data products and SAP Datasphere
content: **reuse** delivered content, **extend** Datasphere modeling, build a **customer-managed** data product, or
**retain** the existing report.

## What the site contains
- **Vision & Approach** (home): the transition problem and the seven-step process
  Discover → Understand → Identify BDC products → Map semantics → Validate → Reconcile → Recommend.
- **AR Aging Scenario**: an interactive *method demonstration* on **synthetic** data. It compares a source report
  definition with a candidate target definition, reconciles the results and quantifies the Finance decisions behind any
  difference (key date, company code, aging buckets, ledger, aging basis, special G/L, JSON export).
- **Architecture**, **Evidence & Limitations**, **Methodology**.

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
