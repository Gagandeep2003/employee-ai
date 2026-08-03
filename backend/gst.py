"""GST (India) calculation for subscription billing.

Verified against current public GST guidance (2026): the standard rate for SaaS/software
services is 18% (9% CGST + 9% SGST intra-state, or 18% IGST inter-state), under SAC 998314
(IT design & development services -- the code most commonly used for SaaS). Both the rate
and SAC code are admin-configurable via platform_settings (see DEFAULTS: gst_rate,
hsn_sac_code) rather than hardcoded, since tax rates and classifications can change and
this isn't a substitute for the deployment owner's own CA sign-off.

State codes below are the standard 2-digit GST state code table (first two digits of any
GSTIN) -- stable, public data, but state codes have been extended before (e.g. Dadra &
Nagar Haveli + Daman & Diu merged into a single code 26 in Jan 2020), so a production
deployment should periodically confirm this list against https://www.gst.gov.in.
"""
from typing import Optional

INDIA_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan",
    "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand",
    "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}


def validate_gstin(gstin: str) -> bool:
    """Structural check only (15 chars, state code is a known one) -- not a checksum or a
    live registry lookup. Good enough to catch typos; not a substitute for GST portal
    verification if a business's ITC eligibility matters to them."""
    gstin = (gstin or "").strip().upper()
    if len(gstin) != 15:
        return False
    return gstin[:2] in INDIA_STATE_CODES


def state_code_from_gstin(gstin: str) -> Optional[str]:
    gstin = (gstin or "").strip().upper()
    return gstin[:2] if validate_gstin(gstin) else None


def compute_gst_inclusive(total_paise: int, buyer_state_code: Optional[str],
                          seller_state_code: str, gst_rate: float) -> dict:
    """Same output shape as compute_gst, but the input is the GST-INCLUSIVE total actually
    charged. Back-calculates the taxable value so cgst+sgst+igst sum exactly back to
    total_paise -- the invoice's total must always match the amount actually charged to
    the paisa, never drift from a rounding error."""
    taxable = round(total_paise / (1 + gst_rate / 100)) if gst_rate > 0 else total_paise
    calc = compute_gst(taxable, buyer_state_code, seller_state_code, gst_rate)
    drift = total_paise - calc["total_paise"]
    if drift:
        if calc["is_intra_state"]:
            calc["sgst_paise"] += drift
        else:
            calc["igst_paise"] += drift
        calc["total_tax_paise"] += drift
        calc["total_paise"] = total_paise
    return calc


def compute_gst(taxable_value_paise: int, buyer_state_code: Optional[str],
                seller_state_code: str, gst_rate: float) -> dict:
    """taxable_value_paise: the pre-tax amount, in paise. Returns a dict with the CGST/SGST
    (intra-state) or IGST (inter-state) split, always in paise, plus the grand total.
    If buyer_state_code is unknown (no GSTIN/state on file), this defaults conservatively
    to IGST -- the same amount either way, just attributed differently, and callers should
    prompt the business to add their state for a correctly-split invoice."""
    tax_paise = round(taxable_value_paise * gst_rate / 100)
    intra_state = bool(buyer_state_code) and buyer_state_code == seller_state_code
    if intra_state:
        cgst = tax_paise // 2
        sgst = tax_paise - cgst  # absorbs the odd paise so cgst+sgst always equals tax_paise exactly
        igst = 0
    else:
        cgst = sgst = 0
        igst = tax_paise
    return {
        "taxable_value_paise": taxable_value_paise,
        "gst_rate": gst_rate,
        "cgst_paise": cgst,
        "sgst_paise": sgst,
        "igst_paise": igst,
        "total_tax_paise": cgst + sgst + igst,
        "total_paise": taxable_value_paise + cgst + sgst + igst,
        "is_intra_state": intra_state,
    }
