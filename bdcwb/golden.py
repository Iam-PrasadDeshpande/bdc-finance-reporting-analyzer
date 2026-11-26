"""Hand-authored expected results for the golden transaction. NEVER computed from either calculation path."""
from decimal import Decimal as D

# PO 100 EA x INR 100; GR 60 + 40; invoices 6,000 + 4,000; payment 6,000 against invoice 1. No tax / price / FX difference.
EXPECTED = {
    "po_qty": D("100"), "po_value": D("10000.00"), "gr_qty": D("100"), "gr_value": D("10000.00"),
    "inv_qty": D("100"), "inv_value": D("10000.00"), "open_po_qty": D("0"), "open_commitment": D("0.00"),
    "grir_balance": D("0.00"), "supplier_liability": D("4000.00"), "supplier_open_items": D("1"),
    "supplier_cleared_items": D("1"), "gr_doc_count": D("2"), "inv_doc_count": D("2"),
}
# Balanced entries: GR1 Dr 6000/Cr 6000, GR2 Dr 4000/Cr 4000, IR1 6000, IR2 4000, payment 6000
EXPECTED_JOURNAL = {"fi_documents": 5, "fi_lines": 10, "debit_total": D("26000.00"), "credit_total": D("26000.00")}
