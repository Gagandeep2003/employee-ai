"""Renders a GST tax invoice (or credit note) PDF from an invoice document (see
invoicing.py). Pure function of the invoice dict -- no DB access here, so it can be reused
both at invoice-creation time and to regenerate a PDF on demand for an older invoice.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

_STYLES = getSampleStyleSheet()
_TITLE = ParagraphStyle("InvoiceTitle", parent=_STYLES["Title"], fontSize=18, spaceAfter=2)
_SMALL = ParagraphStyle("Small", parent=_STYLES["Normal"], fontSize=9, leading=13)
_SMALL_MUTED = ParagraphStyle("SmallMuted", parent=_SMALL, textColor=colors.HexColor("#666666"))
_LABEL = ParagraphStyle("Label", parent=_SMALL, textColor=colors.HexColor("#888888"), fontSize=8)


def _rupees(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    return f"{sign}Rs. {abs(paise) / 100:,.2f}"


def render_invoice_pdf(invoice: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    story = []
    seller = invoice.get("seller_snapshot") or {}
    buyer = invoice.get("buyer_snapshot") or {}
    doc_label = "CREDIT NOTE" if invoice.get("document_type") == "credit_note" else "TAX INVOICE"

    # Header: seller details left, invoice meta right
    header = Table([[
        Paragraph(
            f"<b>{seller.get('legal_name') or 'Your Business'}</b><br/>"
            f"{(seller.get('address') or '').replace(chr(10), '<br/>')}<br/>"
            f"GSTIN: {seller.get('gstin') or 'Not registered'}",
            _SMALL,
        ),
        Paragraph(
            f"<para align=right><b>{doc_label}</b><br/>"
            f"No: {invoice.get('invoice_number', '')}<br/>"
            f"Date: {(invoice.get('created_at') or '')[:10]}</para>",
            _SMALL,
        ),
    ]], colWidths=[100 * mm, 72 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(header)
    story.append(Spacer(1, 10 * mm))

    story.append(Paragraph("BILL TO", _LABEL))
    story.append(Paragraph(
        f"<b>{buyer.get('legal_name') or ''}</b><br/>"
        f"{(buyer.get('address') or '').replace(chr(10), '<br/>') or '-'}<br/>"
        f"GSTIN: {buyer.get('gstin') or 'Not registered'}<br/>"
        f"{buyer.get('email') or ''}",
        _SMALL,
    ))
    story.append(Spacer(1, 8 * mm))

    is_intra = invoice.get("is_intra_state")
    tax_cols = (
        [("CGST", invoice.get("cgst_paise", 0)), ("SGST", invoice.get("sgst_paise", 0))]
        if is_intra else [("IGST", invoice.get("igst_paise", 0))]
    )
    header_row = ["Description", "HSN/SAC", "Taxable Value"] + [c[0] for c in tax_cols] + ["Total"]
    data_row = [
        Paragraph(invoice.get("description") or f"{(invoice.get('plan') or '').title()} plan subscription", _SMALL),
        invoice.get("hsn_sac_code", ""),
        _rupees(invoice.get("taxable_value_paise", 0)),
    ] + [_rupees(c[1]) for c in tax_cols] + [_rupees(invoice.get("total_paise", 0))]

    rate = invoice.get("gst_rate", 0)
    if is_intra:
        half_rate = rate / 2
        rate_labels = [f" ({half_rate:g}%)", f" ({half_rate:g}%)"]
    else:
        rate_labels = [f" ({rate:g}%)"]
    header_row = [header_row[0], header_row[1], header_row[2]] + \
        [f"{c[0]}{lbl}" for c, lbl in zip(tax_cols, rate_labels)] + [header_row[-1]]

    table = Table([header_row, data_row], colWidths=[62 * mm] + [22 * mm] * (len(header_row) - 1))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3F33")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    total_style = ParagraphStyle("Total", parent=_SMALL, alignment=2, fontSize=12)
    story.append(Paragraph(f"<b>Total: {_rupees(invoice.get('total_paise', 0))}</b>", total_style))

    if invoice.get("refund_amount_paise"):
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"Refunded: {_rupees(invoice['refund_amount_paise'])} on "
                               f"{(invoice.get('refunded_at') or '')[:10]}",
                               ParagraphStyle("Refund", parent=_SMALL, alignment=2, textColor=colors.red)))

    story.append(Spacer(1, 14 * mm))
    payment_ref = invoice.get("razorpay_payment_id") or invoice.get("razorpay_order_id") or ""
    if payment_ref:
        story.append(Paragraph(f"Payment reference: {payment_ref}", _SMALL_MUTED))
    if not invoice.get("is_intra_state", True):
        story.append(Paragraph("Place of supply: outside seller's state (inter-state supply, IGST applies).", _SMALL_MUTED))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "This is a system-generated invoice and does not require a physical signature.",
        _SMALL_MUTED,
    ))

    doc.build(story)
    return buf.getvalue()
