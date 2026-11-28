# Notices

This prototype is an independent work and is not affiliated with, endorsed by or sponsored by SAP SE. SAP, SAP S/4HANA, SAP Business Data Cloud, SAP Datasphere and related names are trademarks or registered trademarks of SAP SE.

## Third-party sources

- **SAP Business Accelerator Hub (data products)**: names, technical ids, versions, process tags, edition tags and business-object names of SAP-published data products were read from SAP's public hub on 2026-11-28 and stored as facts in `data/public_demo/sap_hub_finance_SNAPSHOT.json`. SAP's description texts are not copied. The snapshot is a point-in-time reading and may be out of date.
- **SAP/abap-atc-cr-cv-s4hc** (https://github.com/SAP/abap-atc-cr-cv-s4hc), Copyright SAP SE, licensed under the Apache License, Version 2.0 (http://www.apache.org/licenses/LICENSE-2.0). Only the names and release states of CDS views were extracted from `objectReleaseInfoLatest.json` and `objectReleaseInfo_PCELatest.json`; the data was reduced and re-organised per data product. CDS views are matched to data products by name by this prototype, which SAP does not publish.

## Evidence and limits

All business data in this prototype is synthetic. SAP-published facts are not verified in any tenant. Nothing here is SAP documentation, and no SAP system is connected.
