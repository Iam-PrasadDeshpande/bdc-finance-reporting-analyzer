"""Scenario A / B configuration, the 20-group Procure-to-Pay discovery inventory, synthetic object metadata and the
synthetic catalog fixture. ALL system ids, objects and product ids here are SYNTHETIC; none is a verified SAP product id.

Table names (EBAN, EKKO, ...) are discovery reference candidates only; released CDS views and extraction mechanisms
must come from source-system metadata, so synthetic objects here carry evidence=SYNTHETIC_FIXTURE.
"""
from __future__ import annotations

from .core import Field_, SapObject

# ---- field typing helpers -------------------------------------------------------------------------------------------
_T = {"MENGE": ("QUAN", 13, 3), "WEMNG": ("QUAN", 13, 3), "NETPR": ("CURR", 11, 2), "NETWR": ("CURR", 13, 2),
      "WRBTR": ("CURR", 13, 2), "DMBTR": ("CURR", 13, 2), "RMWWR": ("CURR", 13, 2), "PREIS": ("CURR", 11, 2),
      "HSL": ("CURR", 23, 2), "KSL": ("CURR", 23, 2), "BUDAT": ("DATS", 8, 0), "BEDAT": ("DATS", 8, 0),
      "BADAT": ("DATS", 8, 0), "BLDAT": ("DATS", 8, 0), "EINDT": ("DATS", 8, 0), "AUGDT": ("DATS", 8, 0),
      "BNFPO": ("NUMC", 5, 0), "EBELP": ("NUMC", 5, 0), "BUZEI": ("NUMC", 3, 0), "ZEILE": ("NUMC", 4, 0),
      "DOCLN": ("CHAR", 6, 0), "GJAHR": ("NUMC", 4, 0), "MJAHR": ("NUMC", 4, 0), "MONAT": ("NUMC", 2, 0),
      "VPROZ": ("DEC", 5, 2), "PEINH": ("DEC", 5, 0), "NAME1": ("CHAR", 35, 0)}
_CURR_REF = {"CURR": "WAERS"}
_UNIT_REF = {"QUAN": "MEINS"}


def _fields(names: str, keys: list[str], custom: tuple[str, ...] = ()) -> list[Field_]:
    out = []
    for n in names.split():
        t, ln, dc = _T.get(n, ("CHAR", 10, 0))
        out.append(Field_(n, t, ln, dc, key=n in keys, custom=n in custom,
                          currency_ref=_CURR_REF.get(t),
                          unit_ref=_UNIT_REF.get(t)))
    return out


# group id -> (label, table, keys, grain, fields, depends(groups), domain, delta_needed, auth_objects)
GROUPS: dict[str, dict] = {
    "PR": dict(n=1, label="Purchase requisition", table="EBAN", keys=["BANFN", "BNFPO"], grain="PR item",
               f="BANFN BNFPO MATNR MENGE MEINS PREIS WAERS WERKS BADAT LOEKZ", dep=["MAT"], dom="PROCUREMENT",
               auth=["M_BANF_WRK"]),
    "PRACC": dict(n=2, label="PR account assignment", table="EBKN", keys=["BANFN", "BNFPO", "ZEBKN"],
                  grain="PR account assignment", f="BANFN BNFPO ZEBKN KOSTL SAKTO WRBTR WAERS", dep=["PR"],
                  dom="PROCUREMENT", auth=["M_BANF_WRK"]),
    "POH": dict(n=3, label="Purchase order header", table="EKKO", keys=["EBELN"], grain="PO header",
                f="EBELN BUKRS LIFNR BSART BEDAT WAERS EKORG", dep=["BP"], dom="PROCUREMENT", auth=["M_BEST_EKO"]),
    "POI": dict(n=4, label="Purchase order item", table="EKPO", keys=["EBELN", "EBELP"], grain="PO item",
                f="EBELN EBELP MATNR MENGE MEINS NETPR PEINH NETWR WAERS WERKS ELIKZ ZZ_SAFETY_CLASS", dep=["POH", "MAT", "PR"],
                dom="PROCUREMENT", auth=["M_BEST_EKO", "M_BEST_WRK"], custom=("ZZ_SAFETY_CLASS",)),
    "POACC": dict(n=5, label="PO account assignment", table="EKKN", keys=["EBELN", "EBELP", "ZEKKN"],
                  grain="PO account assignment", f="EBELN EBELP ZEKKN KOSTL SAKTO VPROZ WRBTR WAERS", dep=["POI"],
                  dom="PROCUREMENT", auth=["M_BEST_EKO"], sem={"amount_basis": "DOCUMENT_CURRENCY"}),
    "POSCH": dict(n=6, label="PO schedule line", table="EKET", keys=["EBELN", "EBELP", "ETENR"], grain="PO schedule line",
                  f="EBELN EBELP ETENR EINDT MENGE WEMNG MEINS", dep=["POI"], dom="PROCUREMENT", auth=["M_BEST_EKO"]),
    "POHIST": dict(n=7, label="PO history", table="EKBE", keys=["EBELN", "EBELP", "VGABE", "GJAHR", "BELNR", "BUZEI"],
                   grain="PO history document item",
                   f="EBELN EBELP VGABE GJAHR BELNR BUZEI MENGE MEINS DMBTR WRBTR WAERS BUDAT SHKZG", dep=["POI"],
                   dom="PROCUREMENT", auth=["M_BEST_EKO"]),
    "MATDOC": dict(n=8, label="Material document / goods receipt", table="MATDOC", keys=["MBLNR", "MJAHR", "ZEILE"],
                   grain="Material document item", f="MBLNR MJAHR ZEILE EBELN EBELP MENGE MEINS DMBTR BUDAT SHKZG",
                   dep=["POI"], dom="PROCUREMENT", auth=["M_MSEG_WWA"]),
    "INVH": dict(n=9, label="Supplier invoice header", table="RBKP", keys=["BELNR", "GJAHR"], grain="Invoice header",
                 f="BELNR GJAHR BUKRS LIFNR RMWWR WAERS BLDAT BUDAT", dep=["BP"], dom="PROCUREMENT", auth=["M_RECH_BUK"]),
    "INVI": dict(n=10, label="Supplier invoice item", table="RSEG", keys=["BELNR", "GJAHR", "BUZEI"], grain="Invoice item",
                 f="BELNR GJAHR BUZEI EBELN EBELP MENGE MEINS WRBTR WAERS MWSKZ", dep=["INVH", "POI"],
                 dom="PROCUREMENT", auth=["M_RECH_BUK"]),
    "BKPF": dict(n=11, label="Accounting document header", table="BKPF", keys=["BUKRS", "BELNR", "GJAHR"],
                 grain="Accounting document header", f="BUKRS BELNR GJAHR BLART BUDAT MONAT WAERS XBLNR",
                 dep=["INVH", "MATDOC"], dom="FINANCE", auth=["F_BKPF_BUK"]),
    "BSEG": dict(n=12, label="Entry-view accounting line items", table="BSEG", keys=["BUKRS", "BELNR", "GJAHR", "BUZEI"],
                 grain="Accounting line item", f="BUKRS BELNR GJAHR BUZEI HKONT LIFNR WRBTR DMBTR SHKZG AUGBL",
                 dep=["BKPF"], dom="FINANCE", auth=["F_BKPF_BUK"]),
    "ACDOCA": dict(n=13, label="Universal Journal", table="ACDOCA", keys=["RLDNR", "RBUKRS", "GJAHR", "BELNR", "DOCLN"],
                   grain="Journal entry line", f="RLDNR RBUKRS GJAHR BELNR DOCLN RACCT HSL KSL RHCUR RKCUR DRCRK POPER",
                   dep=["BKPF"], dom="FINANCE", auth=["F_BKPF_BUK"]),
    "SUPOI": dict(n=14, label="Supplier open and cleared items", table="BSIK/BSAK",
                  keys=["BUKRS", "LIFNR", "BELNR", "GJAHR"], grain="Supplier open item",
                  f="BUKRS LIFNR BELNR GJAHR WRBTR WAERS AUGDT AUGBL", dep=["BSEG"], dom="FINANCE", auth=["F_LFA1_BUK"]),
    "PAYCLR": dict(n=15, label="Payment and clearing relationships", table="BSEG/REGUH", keys=["BUKRS", "BELNR", "GJAHR"],
                   grain="Clearing relationship", f="BUKRS BELNR GJAHR AUGBL AUGDT VBLNR", dep=["SUPOI"], dom="FINANCE",
                   auth=["F_LFA1_BUK"], logic=["R-CLEARING-ALLOC-001"]),
    "BP": dict(n=16, label="Supplier and business partner master", table="LFA1/BUT000", keys=["LIFNR"],
               grain="Supplier", f="LIFNR NAME1 LAND1 KTOKK", dep=[], dom="MASTER_DATA",
               auth=["F_LFA1_BUK", "F_LFA1_GEN"]),
    "MAT": dict(n=17, label="Product and material master", table="MARA", keys=["MATNR"], grain="Material",
                f="MATNR MTART MEINS MATKL", dep=[], dom="MASTER_DATA", auth=["M_MATE_WRK"]),
    "GL": dict(n=18, label="G/L account master", table="SKA1/SKAT", keys=["KTOPL", "SAKNR"], grain="G/L account",
               f="KTOPL SAKNR XBILK KTOKS", dep=[], dom="FIN_MASTER", auth=["F_SKA1_BUK"]),
    "CC": dict(n=19, label="Cost center and profit center master", table="CSKS/CEPC", keys=["KOKRS", "KOSTL"],
               grain="Cost center", f="KOKRS KOSTL PRCTR KOSAR", dep=[], dom="FIN_MASTER", auth=["K_CSKS"]),
    "XMAP": dict(n=20, label="Cross-system document and master-data mappings", table="CFIN mapping",
                 keys=["SRC_SYS", "SRC_BUKRS", "SRC_BELNR", "SRC_GJAHR"], grain="Document mapping",
                 f="SRC_SYS SRC_BUKRS SRC_BELNR SRC_GJAHR CFIN_BELNR CFIN_GJAHR", dep=["ACDOCA", "BP"], dom="CROSS_SYSTEM",
                 auth=["F_BKPF_BUK"], alt=["DSP01 mapping tables"]),
}
TRANSACTIONAL = {"PR", "PRACC", "POH", "POI", "POACC", "POSCH", "POHIST", "MATDOC", "INVH", "INVI", "BKPF", "BSEG", "ACDOCA",
                 "SUPOI", "PAYCLR"}


def inventory() -> list[dict]:
    """The 20 logical object groups as discovery reference candidates (not verified released CDS views)."""
    return [{"n": g["n"], "group": gid, "label": g["label"], "reference_table": g["table"], "keys": g["keys"],
             "grain": g["grain"], "domain": g["dom"], "cds_view": "UNRESOLVED - determine from source-system metadata",
             "extraction_mechanism": "UNRESOLVED - determine from source-system metadata",
             "state": "DISCOVERY_REFERENCE_CANDIDATE"} for gid, g in sorted(GROUPS.items(), key=lambda kv: kv[1]["n"])]


# ---- systems --------------------------------------------------------------------------------------------------------
SYSTEMS = {
    "ECC01": dict(type="ECC", release="SAP ECC 6.0 EHP8", client="800", role="Procurement and historical FI transactions",
                  caps=dict(key_user_ext=False, developer_ext=False, odp=True, cds_extraction=False, dpg=False)),
    "S4A": dict(type="S4", release="S/4HANA 2023 FP01 (Private Cloud Edition)", release_family="S4_2023", client="100",
                role="Procurement, inventory and Finance",
                caps=dict(key_user_ext=True, developer_ext=True, odp=True, cds_extraction=True, dpg=False)),
    "S4B": dict(type="S4", release="S/4HANA 2022", release_family="S4_2022", client="200",
                role="Additional procurement and Finance transactions",
                caps=dict(key_user_ext=True, developer_ext=False, odp=True, cds_extraction=True, dpg=False)),
    "CFIN01": dict(type="CFIN", release="S/4HANA 2023 FP01 Central Finance", release_family="S4_2023", client="100",
                   role="Central Finance accounting and mapped financial information",
                   caps=dict(key_user_ext=False, developer_ext=False, odp=True, cds_extraction=True, dpg=False)),
    "BW401": dict(type="BW", release="SAP BW/4HANA 2.0", release_family="BW4_2_0", client="000",
                  role="Existing historical reporting and transformation logic",
                  caps=dict(key_user_ext=False, developer_ext=False, odp=False, cds_extraction=False, dpg=True,
                            dpg_eligibility=dict(version_ok=True, deployment_ok=True, license="UNVERIFIED"))),
    "BDC01": dict(type="BDC", release="n/a", client="-", role="Data product management and consumption", caps={}),
    "DSP01": dict(type="DATASPHERE", release="n/a", client="-", role="Harmonization, transformations and analytical models",
                  caps={}),
    "DBX01": dict(type="DATABRICKS", release="n/a", client="-", role="Optional downstream SAP Databricks consumption",
                  caps={}, optional=True),
}
SYSTEMS["ECC01"]["release_family"] = "ECC_6_0_EHP8"

SCENARIOS = {
    "A": dict(id="A", name="Single SAP system (S/4HANA PCE)", seed=13, systems=["S4A", "BDC01", "DSP01"],
              sources=["S4A"], n_po={"S4A": 100}, company_codes={"S4A": [("1000", "INR")]},
              reporting_roots=["S4A:SIM_Q_P2P_RECON"]),
    "B": dict(id="B", name="Multi-system enterprise landscape", seed=13,
              systems=["ECC01", "S4A", "S4B", "CFIN01", "BW401", "BDC01", "DSP01", "DBX01"],
              sources=["ECC01", "S4A", "S4B"], n_po={"ECC01": 30, "S4A": 40, "S4B": 40},
              company_codes={"ECC01": [("0100", "INR")], "S4A": [("1000", "INR")], "S4B": [("1000", "USD"), ("1100", "INR")]},
              # Which system is authoritative for FI reporting of each (system, company code). Never both.
              fi_authority={("ECC01", "0100"): "ECC01", ("S4A", "1000"): "S4A", ("S4B", "1000"): "CFIN01",
                            ("S4B", "1100"): "S4B"},
              reporting_roots=["S4A:SIM_Q_P2P_RECON", "S4B:SIM_Q_P2P_RECON", "ECC01:SIM_DS_GRIR_FI", "BW401:SIM_Q_GRIR_AP"]),
}

# ---- synthetic object metadata ---------------------------------------------------------------------------------------


def _view_name(gid: str) -> str:
    return "SIM_I_" + GROUPS[gid]["label"].split("/")[0].title().replace(" ", "").replace("-", "")


def _ds_name(gid: str) -> str:
    return f"SIM_DS_{gid}"


def build_objects(sys_id: str) -> dict[str, SapObject]:
    """Synthetic discovered metadata for one source system, keyed by "SYS:NAME"."""
    s = SYSTEMS[sys_id]
    out: dict[str, SapObject] = {}
    if s["type"] == "BW":
        out["BW401:SIM_ADSO_GRIR"] = SapObject("BW401", s["client"], "SIM_ADSO_GRIR", "ADSO", s["release"], "NOT_APPLICABLE",
                                               "FINANCE", _fields("BUKRS RACCT HSL POPER", ["BUKRS", "RACCT", "POPER"]),
                                               ["BUKRS", "RACCT", "POPER"], "G/L balance per period",
                                               depends_on=["ECC01:SIM_DS_GRIR_FI"], extraction={"initial": True, "delta": True,
                                                                                               "mechanism": "BW_DTP"},
                                               group="BW")
        out["BW401:SIM_Q_GRIR_AP"] = SapObject("BW401", s["client"], "SIM_Q_GRIR_AP", "BW_QUERY", s["release"], "NOT_APPLICABLE",
                                               "FINANCE", [], [], "Aggregated", depends_on=["SIM_ADSO_GRIR"], group="BW")
        return out
    cfin_groups = ("ACDOCA", "BKPF", "XMAP", "BP", "GL", "CC")
    for gid, g in GROUPS.items():
        if s["type"] == "CFIN" and gid not in cfin_groups:
            continue
        fl = _fields(g["f"], g["keys"], g.get("custom", ()))
        if s["type"] == "ECC" and gid == "ACDOCA":
            continue  # no Universal Journal in ECC
        if gid in ("POI",) and s["type"] != "S4":
            fl = [f for f in fl if not f.custom]
        base_dep = [d for d in g["dep"] if s["type"] != "CFIN" or d in cfin_groups]
        tbl = SapObject(sys_id, s["client"], g["table"].split("/")[0], "DDIC_TABLE", s["release"], "NOT_APPLICABLE",
                        g["dom"], fl, g["keys"], g["grain"], group=gid)
        out[tbl.id] = tbl
        if s["type"] == "ECC":
            o = SapObject(sys_id, s["client"], _ds_name(gid), "ODP_DATASOURCE", s["release"], "NOT_APPLICABLE", g["dom"], fl,
                          g["keys"], g["grain"], depends_on=[g["table"].split("/")[0]],
                          extraction={"initial": True, "delta": gid in TRANSACTIONAL, "mechanism": "ODP_SAPI"},
                          authorization=g["auth"], group=gid)
        else:
            deps = [g["table"].split("/")[0]] + [_view_name(d) for d in base_dep if d in GROUPS]
            if gid == "ACDOCA" and s["type"] == "CFIN":
                deps = ["ACDOCA"]
            o = SapObject(sys_id, s["client"], _view_name(gid), "CDS_INTERFACE_VIEW", s["release"], "RELEASED", g["dom"], fl,
                          g["keys"], g["grain"], depends_on=deps, authorization=g["auth"],
                          extraction={"initial": True, "delta": gid in TRANSACTIONAL, "mechanism": "CDS_EXTRACTION"},
                          custom_fields=list(g.get("custom", ())), group=gid,
                          associations=[{"target": _view_name(d), "cardinality": "N:1"} for d in base_dep if d in GROUPS])
        out[o.id] = o
    # reporting artefacts
    if s["type"] in ("S4", "CFIN"):
        key_groups = ["POI", "MATDOC", "INVI", "ACDOCA", "SUPOI"] if s["type"] == "S4" else ["ACDOCA"]
        cube = SapObject(sys_id, s["client"], "SIM_C_P2P_RECON", "CUBE", s["release"], "RELEASED", "FINANCE", [], [],
                         "Mixed (facts at independent grains)", depends_on=[_view_name(g) for g in key_groups] +
                         (["SIM_Z_CUSTOM_GRIR"] if sys_id == "S4A" else []), group="REPORT")
        qry = SapObject(sys_id, s["client"], "SIM_Q_P2P_RECON", "QUERY", s["release"], "RELEASED", "FINANCE", [], [],
                        "Aggregated", depends_on=["SIM_C_P2P_RECON"], group="REPORT")
        out[cube.id], out[qry.id] = cube, qry
        if sys_id == "S4A":
            # Custom view that references a helper which discovery could not resolve -> reported, never guessed.
            out["S4A:SIM_Z_CUSTOM_GRIR"] = SapObject("S4A", s["client"], "SIM_Z_CUSTOM_GRIR", "CDS_CUSTOM_VIEW", s["release"],
                                                     "NOT_RELEASED", "FINANCE", [], [], "Aggregated",
                                                     depends_on=[_view_name("MATDOC"), "SIM_Z_UNRELEASED_HELPER"],
                                                     group="CUSTOM")
    if sys_id == "ECC01":
        out["ECC01:SIM_DS_GRIR_FI"] = SapObject("ECC01", s["client"], "SIM_DS_GRIR_FI", "ODP_DATASOURCE", s["release"],
                                                "NOT_APPLICABLE", "FINANCE", _fields("BUKRS RACCT HSL POPER", ["BUKRS", "RACCT", "POPER"]),
                                                ["BUKRS", "RACCT", "POPER"], "G/L balance per period",
                                                depends_on=["BSEG"], extraction={"initial": True, "delta": True, "mechanism": "ODP_SAPI"},
                                                group="BW_SRC")
    return out


def all_objects(scenario: str) -> dict[str, SapObject]:
    sc = SCENARIOS[scenario]
    objs: dict[str, SapObject] = {}
    for sid in sc["systems"]:
        if SYSTEMS[sid]["type"] in ("S4", "ECC", "CFIN", "BW"):
            objs.update(build_objects(sid))
    return objs


# ---- synthetic data product catalog fixture --------------------------------------------------------------------------

def _entity(gid: str, drop: tuple[str, ...] = (), keys: list[str] | None = None, grain: str | None = None, delta: bool = True,
            auth: list[str] | None = None, covers: list[str] | None = None, logic: list[str] | None = None,
            sem: dict | None = None, relationships: list[str] | None = None, name: str | None = None) -> dict:
    g = GROUPS[gid]
    fl = [f for f in _fields(g["f"], g["keys"]) if f.name not in drop]
    return {"entity": name or gid, "covers_objects": covers or [gid],
            "fields": {f.name: {"type": f.type, "length": f.length, "decimals": f.decimals} for f in fl},
            "keys": keys if keys is not None else list(g["keys"]), "grain": grain or g["grain"],
            "relationships": relationships if relationships is not None else [d for d in g["dep"]],
            "delta": delta, "auth_objects": auth if auth is not None else list(g["auth"]),
            "logic_supported": logic or [], "semantics": sem or ({"amount_basis": "DOCUMENT_CURRENCY"} if "sem" in g else {})}


def _product(pid: str, name: str, ents: list[dict], evidence: str = "SYNTHETIC_FIXTURE", releases=("S4_2023", "S4_2022"),
             key_user: bool = False, dev: bool = False, dp_ext: bool = False, entitlement: str = "ENTITLED",
             activation: str = "ACTIVATED", domain: str = "PROCUREMENT", pkg: str = "SIM_PKG") -> dict:
    return {"product_id": pid, "name": name, "version": "1.0.0-SYNTHETIC", "source_application": "S/4HANA",
            "supported_releases": list(releases), "data_package": pkg, "entities": ents, "evidence": evidence,
            "domain": domain, "extension": {"key_user": key_user, "developer": dev, "data_product_extension": dp_ext},
            "activation": activation, "entitlement": entitlement, "installation": "INSTALLED" if activation == "ACTIVATED" else "NOT_INSTALLED",
            "published_availability": "SYNTHETIC", "tenant_availability": "SYNTHETIC", "technical_compatibility": "SYNTHETIC",
            "consumption": "NOT_ATTEMPTED", "source_reference_url": "SYNTHETIC_FIXTURE_NO_URL",
            "last_verified": "2026-11-26"}


def catalog_fixture() -> dict:
    """Synthetic catalog snapshot. Domain completeness is declared per domain; undeclared => NOT_ESTABLISHED."""
    products = [
        _product("SIM_DP_PURCHASE_REQUISITION", "Purchase Requisition (synthetic)", [_entity("PR"), _entity("PRACC")],
                 releases=("S4_2023", "S4_2022", "ECC_6_0_EHP8")),
        _product("SIM_DP_PURCHASE_ORDER", "Purchase Order (synthetic)",
                 [_entity("POH"), _entity("POI", drop=("ZZ_SAFETY_CLASS",)), _entity("POSCH"),
                  _entity("POACC", sem={"amount_basis": "COMPANY_CODE_CURRENCY"})], key_user=True, dp_ext=True),
        _product("SIM_DP_SUPPLIER_INVOICE", "Supplier Invoice (synthetic, header level only)",
                 [_entity("INVH", covers=["INVH", "INVI"], name="INVOICE_HEADER")]),
        _product("SIM_DP_GOODS_MOVEMENT", "Goods Movement (synthetic, no delta)", [_entity("MATDOC", delta=False)]),
        _product("SIM_DP_JOURNAL_ENTRY", "Journal Entry (synthetic)",
                 [_entity("ACDOCA"), _entity("BKPF"), _entity("BSEG", drop=("SHKZG", "AUGBL"), covers=["BSEG"],
                                                              name="BSEG_ENTRY_VIEW")],
                 releases=("S4_2023",), domain="FINANCE"),
        _product("SIM_DP_SUPPLIER_OPEN_ITEM", "Supplier Open Item (synthetic CANDIDATE)", [_entity("SUPOI")],
                 evidence="CANDIDATE_UNVERIFIED", releases=("S4_2023",), domain="FINANCE"),
        _product("SIM_DP_PAYMENT_CLEARING", "Payment Clearing (synthetic)", [_entity("PAYCLR")], releases=("S4_2023",),
                 domain="FINANCE"),
        _product("SIM_DP_BUSINESS_PARTNER", "Business Partner (synthetic)",
                 [_entity("BP", auth=["F_LFA1_GEN"])], domain="MASTER_DATA", releases=("S4_2023", "S4_2022")),
        _product("SIM_DP_PRODUCT", "Product (synthetic)", [_entity("MAT")], domain="MASTER_DATA",
                 releases=("S4_2023", "S4_2022", "ECC_6_0_EHP8")),
    ]
    return {"snapshot_id": "SYNTHETIC_CATALOG_v1", "evidence": "SYNTHETIC_FIXTURE", "products": products,
            # Only PROCUREMENT is declared complete (synthetic), so a missing product there is PRODUCT_NOT_AVAILABLE.
            # FIN_MASTER completeness is not established -> UNKNOWN, never "does not exist".
            "domain_completeness": {"PROCUREMENT": True, "FINANCE": True, "MASTER_DATA": True,
                                    "CROSS_SYSTEM": True}}
