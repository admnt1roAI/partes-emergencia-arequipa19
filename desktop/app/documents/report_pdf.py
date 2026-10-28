from __future__ import annotations

from html import escape
from pathlib import Path
from datetime import datetime
import re
import secrets
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from desktop.app.models.report import EmergencyReport


NAVY = colors.HexColor("#123d68")
BLUE = colors.HexColor("#176bc2")
PALE_BLUE = colors.HexColor("#e8f3fd")
LIGHT = colors.HexColor("#f4f8fc")
GRID = colors.HexColor("#b8cde0")
TEXT = colors.HexColor("#173a58")


def _plain(value: object) -> str:
    text = str(value or "").strip()
    return escape(text).replace("\n", "<br/>") if text else "—"


def _label(key: str) -> str:
    known = {
        "nombres_y_apellidos": "Nombres y apellidos", "dni": "DNI", "edad": "Edad", "lesión": "Lesión",
        "placa": "Placa", "marca": "Marca", "modelo": "Modelo", "color": "Color", "año": "Año",
        "unidad": "Unidad", "piloto": "Piloto", "al_mando": "Al mando", "km_salida": "KM salida",
        "km_ingreso": "KM ingreso", "h._salida": "Hora salida", "h._ingreso": "Hora ingreso",
        "soat": "SOAT", "citv": "CITV", "efectivo": "Efectivo", "condición": "Condición",
        "compañía": "Compañía", "institución_/_dependencia": "Institución / dependencia",
        "vehículo": "Vehículo",
    }
    return known.get(key, key.replace("_", " ").strip().capitalize())


def generate_report_pdf(report: EmergencyReport, output_path: Path | str, version: int = 1,
                        branding: dict[str, str] | None = None) -> Path:
    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"Ya existe un archivo en esta ubicación: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().astimezone()
    generated_text = generated_at.strftime("%d/%m/%Y %H:%M:%S")
    number_token = re.sub(r"[^A-Za-z0-9]", "", report.local_number).upper()[:24] or report.id[:12].upper()
    issue_code = f"A19-{generated_at:%Y%m%d-%H%M%S}-{number_token}-{secrets.token_hex(2).upper()}"
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Institution", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9,
                              leading=12, alignment=TA_CENTER, textColor=NAVY))
    styles.add(ParagraphStyle("DocTitle", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=15,
                              leading=18, alignment=TA_CENTER, textColor=NAVY, spaceBefore=3))
    styles.add(ParagraphStyle("DocSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=8,
                              leading=10, alignment=TA_CENTER, textColor=TEXT))
    styles.add(ParagraphStyle("Section", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9,
                              leading=12, textColor=NAVY))
    styles.add(ParagraphStyle("Cell", parent=styles["Normal"], fontName="Helvetica", fontSize=8,
                              leading=10, textColor=TEXT, wordWrap="CJK"))
    styles.add(ParagraphStyle("CellBold", parent=styles["Cell"], fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("SmallCenter", parent=styles["Cell"], alignment=TA_CENTER))

    doc = SimpleDocTemplate(str(destination), pagesize=letter, rightMargin=14 * mm, leftMargin=14 * mm,
                            topMargin=20 * mm, bottomMargin=17 * mm,
                            title=f"Parte de emergencia {report.local_number}",
                            author="Benemérita y Centenaria Compañía de Bomberos Arequipa 19")
    story: list = []
    branding = branding or {}
    default_logo = Path(__file__).resolve().parents[2] / "assets" / "emblem-reference.png"
    logo = Path(branding.get("emblem_path") or default_logo)
    if not logo.is_file():
        logo = default_logo
    institution = [
        Paragraph(escape(branding.get("institution_line_1", "CUERPO GENERAL DE BOMBEROS VOLUNTARIOS DEL PERÚ")), styles["Institution"]),
        Paragraph(escape(branding.get("institution_line_2", "VII COMANDANCIA DEPARTAMENTAL")), styles["Institution"]),
        Paragraph(escape(branding.get("institution_line_3", "BENEMÉRITA Y CENTENARIA COMPAÑÍA DE BOMBEROS AREQUIPA 19")), styles["Institution"]),
        Paragraph(escape(branding.get("document_title", "PARTE DE EMERGENCIA")), styles["DocTitle"]),
        Paragraph(escape(branding.get("document_subtitle", "Documento Oficial según el Artículo N.º 217 del Reglamento Interno de Funciones")), styles["DocSubtitle"]),
    ]
    logo_cell = Image(str(logo), width=22 * mm, height=27 * mm, kind="proportional") if logo.exists() else ""
    heading = Table([[logo_cell, institution]], colWidths=[25 * mm, 155 * mm])
    heading.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BOX", (0, 0), (-1, -1), 0.7, GRID),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
    ]))
    story.extend([heading, Spacer(1, 5 * mm)])

    def section(title: str) -> None:
        band = Table([[Paragraph(escape(title.upper()), styles["Section"])]], colWidths=[180 * mm])
        # Keep each section heading with the first row/table that follows it.
        band.keepWithNext = 1
        band.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE), ("BOX", (0, 0), (-1, -1), 0.6, GRID),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        gap = Spacer(1, 1.5 * mm)
        gap.keepWithNext = 1
        story.extend([band, gap])

    def data_table(rows: list[list], widths: list[float], header: bool = False) -> Table:
        table_class = LongTable if header else Table
        table = table_class(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.45, GRID),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ]
        if header:
            commands.extend([
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ])
        table.setStyle(TableStyle(commands))
        return table

    def records(title: str, values: Iterable[dict[str, str]], keys: list[str],
                ratios: list[float] | None = None) -> None:
        section(title)
        rows = [[Paragraph(escape(_label(key)).upper(), styles["CellBold"]) for key in keys]]
        records_list = list(values)
        if records_list:
            for item in records_list:
                rows.append([Paragraph(_plain(item.get(key, "")), styles["Cell"]) for key in keys])
        else:
            rows.append([Paragraph("Sin registros", styles["Cell"]) for _ in keys])
        total_width = 180 * mm
        count = len(keys)
        widths = [total_width * ratio for ratio in ratios] if ratios else [total_width / count] * count
        story.extend([data_table(rows, widths, header=True), Spacer(1, 3 * mm)])

    section("Datos generales")
    occurred = report.occurred_at.replace("T", " ")[:16]
    general_rows = [
        ["PARTE N.º", _plain(report.local_number), "FECHA Y HORA", _plain(occurred)],
        ["EMERGENCIA", _plain(report.emergency_type), "CODIFICACIÓN", _plain(report.codification)],
        ["DIRECCIÓN", _plain(report.address), "DISTRITO", _plain(report.district)],
    ]
    general = [[Paragraph(_plain(cell), styles["CellBold"] if index % 2 == 0 else styles["Cell"])
                for index, cell in enumerate(row)] for row in general_rows]
    story.extend([data_table(general, [24 * mm, 66 * mm, 27 * mm, 63 * mm]), Spacer(1, 2 * mm)])
    section("Trabajo realizado")
    story.extend([data_table([[Paragraph(_plain(report.work_description), styles["Cell"])]], [180 * mm]), Spacer(1, 3 * mm)])

    records("Víctimas", report.victims, ["nombres_y_apellidos", "dni", "edad", "lesión"],
            [0.50, 0.20, 0.10, 0.20])
    records("Vehículos involucrados", report.vehicles, ["placa", "marca", "modelo", "color", "año"])
    records("Unidades que asistieron", report.units,
            ["unidad", "piloto", "al_mando", "km_salida", "km_ingreso", "h._salida", "h._ingreso", "soat", "citv"],
            [0.12, 0.16, 0.18, 0.10, 0.10, 0.10, 0.10, 0.07, 0.07])
    records("Efectivos en servicio", report.personnel, ["efectivo", "condición"])

    section("Material utilizado")
    story.extend([data_table([[Paragraph(_plain(report.materials), styles["Cell"])]], [180 * mm]), Spacer(1, 3 * mm)])
    section("Verificaciones")
    verification = [
        [Paragraph("PERSONAL CORRECTAMENTE UNIFORMADO", styles["CellBold"]), Paragraph(_plain(report.uniformed), styles["SmallCenter"]),
         Paragraph("MATERIAL CONFORME, LIMPIO Y ORDENADO", styles["CellBold"]), Paragraph(_plain(report.equipment_orderly), styles["SmallCenter"]),
         Paragraph("BITÁCORA REGISTRADA", styles["CellBold"]), Paragraph(_plain(report.logbook_recorded), styles["SmallCenter"])],
    ]
    story.extend([data_table(verification, [44 * mm, 12 * mm, 45 * mm, 12 * mm, 45 * mm, 22 * mm]), Spacer(1, 3 * mm)])
    records("Vehículos de apoyo del CGBVP", report.supports, ["compañía", "unidad", "al_mando"])
    records("Apoyo PNP / otras instituciones", report.pnp_support,
            ["institución_/_dependencia", "vehículo", "al_mando"])

    section("Cierre del parte")
    closing_rows = [
        [Paragraph("CENTRALISTA DE TURNO", styles["CellBold"]), Paragraph(_plain(report.shift_operator), styles["Cell"]),
         Paragraph("LLENADO POR", styles["CellBold"]), Paragraph(_plain(report.filled_by), styles["Cell"])],
        [Paragraph("OBSERVACIONES", styles["CellBold"]), Paragraph(_plain(report.observations), styles["Cell"]), "", ""],
    ]
    closing = data_table(closing_rows, [45 * mm, 55 * mm, 25 * mm, 55 * mm])
    closing.setStyle(TableStyle([("SPAN", (1, 1), (3, 1))]))
    watermark_path = Path(__file__).resolve().parents[2] / "assets" / "signature-watermark.jpg"
    signature_watermark = (
        Image(str(watermark_path), width=68 * mm, height=16 * mm, kind="proportional")
        if watermark_path.is_file() else ""
    )
    signature_row = data_table([[
        Paragraph("FIRMA / CONFORMIDAD", styles["CellBold"]),
        signature_watermark,
        Paragraph(_plain(report.signature_name), styles["Cell"]),
    ]], [45 * mm, 70 * mm, 65 * mm])
    signature_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    issuance_note = f"Código de emisión: {issue_code} · Generado: {generated_text}"
    if version > 1:
        issuance_note += " · copia registrada"
    issuance_note += " · Pendiente de sincronización oficial"
    story.extend([closing, Spacer(1, 1.5 * mm), signature_row, Spacer(1, 4 * mm),
                  Paragraph(escape(issuance_note), styles["DocSubtitle"])])

    def footer(canvas, document) -> None:
        canvas.saveState()
        if document.page > 1:
            canvas.setFont("Helvetica-Bold", 7)
            canvas.setFillColor(NAVY)
            canvas.drawString(14 * mm, letter[1] - 11 * mm,
                              f"{branding.get('document_title', 'PARTE DE EMERGENCIA')} · {branding.get('institution_line_3', 'AREQUIPA 19')}")
            canvas.drawRightString(letter[0] - 14 * mm, letter[1] - 11 * mm,
                                   f"Parte {report.local_number} · {issue_code}")
        canvas.setStrokeColor(GRID)
        canvas.setLineWidth(0.5)
        canvas.line(14 * mm, 12 * mm, letter[0] - 14 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(TEXT)
        canvas.drawString(14 * mm, 8 * mm, f"Código {issue_code}")
        canvas.drawRightString(letter[0] - 14 * mm, 8 * mm, f"Página {document.page}")
        canvas.restoreState()

    try:
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination
