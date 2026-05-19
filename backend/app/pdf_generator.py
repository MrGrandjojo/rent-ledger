"""Generates PDF rent receipts (quittances de loyer) using fpdf2."""

from decimal import Decimal
from io import BytesIO
from fpdf import FPDF
import pytz
from datetime import datetime
from typing import Optional

PARIS_TZ = pytz.timezone("Europe/Paris")
MONTHS_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def fmt_currency(value: Decimal) -> str:
    """Format Decimal as French currency string.

    Uses the text "EUR" rather than the "€" sign because the built-in
    Helvetica core font used by fpdf2 is Latin-1, which does not contain
    the euro sign. Switching to a Unicode TTF font would be the alternative,
    but bundling a font for one glyph isn't worth it for a printable receipt.
    """
    s = f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} EUR"


def generate_rent_receipt(
    *,
    landlord_name: str,
    landlord_address: str,
    landlord_phone: str,
    landlord_email: str,
    tenant_first_name: str,
    tenant_last_name: str,
    property_address: str,
    year: int,
    month: int,
    monthly_rent: Decimal,
    monthly_charges: Decimal,
    payment_date: str,
    signature_png_bytes: Optional[bytes] = None,
) -> bytes:
    """Return PDF bytes for a rent receipt."""
    total = monthly_rent + monthly_charges
    period = f"{MONTHS_FR[month]} {year}"
    now_paris = datetime.now(PARIS_TZ).strftime("%d/%m/%Y")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(20, 20, 20)

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "QUITTANCE DE LOYER", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, f"Période : {period}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_draw_color(100, 100, 100)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)

    # Landlord section
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "BAILLEUR", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, landlord_name or "—", new_x="LMARGIN", new_y="NEXT")
    if landlord_address:
        for line in landlord_address.splitlines():
            pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    if landlord_phone:
        pdf.cell(0, 5, f"Tél. : {landlord_phone}", new_x="LMARGIN", new_y="NEXT")
    if landlord_email:
        pdf.cell(0, 5, f"Email : {landlord_email}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Tenant section
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "LOCATAIRE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"{tenant_first_name} {tenant_last_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Property section
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "BIEN LOUÉ", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, property_address, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)

    # Payment detail
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "DÉTAIL DU RÈGLEMENT", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)

    col_w = 130
    pdf.cell(col_w, 6, "Loyer (hors charges)")
    pdf.cell(0, 6, fmt_currency(monthly_rent), new_x="LMARGIN", new_y="NEXT")

    pdf.cell(col_w, 6, "Provision pour charges")
    pdf.cell(0, 6, fmt_currency(monthly_charges), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(col_w, 7, "TOTAL")
    pdf.cell(0, 7, fmt_currency(total), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"Date de paiement : {payment_date}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)

    # Receipt statement
    pdf.set_font("Helvetica", "I", 10)
    body = (
        f"Je soussigné(e) {landlord_name or '[Bailleur]'}, bailleur, donne quittance à "
        f"{tenant_first_name} {tenant_last_name} pour la somme de {fmt_currency(total)}, "
        f"correspondant au règlement du loyer et des charges du logement situé "
        f"{property_address}, pour la période de {period}."
    )
    pdf.multi_cell(0, 5, body)

    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"Fait le {now_paris}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.cell(0, 5, "Signature du bailleur :", new_x="LMARGIN", new_y="NEXT")

    if signature_png_bytes:
        # Embed the decrypted signature image. fpdf2 reads the bytes from the
        # BytesIO and discards them after rendering — nothing is persisted.
        x = pdf.l_margin
        y = pdf.get_y() + 2
        pdf.image(BytesIO(signature_png_bytes), x=x, y=y, h=20)

    return bytes(pdf.output())
