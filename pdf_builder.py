"""
pdf_builder.py
Builds the final DDR PDF using ReportLab with embedded images.
"""

import io
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image as RLImage, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

# ── Color Palette ──────────────────────────────────────────────────────────────
C_DARK      = colors.HexColor("#1a1a2e")
C_ACCENT    = colors.HexColor("#16213e")
C_HIGHLIGHT = colors.HexColor("#e94560")
C_LIGHT_BG  = colors.HexColor("#f5f5f5")
C_BORDER    = colors.HexColor("#cccccc")
C_TEXT      = colors.HexColor("#222222")
C_MUTED     = colors.HexColor("#555555")
C_WHITE     = colors.white

SEV_COLORS = {
    "Critical": colors.HexColor("#c0392b"),
    "High":     colors.HexColor("#e67e22"),
    "Moderate": colors.HexColor("#f39c12"),
    "Low":      colors.HexColor("#27ae60"),
}
PRI_COLORS = {
    "Immediate":  colors.HexColor("#c0392b"),
    "Short-term": colors.HexColor("#e67e22"),
    "Long-term":  colors.HexColor("#27ae60"),
}


def _styles():
    return {
        "title": ParagraphStyle(
            "DDRTitle", fontSize=22, fontName="Helvetica-Bold",
            textColor=C_WHITE, alignment=TA_CENTER, spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "DDRSubtitle", fontSize=11, fontName="Helvetica",
            textColor=colors.HexColor("#dddddd"), alignment=TA_CENTER, spaceAfter=4,
        ),
        "h1": ParagraphStyle(
            "DDRh1", fontSize=13, fontName="Helvetica-Bold",
            textColor=C_WHITE, spaceBefore=14, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "DDRh2", fontSize=11, fontName="Helvetica-Bold",
            textColor=C_ACCENT, spaceBefore=10, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "DDRBody", fontSize=9.5, fontName="Helvetica",
            textColor=C_TEXT, leading=14, spaceAfter=4, alignment=TA_JUSTIFY,
        ),
        "bullet": ParagraphStyle(
            "DDRBullet", fontSize=9.5, fontName="Helvetica",
            textColor=C_TEXT, leading=14, leftIndent=14, spaceAfter=3, bulletIndent=4,
        ),
        "label": ParagraphStyle(
            "DDRLabel", fontSize=9, fontName="Helvetica-Bold",
            textColor=C_MUTED, spaceAfter=2,
        ),
        "caption": ParagraphStyle(
            "DDRCaption", fontSize=8, fontName="Helvetica-Oblique",
            textColor=C_MUTED, alignment=TA_CENTER, spaceAfter=6,
        ),
        "na": ParagraphStyle(
            "DDRNA", fontSize=9.5, fontName="Helvetica-Oblique",
            textColor=C_MUTED, spaceAfter=4,
        ),
    }


def _section_header(title: str, styles: dict) -> list:
    """Dark colored banner for each major section."""
    banner = Table(
        [[Paragraph(f"  {title}", styles["h1"])]],
        colWidths=[17.5 * cm],
    )
    banner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_ACCENT),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
    ]))
    return [Spacer(1, 0.3 * cm), banner, Spacer(1, 0.2 * cm)]


def _kv_table(rows: list[tuple], styles: dict) -> Table:
    """Two-column key-value table with shaded label column."""
    data = []
    for k, v in rows:
        val = v if v else "Not Available"
        data.append([
            Paragraph(k, styles["label"]),
            Paragraph(str(val), styles["body"]),
        ])
    t = Table(data, colWidths=[5 * cm, 12.5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), C_LIGHT_BG),
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _embed_image(img_bytes: bytes, max_w_cm: float = 8.0, max_h_cm: float = 6.0) -> RLImage | None:
    """Convert raw image bytes to ReportLab Image flowable with aspect-ratio scaling."""
    try:
        pil = PILImage.open(io.BytesIO(img_bytes))
        orig_w, orig_h = pil.size
        if orig_w == 0 or orig_h == 0:
            return None
        ratio = min((max_w_cm * cm) / orig_w, (max_h_cm * cm) / orig_h)
        return RLImage(io.BytesIO(img_bytes), width=orig_w * ratio, height=orig_h * ratio)
    except Exception as e:
        logger.warning(f"Could not embed image: {e}")
        return None


def _match_images_to_area(area_name: str, image_captions: list[str], all_images: list[dict]) -> list[dict]:
    """
    Keyword-based image matching. Scores each image by how many area/caption
    keywords appear in the image label. Returns up to 4 best matches.
    """
    if not all_images:
        return []

    stopwords = {"the", "of", "and", "in", "at", "on", "a", "is", "to", "for", "not", "available"}
    combined = (area_name + " " + " ".join(image_captions)).lower()
    keywords = set(combined.split()) - stopwords

    scored = []
    for img in all_images:
        score = sum(1 for kw in keywords if kw in img["label"].lower())
        if score > 0:
            scored.append((score, img))

    scored.sort(key=lambda x: -x[0])
    return [img for _, img in scored[:4]]


def _color_hex(color) -> str:
    """Convert ReportLab color to hex string without #."""
    try:
        return f"{int(color.red*255):02x}{int(color.green*255):02x}{int(color.blue*255):02x}"
    except Exception:
        return "222222"


def build_ddr_pdf(
    ddr_data: dict,
    inspection_images: list[dict],
    thermal_images: list[dict],
    property_name: str = "Property",
) -> bytes:
    """
    Assemble the full DDR PDF. Returns raw PDF bytes.

    Args:
        ddr_data:           Parsed JSON from Gemini (7-section DDR structure).
        inspection_images:  Image dicts from extractor.py (inspection PDF).
        thermal_images:     Image dicts from extractor.py (thermal PDF).
        property_name:      Used in title and footer.
    """
    all_images = inspection_images + thermal_images
    buffer = io.BytesIO()
    styles = _styles()

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Detailed Diagnostic Report – {property_name}",
    )

    story = []
    meta = ddr_data.get("report_metadata", {})

    # ── Cover Block ───────────────────────────────────────────────────────────
    for text, style_key in [
        ("DETAILED DIAGNOSTIC REPORT", "title"),
        (meta.get("property_address", property_name), "subtitle"),
    ]:
        cell = Table([[Paragraph(text, styles[style_key])]], colWidths=[17.5*cm])
        cell.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), C_DARK),
            ("TOPPADDING",    (0,0),(-1,-1), 20 if style_key=="title" else 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6 if style_key=="title" else 20),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ]))
        story.append(cell)
    story.append(Spacer(1, 0.5*cm))

    # ── Section 1: Report Information ────────────────────────────────────────
    story += _section_header("1. REPORT INFORMATION", styles)
    story.append(_kv_table([
        ("Property Address",      meta.get("property_address", "Not Available")),
        ("Property Type",         meta.get("property_type", "Not Available")),
        ("Year of Construction",  meta.get("year_of_construction", "Not Available")),
        ("Building Age",          meta.get("building_age", "Not Available")),
        ("Inspection Date",       meta.get("inspection_date", "Not Available")),
        ("Inspected By",          meta.get("inspected_by", "Not Available")),
        ("Report Date",           meta.get("report_date", datetime.today().strftime("%d %B %Y"))),
        ("Previous Audit",        meta.get("previous_audit", "Not Available")),
        ("Previous Repairs",      meta.get("previous_repairs", "Not Available")),
    ], styles))
    story.append(Spacer(1, 0.3*cm))

    # ── Section 2: Property Issue Summary ────────────────────────────────────
    story += _section_header("2. PROPERTY ISSUE SUMMARY", styles)
    summary = ddr_data.get("property_issue_summary", {})
    story.append(Paragraph(summary.get("overview", "Not Available"), styles["body"]))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(f"<b>Total Issues Found:</b> {summary.get('total_issues_found', 'N/A')}", styles["body"]))

    for label, key in [("Critical Issues", "critical_issues"), ("Moderate Issues", "moderate_issues")]:
        items = summary.get(key, [])
        if items:
            story.append(Spacer(1, 0.15*cm))
            story.append(Paragraph(f"<b>{label}:</b>", styles["label"]))
            for item in items:
                story.append(Paragraph(f"• {item}", styles["bullet"]))
    story.append(Spacer(1, 0.3*cm))

    # ── Section 3: Area-wise Observations ────────────────────────────────────
    story += _section_header("3. AREA-WISE OBSERVATIONS", styles)

    for i, obs in enumerate(ddr_data.get("area_wise_observations", []), 1):
        area_name = obs.get("area_name", f"Area {i}")
        image_captions = obs.get("image_captions", [])

        area_items = [
            Paragraph(f"{i}. {area_name}", styles["h2"]),
            _kv_table([
                ("Problem Observed",       obs.get("negative_side", "Not Available")),
                ("Source / Cause Found",   obs.get("positive_side", "Not Available")),
                ("Thermal Reading",        obs.get("thermal_reading", "Not Available")),
                ("Thermal Interpretation", obs.get("thermal_interpretation", "Not Available")),
            ], styles),
            Spacer(1, 0.2*cm),
        ]

        matched_imgs = _match_images_to_area(area_name, image_captions, all_images)

        if matched_imgs:
            area_items.append(Paragraph("<b>Supporting Images:</b>", styles["label"]))
            area_items.append(Spacer(1, 0.1*cm))
            for pair in [matched_imgs[j:j+2] for j in range(0, len(matched_imgs), 2)]:
                row_cells = []
                for img_info in pair:
                    rl_img = _embed_image(img_info["image_bytes"], 7.5, 5.5)
                    row_cells.append(
                        [rl_img, Paragraph(img_info["label"], styles["caption"])]
                        if rl_img else [Paragraph("Image Not Available", styles["na"])]
                    )
                while len(row_cells) < 2:
                    row_cells.append([Paragraph("", styles["body"])])
                img_table = Table([row_cells], colWidths=[8.5*cm, 8.5*cm])
                img_table.setStyle(TableStyle([
                    ("VALIGN", (0,0),(-1,-1), "TOP"),
                    ("ALIGN",  (0,0),(-1,-1), "CENTER"),
                    ("TOPPADDING",    (0,0),(-1,-1), 4),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 4),
                    ("LEFTPADDING",   (0,0),(-1,-1), 4),
                    ("RIGHTPADDING",  (0,0),(-1,-1), 4),
                ]))
                area_items.append(img_table)
                area_items.append(Spacer(1, 0.15*cm))
        elif image_captions:
            area_items.append(Paragraph("<b>Referenced Images:</b>", styles["label"]))
            for cap in image_captions:
                area_items.append(Paragraph(f"• {cap}", styles["bullet"]))
            area_items.append(Paragraph(
                "Note: Images could not be automatically matched. Please refer to source documents.",
                styles["na"]
            ))

        area_items += [HRFlowable(width="100%", thickness=0.5, color=C_BORDER), Spacer(1, 0.2*cm)]
        story.append(KeepTogether(area_items[:6]))
        story += area_items[6:]

    # ── Section 4: Probable Root Cause ───────────────────────────────────────
    story += _section_header("4. PROBABLE ROOT CAUSE", styles)
    root = ddr_data.get("probable_root_cause", {})
    story.append(Paragraph(f"<b>Primary Cause:</b> {root.get('primary_cause', 'Not Available')}", styles["body"]))
    story.append(Spacer(1, 0.15*cm))
    factors = root.get("contributing_factors", [])
    if factors:
        story.append(Paragraph("<b>Contributing Factors:</b>", styles["label"]))
        for f in factors:
            story.append(Paragraph(f"• {f}", styles["bullet"]))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(root.get("cause_explanation", "Not Available"), styles["body"]))
    story.append(Spacer(1, 0.3*cm))

    # ── Section 5: Severity Assessment ───────────────────────────────────────
    story += _section_header("5. SEVERITY ASSESSMENT", styles)
    sev_list = ddr_data.get("severity_assessment", [])
    if sev_list:
        sev_rows = [[
            Paragraph("Area", styles["label"]),
            Paragraph("Severity", styles["label"]),
            Paragraph("Reasoning", styles["label"]),
        ]]
        for item in sev_list:
            sev = item.get("severity", "Moderate")
            sev_rows.append([
                Paragraph(item.get("area", ""), styles["body"]),
                Paragraph(f"<b>{sev}</b>", ParagraphStyle(
                    "SevCell", fontSize=9, fontName="Helvetica-Bold",
                    textColor=SEV_COLORS.get(sev, colors.grey)
                )),
                Paragraph(item.get("reasoning", ""), styles["body"]),
            ])
        sev_table = Table(sev_rows, colWidths=[5.5*cm, 2.5*cm, 9.5*cm])
        sev_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  C_LIGHT_BG),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("GRID",          (0,0),(-1,-1), 0.5, C_BORDER),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_WHITE, C_LIGHT_BG]),
        ]))
        story.append(sev_table)
    else:
        story.append(Paragraph("Not Available", styles["na"]))
    story.append(Spacer(1, 0.3*cm))

    # ── Section 6: Recommended Actions ───────────────────────────────────────
    story += _section_header("6. RECOMMENDED ACTIONS", styles)
    for j, action in enumerate(ddr_data.get("recommended_actions", []), 1):
        priority = action.get("priority", "Short-term")
        pri_color = PRI_COLORS.get(priority, colors.grey)
        action_items = [
            Paragraph(f"{j}. {action.get('action_title', 'Action')}", styles["h2"]),
            Paragraph(f"<b>Applies To:</b> {', '.join(action.get('applies_to', [])) or 'General'}", styles["body"]),
            Paragraph(f"<b>Priority:</b> <font color='#{_color_hex(pri_color)}'>{priority}</font>", styles["body"]),
            Paragraph(action.get("description", "Not Available"), styles["body"]),
            Spacer(1, 0.15*cm),
        ]
        story.append(KeepTogether(action_items))
    story.append(Spacer(1, 0.3*cm))

    # ── Section 7: Additional Notes ───────────────────────────────────────────
    story += _section_header("7. ADDITIONAL NOTES", styles)
    notes = ddr_data.get("additional_notes", [])
    if notes:
        for note in notes:
            story.append(Paragraph(f"• {note}", styles["bullet"]))
    else:
        story.append(Paragraph("Not Available", styles["na"]))
    story.append(Spacer(1, 0.3*cm))

    # ── Section 8: Missing or Unclear Information ─────────────────────────────
    story += _section_header("8. MISSING OR UNCLEAR INFORMATION", styles)
    for m in ddr_data.get("missing_or_unclear_information", ["Not Available"]):
        story.append(Paragraph(f"• {m}", styles["bullet"]))
    story.append(Spacer(1, 0.5*cm))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=C_ACCENT))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "This report is generated by an AI-assisted system based on provided inspection and thermal documents. "
        "It is intended as a diagnostic aid and does not replace a professional structural engineer's assessment. "
        f"Generated on: {datetime.today().strftime('%d %B %Y %H:%M')}",
        ParagraphStyle("Footer", fontSize=7.5, fontName="Helvetica-Oblique",
                       textColor=C_MUTED, alignment=TA_CENTER)
    ))

    doc.build(story)
    return buffer.getvalue()
