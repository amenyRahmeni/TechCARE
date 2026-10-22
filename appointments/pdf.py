from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import threading
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_PDF_LOCK = threading.Lock()
GREEN = colors.HexColor("#175f50")
INK = colors.HexColor("#273d34")
MUTED = colors.HexColor("#718078")
PALE = colors.HexColor("#edf5ef")


def money(value):
    return f"{Decimal(str(value)):.3f}".replace(".", ",") + " TND"


def _font():
    if "AtelierPC" not in pdfmetrics.getRegisteredFontNames():
        fonts = Path(reportlab.__file__).parent / "fonts"
        regular = Path("C:/Windows/Fonts/arial.ttf")
        bold = Path("C:/Windows/Fonts/arialbd.ttf")
        pdfmetrics.registerFont(TTFont("AtelierPC", str(regular if regular.exists() else fonts / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("AtelierPC-Bold", str(bold if bold.exists() else fonts / "VeraBd.ttf")))
        pdfmetrics.registerFontFamily("AtelierPC", normal="AtelierPC", bold="AtelierPC-Bold", italic="AtelierPC", boldItalic="AtelierPC-Bold")


def generate_pdf(invoice, kind="invoice"):
    # ReportLab font registration and document construction share internal caches.
    with _PDF_LOCK:
        _font()
        return _build(invoice, kind)


def _build(invoice, kind):
    data = invoice.snapshot
    output = BytesIO()
    is_report = kind == "report"
    title = "Rapport d’intervention" if is_report else "Facture de réparation"
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("BodyPC", fontName="AtelierPC", fontSize=9, leading=14, textColor=INK, spaceAfter=6, splitLongWords=True))
    styles.add(ParagraphStyle("TitlePC", fontName="AtelierPC-Bold", fontSize=23, leading=30, textColor=GREEN, spaceAfter=12))
    styles.add(ParagraphStyle("HeadingPC", fontName="AtelierPC-Bold", fontSize=12, leading=18, textColor=GREEN, spaceBefore=16, spaceAfter=9))
    styles.add(ParagraphStyle("SmallPC", parent=styles["BodyPC"], fontSize=8, leading=12, textColor=MUTED))
    styles.add(ParagraphStyle("RightPC", parent=styles["BodyPC"], alignment=TA_RIGHT))

    def p(value, style="BodyPC"):
        return Paragraph(escape(str(value or "—")).replace("\n", "<br/>"), styles[style])

    def heading(value):
        return p(value, "HeadingPC")

    def formatted_date(value):
        return datetime.fromisoformat(value).strftime("%d/%m/%Y à %H:%M")

    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=17 * mm, bottomMargin=19 * mm, title=f"{title} · {invoice.number}", author="TECHcare")
    width = A4[0] - 32 * mm
    story = [p("TECHcare · PC & MAINTENANCE", "SmallPC"), Spacer(1, 6 * mm), p(title, "TitlePC"), p(invoice.number, "SmallPC"), Spacer(1, 5 * mm)]
    summary = Table([
        [p("CLIENT", "SmallPC"), p("INTERVENTION", "SmallPC")],
        [p(data["client"]), p(f"Rendez-vous #{data['appointment_id']} · {data['category']}")],
        [p(data.get("client_email"), "SmallPC"), p(f"Technicien : {data['technician']}", "SmallPC")],
        [p(f"Clôture : {formatted_date(data['completed_at'])}", "SmallPC"), p(f"Créneau : {formatted_date(data['scheduled_at'])}", "SmallPC")],
    ], colWidths=[width / 2] * 2, hAlign="LEFT")
    summary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 13), ("RIGHTPADDING", (0, 0), (-1, -1), 13), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.extend([summary, heading("Ordinateur pris en charge")])
    pc = data["pc"]
    story.extend([p(f"{pc['name']} · {pc['brand']} {pc['model']}"), p(f"{pc['operating_system']} · {pc['ram_gb']} Go RAM · {pc['storage_gb']} Go {pc['storage_type']}"), p(f"Processeur : {pc.get('processor') or 'Non renseigné'} · N° de série : {pc.get('serial_number') or 'Non renseigné'}", "SmallPC"), p(f"Motif : {data['reason']}")])
    if is_report:
        story.extend([heading("Diagnostic"), p(data["diagnosis"]), heading("Travaux réalisés et solution"), p(data["solution"])])
    story.append(heading("Pièces et main-d’œuvre"))
    rows = [[p("Désignation"), p("Qté"), p("Prix unitaire"), p("Montant")]]
    for part in data["parts"]:
        rows.append([p(part["name"]), p(part["quantity"]), p(money(part["unit_price"]), "RightPC"), p(money(part["total"]), "RightPC")])
    rows.append([p("Main-d’œuvre"), p("1"), p(money(data["labour_cost"]), "RightPC"), p(money(data["labour_cost"]), "RightPC")])
    table = Table(rows, colWidths=[width * .44, width * .08, width * .24, width * .24], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), PALE), ("LINEBELOW", (0, 0), (-1, 0), .7, GREEN), ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#e3eae4")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.extend([table, Spacer(1, 6 * mm), p("TOTAL : " + money(data["total"]), "RightPC"), Spacer(1, 7 * mm), p("Document établi à partir du compte rendu clôturé. Montants exprimés en dinars tunisiens (TND). Horaires de Tunis.", "SmallPC")])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dde7df"))
        canvas.line(16 * mm, 15 * mm, A4[0] - 16 * mm, 15 * mm)
        canvas.setFont("AtelierPC", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 10 * mm, "TECHcare · " + invoice.number)
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output
