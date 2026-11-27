"""BDC Finance Reporting Transition Analyzer — public Vision & Approach page.

Integrated 2026-11-06 from BDC_Public_Home_Integration_Kit.zip (sha256 a2ce0238...); adapted: explicit vision/problem/
target/decision block, SYNTHETIC_PASS vs HOLD wording, scenario figures supplied by the host engine (not hardcoded).

Integration component only. Does not load SAP/private evidence or call services.
Requires Streamlit in the host app. This file is unsigned and not release-ready.

Usage inside the existing app, after its authoritative routing has been inspected:
    from public_home import render_vision_home
    if section == "Vision & Approach":
        desired_page = render_vision_home()
        if desired_page:
            st.session_state["_bdc_requested_page"] = desired_page
            st.rerun()

The host must apply _bdc_requested_page BEFORE creating its navigation widget.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

PUBLIC_SECTIONS = (
    "Vision & Approach",
    "AR Aging Scenario",
    "Architecture",
    "Evidence & Limitations",
    "Methodology",
)

CSS = r"""
<style>
.bdc-home{--ink:#163145;--muted:#53697b;--line:#dfebef;--teal:#14796f;--soft:#e8f4f1;--paper:#fff;
font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:var(--ink)}
.bdc-home *, .bdc-home *::before, .bdc-home *::after{box-sizing:border-box}
.bdc-home .eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:.7rem;font-weight:800;color:#367b78}
.bdc-home h1{font-size:clamp(2.05rem,3.5vw,3.65rem);line-height:1.13;letter-spacing:-.045em;
margin:.65rem 0 .9rem;color:#122c3c;max-width:880px}
.bdc-home h2{font-size:clamp(1.35rem,2.1vw,1.9rem);letter-spacing:-.025em;margin:.25rem 0 1.2rem;color:#17374a}
.bdc-home h3{font-size:1.02rem;margin:.45rem 0 .55rem;color:#19394a}
.bdc-home p{line-height:1.63;margin:.4rem 0 0;color:#53697b}
.bdc-home .lead{max-width:830px;font-size:1.1rem;line-height:1.65;color:#39576a}
.bdc-home .hero{padding:2.15rem 2.25rem;background:linear-gradient(115deg,#f4faf8,#f4f8fc 70%,#fff);
border:1px solid #dbe9e8;border-radius:19px;margin-bottom:.5rem}
.bdc-home .flags{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:1.25rem}
.bdc-home .flag{font-size:.73rem;font-weight:750;padding:.35rem .65rem;border-radius:99px;background:#e4f4ef;color:#0f6d5b}
.bdc-home .flag.amber{background:#fff0d8;color:#875a21}
.bdc-home .section{margin:2.3rem 0}
.bdc-home .grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}
.bdc-home .grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}
.bdc-home .card{background:#fff;border:1px solid var(--line);padding:1.35rem 1.4rem;border-radius:14px;
box-shadow:0 5px 22px rgba(21,53,69,.035)}
.bdc-home .card.source{border-top:4px solid #5686a3}
.bdc-home .card.target{border-top:4px solid #17776c}
.bdc-home .muted{font-size:.8rem;color:#6a7c88}
.bdc-home .code{font:600 .85rem ui-monospace,SFMono-Regular,Consolas,monospace;color:#214d5b;overflow-wrap:anywhere}
.bdc-home ul{padding-left:1.2rem;color:#4e6675;line-height:1.9;margin:.75rem 0 0}
.bdc-home .bridge{text-align:center;max-width:100%;margin:.8rem 0;color:#2d726e;font-size:.9rem;font-weight:800}
.bdc-home .stepnum{font:.78rem ui-monospace,Consolas,monospace;color:#2d8174;font-weight:800}
.bdc-home .rule{border-left:4px solid #2b8474;background:#edf6f3;padding:1.1rem 1.3rem;border-radius:0 12px 12px 0;
font-size:1.1rem;font-weight:750;line-height:1.5;color:#204c48}
.bdc-home .outcomes{display:flex;flex-wrap:wrap;gap:.6rem;margin:.85rem 0 .35rem}
.bdc-home .outcome{padding:.5rem .78rem;border:1px solid #d9e9e7;border-radius:9px;background:#f5faf8;
font-size:.8rem;font-weight:760;color:#28685e}
.bdc-home .caption{font-size:.76rem;color:#637788;margin-top:.6rem}
.bdc-home .note{padding:1rem 1.25rem;border:1px solid #ead7b3;background:#fff7e8;color:#815a26;border-radius:12px;
font-size:.86rem;line-height:1.6;margin-top:1.1rem}
.bdc-home .statline{display:flex;gap:.65rem;flex-wrap:wrap;margin-top:1rem}
.bdc-home .stat{border:1px solid #dce9e8;background:#fff;border-radius:9px;padding:.57rem .75rem;font-size:.82rem;font-weight:760}
.bdc-home .stat strong{color:#12695e}
.bdc-home .foot{font-size:.78rem;color:#687f88;border-top:1px solid #dce8eb;padding:1.25rem 0;margin-top:2rem}
@media(max-width:780px){.bdc-home .hero{padding:1.3rem}.bdc-home .grid2,.bdc-home .grid3{grid-template-columns:1fr}
.bdc-home .section{margin:1.7rem 0}.bdc-home .lead{font-size:1rem}}
</style>
"""


def _scenario_stats(summary: Optional[dict]) -> str:
    """Headline AR Aging figures. Values come from the host's calculation engine; none are hardcoded here."""
    if not summary:
        return '<div class="statline"><div class="stat">Scenario figures: see the AR Aging page</div><div class="stat">Finance <strong>HOLD</strong></div></div>'
    if summary.get("public"):
        return ('<div class="statline">'
                f'<div class="stat"><strong>{summary["company_codes"]}</strong> synthetic company codes</div>'
                f'<div class="stat">Matching definitions: <strong>{summary["status"]}</strong></div>'
                f'<div class="stat"><strong>{summary["sensitivities"]}</strong> Finance sensitivities quantified</div>'
                '<div class="stat">All figures <strong>SYNTHETIC</strong></div>'
                '<div class="stat">Finance <strong>HOLD</strong></div></div>')
    return ('<div class="statline">'
            f'<div class="stat"><strong>{summary["company_codes"]}</strong> synthetic company codes</div>'
            f'<div class="stat"><strong>{summary["bucket_agreement"]}</strong> bucket agreement per code</div>'
            f'<div class="stat">Result <strong>{summary["status"]}</strong></div>'
            f'<div class="stat"><strong>{summary["inferred_logic_components"]}</strong> logic components inferred</div>'
            '<div class="stat">Finance <strong>HOLD</strong></div></div>')


def render_vision_home(summary: Optional[dict] = None) -> Optional[str]:
    """Render the default public homepage. Return a route request on CTA clicks.

    Does not touch the host app's navigation state, evidence, or calculations.
    Host handles the returned route before recreating its navigation widget.
    `summary` is optional engine output (company_codes, bucket_agreement, status, inferred_logic_components).
    """
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('''
<div class="bdc-home">
  <section class="hero" aria-label="Product vision">
    <div class="eyebrow">Finance architecture · Evidence-led decision support</div>
    <h1>Move Finance reporting to BDC with evidence, not assumptions.</h1>
    <p class="lead">Understand whether an existing SAP S/4HANA Finance report can be reproduced using SAP Business Data Cloud managed data products and Datasphere analytical content—without silently changing what Finance measures.</p>
    <div class="flags"><span class="flag">Technical ingestion demonstrated</span>
      <span class="flag">AR Aging synthetic demonstration: SYNTHETIC_PASS</span>
      <span class="flag amber">Real Finance assessment: HOLD / INSUFFICIENT_EVIDENCE</span></div>
  </section>
</div>''', unsafe_allow_html=True)

    left, right, _ = st.columns([1.3, 1.3, 2])
    with left:
        to_process = st.button("How the analyzer works", key="bdc_home_process", use_container_width=True)
    with right:
        to_scenario = st.button("Explore AR Aging scenario", key="bdc_home_scenario", type="primary", use_container_width=True)
    if to_scenario:
        return "AR Aging Scenario"
    if to_process:
        return "Methodology"

    st.markdown('''
<div class="bdc-home">
  <section class="section" aria-label="Vision, problem, target and decision">
    <div class="grid2">
      <article class="card"><div class="eyebrow">Vision</div><h3>Evidence, not assumptions</h3>
        <p>Move Finance reporting to BDC with evidence, not assumptions.</p></article>
      <article class="card"><div class="eyebrow">Business problem</div><h3>Reports carry hidden business logic</h3>
        <p>Customers have existing S/4HANA Finance reports with business calculations, configuration and custom logic that a target platform must reproduce.</p></article>
      <article class="card"><div class="eyebrow">Target</div><h3>Delivered content first</h3>
        <p>Evaluate SAP-managed BDC data products and delivered Datasphere content before recommending additional custom modeling.</p></article>
      <article class="card"><div class="eyebrow">Expected decision</div><h3>A justified route</h3>
        <p>Reuse delivered content, extend Datasphere, or build a customer-managed product when justified by evidence—or retain the existing report when evidence is insufficient.</p></article>
    </div>
    <div class="rule" style="margin-top:1rem">Analyzer approach: Discover → Understand → Identify BDC products → Map semantics → Validate → Reconcile → Recommend</div>
  </section>
  <section class="section">
    <h2>Two platforms. One Finance definition.</h2>
    <div class="grid2">
      <article class="card source">
        <div class="eyebrow">Existing source · Current landscape</div>
        <h3>SAP S/4HANA PCE</h3>
        <p>Start with the customer’s actual report—not just a CDS name.</p>
        <ul><li>Finance report and business requirements</li>
          <li>Query / CDS / tables and extensions</li>
          <li>Ledger, clearing, due-date and currency semantics</li>
          <li>Owner-approved key-date and aging behavior</li></ul>
      </article>
      <article class="card target">
        <div class="eyebrow">Candidate target · SAP-delivered content</div>
        <h3>SAP Business Data Cloud</h3>
        <p>Evaluate existing governed products and delivered analytical modeling first.</p>
        <ul><li>SAP-managed Finance data products</li>
          <li>SAP-delivered Datasphere content, where licensed</li>
          <li>Entity contracts, joins and calculations</li>
          <li>Report-ready consumption and access controls</li></ul>
      </article>
    </div>
    <div class="bridge">↓ &nbsp; Finance Reporting Transition Analyzer &nbsp; ↓</div>
    <div class="rule">Does the delivered BDC content reproduce the existing Finance report’s meaning and results?</div>
    <div class="outcomes"><span class="outcome">A · Reuse SAP-delivered BDC content</span><span class="outcome">B · Extend SAP Datasphere modeling</span><span class="outcome">C · Customer-managed data product, if justified</span><span class="outcome">D · Retain the existing report</span></div>
    <div class="caption">These are evaluation outcomes, not recommendations already proven for a customer system.</div>
  </section>
  <section class="section">
    <div class="eyebrow">The approach</div>
    <h2>How the analyzer works</h2>
    <div class="grid3">
      <article class="card"><div class="stepnum">01 · DISCOVER</div><h3>Find the real report</h3><p>Identify the report Finance actually uses and trace report → query/CDS → tables.</p></article>
      <article class="card"><div class="stepnum">02 · UNDERSTAND</div><h3>Recover its semantics</h3><p>Capture business calculations, configuration and custom logic, confirmed by the Finance owner.</p></article>
      <article class="card"><div class="stepnum">03 · IDENTIFY BDC PRODUCTS</div><h3>Find candidate content</h3><p>Locate SAP-managed data products and delivered Datasphere content that could carry the report.</p></article>
      <article class="card"><div class="stepnum">04 · MAP SEMANTICS</div><h3>Compare definitions</h3><p>Grain, attributes, ledger, clearing, key date, due dates, buckets and currencies.</p></article>
      <article class="card"><div class="stepnum">05 · VALIDATE</div><h3>Exercise boundary cases</h3><p>Controlled scenarios for credits, partial payments and historical key dates.</p></article>
      <article class="card"><div class="stepnum">06 · RECONCILE</div><h3>Compare real results</h3><p>Authorized source and BDC extracts for the same business scope and tolerances.</p></article>
      <article class="card"><div class="stepnum">07 · RECOMMEND</div><h3>Choose a supported route</h3><p>Reuse, extend, customer-managed product or retain the report—only with traceable evidence.</p></article>
    </div>
  </section>
  <section class="section">
    <div class="eyebrow">Product capabilities</div><h2>From metadata discovery to a defensible transition decision</h2>
    <div class="grid3">
      <article class="card"><h3>Live SAP discovery</h3><p>Read-only DDLS and lineage intake; demonstrated on an ABAP trial, not on customer Finance.</p></article>
      <article class="card"><h3>Product contract ingestion</h3><p>Import and inspect SAP-published CSN entities, types, keys and associations; examples are not current product contracts.</p></article>
      <article class="card"><h3>Finance semantic assessment</h3><p>Separate verified rules, owner assumptions, inferred behavior and missing evidence.</p></article>
      <article class="card"><h3>AR Aging scenario</h3><p>Compare two independent calculations on controlled synthetic cases and business-rule sensitivities.</p></article>
      <article class="card"><h3>Runtime KPI reconciliation</h3><p>Planned customer validation against approved S/4HANA and BDC extracts; not yet performed.</p></article>
      <article class="card"><h3>Evidence-backed recommendation</h3><p>Traceability from requirements to product capability, gaps and proposed transition action.</p></article>
    </div>
  </section>
  <section class="section">
    <div class="eyebrow">Working demonstration</div><h2>Accounts Receivable Aging</h2>
    <div class="card">
      <p>The public demonstration compares an S/4HANA report definition with a candidate BDC definition on <strong>synthetic</strong> data, reconciles the results and quantifies the Finance decisions that change them. It uses project-authored rules; it does not reproduce SAP-delivered content. An internal proof of concept against SAP-delivered content is not published.</p>
      __STATLINE__
      <div class="note"><strong>Evidence boundary:</strong> Synthetic agreement is not customer Finance reconciliation. Exact product schemas, customer S/4HANA evidence, tenant availability and Finance-owner validation remain outstanding.</div>
    </div>
  </section>
  <div class="foot">Independent assessment prototype, not affiliated with SAP. No production or customer Finance equivalence is claimed. Only approved public-safe evidence should be displayed.</div>
</div>
'''.replace("__STATLINE__", _scenario_stats(summary)), unsafe_allow_html=True)
    return None
