import io
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from models import BloodProduct, Donation, TestResult
from auth import ensure_permission, get_current_user, get_db

router = APIRouter(prefix="/api/pdf")


def _styles():
    sheets = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=sheets["Title"], fontSize=13, leading=16),
        "sub": ParagraphStyle("s", parent=sheets["Normal"], fontSize=9,
                              textColor=colors.grey, alignment=1),
    }


def _table(data, widths):
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3f8")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])
    return Table(data, colWidths=widths, style=style, repeatRows=1)


def _pdf_response(elements) -> Response:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=14 * mm, bottomMargin=14 * mm)
    doc.build(elements)
    return Response(
        content=buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=report.pdf"},
    )


@router.get("/results")
def results_pdf(status: str = "APPROVED", no_from: int | None = None, no_to: int | None = None,
                user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "pdf")
    q = db.query(TestResult).join(Donation, TestResult.donation_id == Donation.id)
    if status:
        q = q.filter(TestResult.status == status)
    if no_from is not None:
        q = q.filter(Donation.donation_no >= f"DON-{no_from:05d}")
    if no_to is not None:
        q = q.filter(Donation.donation_no <= f"DON-{no_to:05d}")
    rows = q.order_by(Donation.donation_no.desc()).limit(400)

    sheets = _styles()
    elements = [
        Paragraph("NBTS: Laboratory Results Report",
                  sheets["title"]),
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} — "
                  f"Status: {status or 'ALL'}", sheets["sub"]),
        Spacer(1, 8),
    ]
    data = [["Donation No", "Donor", "Date", "ABOD", "HIV", "HBV", "HCV", "VDRL", "Status"]]
    for r in rows:
        d = r.donation
        data.append([
            d.donation_no, d.donor.names if d.donor else "", d.donation_date,
            r.abod, r.hiv[:3], r.hbv[:3], r.hcv[:3], r.syphilis[:3], r.status,
        ])
    elements.append(_table(data, [26 * mm, 42 * mm, 20 * mm, 14 * mm, 13 * mm,
                                  13 * mm, 13 * mm, 14 * mm, 22 * mm]))
    return _pdf_response(elements)


@router.get("/products")
def products_pdf(status: str = "", product_type: str = "",
                 user=Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_permission(user, "pdf")
    q = db.query(BloodProduct)
    if status:
        q = q.filter_by(status=status)
    if product_type:
        q = q.filter_by(product_type=product_type)
    rows = q.order_by(BloodProduct.id.desc()).limit(400)

    sheets = _styles()
    elements = [
        Paragraph("NBTS: Blood Products Report", sheets["title"]),
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} — "
                  f"Status: {status or 'ALL'} — Type: {product_type or 'ALL'}",
                  sheets["sub"]),
        Spacer(1, 8),
    ]
    data = [["Code", "Type", "Donation", "ABOD", "Status", "Expiry", "Hospital"]]
    for p in rows:
        data.append([
            p.product_code, p.product_type,
            p.donation.donation_no if p.donation else "",
            p.donation.result.abod if p.donation and p.donation.result else "",
            p.status, p.expiry_date,
            p.hospital.name if p.hospital else "",
        ])
    elements.append(_table(data, [42 * mm, 16 * mm, 30 * mm, 14 * mm, 24 * mm,
                                  22 * mm, 32 * mm]))
    return _pdf_response(elements)
