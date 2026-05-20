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
    pdf.cell(0, 5, landlord_name or "[Bailleur]", new_x="LMARGIN", new_y="NEXT")
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
        # Local import — Pillow is already a dependency, used here only to
        # measure the embedded signature so the watermark area matches it.
        from PIL import Image

        x = pdf.l_margin
        y = pdf.get_y() + 2
        sig_h = 20  # mm
        pdf.image(BytesIO(signature_png_bytes), x=x, y=y, h=sig_h)

        # Compute the signature's rendered width in mm so the watermark
        # exactly overlays it (fpdf2 preserves aspect ratio when only `h`
        # is given).
        with Image.open(BytesIO(signature_png_bytes)) as img:
            sig_w = sig_h * (img.width / max(1, img.height))

        # Watermark drawn at PDF level (not on the PNG) so it stays legible
        # regardless of how small the underlying signature is. Diagonal red
        # text centered on the signature box, sized to fit the rendered text
        # rather than the signature dimensions — narrow signatures still get
        # a fully readable watermark across them.
        _draw_signature_watermark(
            pdf,
            text=f"{MONTHS_FR[month].upper()} {year}\n{now_paris}",
            sig_x=x, sig_y=y, sig_height=sig_h, sig_width=sig_w,
        )

    return bytes(pdf.output())


_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
)

# Opacity of the rendered watermark text. Range 0..255. 60 ≈ 23% alpha.
_WATERMARK_ALPHA = 60


def _load_watermark_font(size: int):
    """Return a TTF font that supports French accents. Falls back to Pillow's
    bundled default font if no DejaVu install is found (e.g. tests outside
    the container)."""
    import os
    from PIL import ImageFont
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_signature_watermark(
    pdf: FPDF, *, text: str, sig_x: float, sig_y: float,
    sig_height: float, sig_width: float,
) -> None:
    """Overlay a semi-transparent rotated watermark centered on the signature
    box. The watermark canvas is sized to fit the rotated text (not the
    signature) so narrow signatures still get a fully readable stamp across
    them; the canvas is then clamped to the printable page area.

    fpdf2 2.8.1 has no text-level alpha API, so the watermark is rendered
    as a transparent PNG via Pillow and embedded as an image (fpdf2 honours
    the PNG alpha channel).
    """
    from PIL import Image, ImageDraw

    dpi = 300
    px_per_mm = dpi / 25.4

    # Font size in pixels — anchored to the signature *height* so the text
    # looks consistent across receipts regardless of signature aspect ratio.
    # Smaller than a single-line layout because the watermark is now stacked
    # on two lines ("MOIS YYYY" + "DD/MM/YYYY").
    fontsize = max(24, int(sig_height * px_per_mm * 0.24))
    font = _load_watermark_font(fontsize)
    line_spacing = max(2, fontsize // 6)

    # Render the (possibly multi-line) text on its own transparent layer,
    # then rotate. The rotated tight bbox determines the watermark canvas
    # size. multiline_text + align="center" handles the line break in `text`.
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = measure.multiline_textbbox(
        (0, 0), text, font=font, spacing=line_spacing, align="center",
    )
    tw = int(round(bbox[2] - bbox[0]))
    th = int(round(bbox[3] - bbox[1]))
    pad = max(8, fontsize // 4)
    text_layer = Image.new("RGBA", (tw + 2 * pad, th + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(text_layer).multiline_text(
        (pad, pad), text, font=font,
        fill=(190, 0, 0, _WATERMARK_ALPHA),
        spacing=line_spacing, align="center",
    )
    rotated = text_layer.rotate(-20, expand=True, resample=Image.BICUBIC)
    rw, rh = rotated.size

    # Canvas matches the rotated text exactly.
    canvas = Image.new("RGBA", (rw, rh), (0, 0, 0, 0))
    canvas.alpha_composite(rotated, (0, 0))

    canvas_w_mm = rw / px_per_mm
    canvas_h_mm = rh / px_per_mm

    # Center the canvas on the signature center, then clamp to printable
    # area so the watermark never gets clipped by the page margins.
    sig_cx = sig_x + sig_width / 2
    sig_cy = sig_y + sig_height / 2
    x = sig_cx - canvas_w_mm / 2
    y = sig_cy - canvas_h_mm / 2

    usable_left = pdf.l_margin
    usable_right = pdf.w - pdf.r_margin
    if x < usable_left:
        x = usable_left
    if x + canvas_w_mm > usable_right:
        x = max(usable_left, usable_right - canvas_w_mm)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    pdf.image(BytesIO(buf.getvalue()), x=x, y=y, w=canvas_w_mm, h=canvas_h_mm)
