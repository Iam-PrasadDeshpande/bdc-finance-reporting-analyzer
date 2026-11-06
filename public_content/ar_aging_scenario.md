### About this demonstration

**Status:** synthetic method demonstration. Matching definitions reconcile at **SYNTHETIC_PASS**. Real Finance assessment: **HOLD / INSUFFICIENT_EVIDENCE**.

**Purpose.** Show how the analyzer compares the definition behind an existing SAP S/4HANA Accounts Receivable aging report with a candidate SAP Business Data Cloud definition, reconciles the results, and makes the Finance decisions behind any difference visible.

**What you can change**
- Key date, company code (synthetic) and aging bucket limits.
- The candidate target definition: ledger, aging basis (net due date, or posting date + 30 days), and inclusion of special G/L items.

**How it works**
1. A generated, synthetic ledger of AR items covers:
   - invoices and partial payments;
   - credit memos and special G/L items;
   - items cleared before or after the key date, and items posted after it;
   - two ledgers and two company codes.
2. Two differently structured extracts are produced from it: a *source report extract* and a *target model extract*. Both come from one generated ledger, so their independence is simulated.
3. The **source** side applies the reference definition:
   - an item is open at the key date if it was posted on or before it and not cleared, or cleared after it;
   - aging by net due date, primary ledger, special G/L items excluded.
4. The **target** side applies the definition you select.
5. Results are reconciled only when both sides share the same business context. A different definition is reported as **BLOCKED** (not comparable), with the size of the difference shown as a Finance sensitivity.

**Provenance of the rules.** The rules are general accounts-receivable practice and come from this project's own artefacts, all written before any SAP Business Data Cloud content was reviewed:
- the reconciliation component;
- the AR Aging requirements;
- the Finance-owner decision list.

The demonstration does **not** implement, reproduce or approximate SAP-delivered BDC or Datasphere content.

**What it does not show**
- any customer's report behaviour or compatibility;
- SAP product availability, entitlement or release compatibility;
- the results of an SAP-delivered analytical model.

An internal proof of concept against SAP-delivered content exists but is not published.

**To move beyond HOLD**
1. Finance-owner decisions.
2. Authorized customer S/4HANA metadata.
3. Data products available in the customer BDC tenant.
4. Reconciliation of independent, aggregated runtime figures from both systems.

*Independent assessment prototype, not affiliated with SAP. All figures are synthetic.*
