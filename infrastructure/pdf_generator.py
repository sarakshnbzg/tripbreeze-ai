"""Generate PDF documents from trip planning data."""

import io
from datetime import datetime
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY


def _escape_xml(text: str) -> str:
    """Escape special XML characters for reportlab Paragraph."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _convert_inline_markdown(text: str) -> str:
    """Convert inline markdown (bold, italic) to reportlab XML tags.

    Handles **bold** and *italic* patterns within text.
    """
    import re

    # First escape XML special characters
    text = _escape_xml(text)

    # Convert **bold** to <b>bold</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # Convert *italic* to <i>italic</i> (but not inside already converted bold)
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<i>\1</i>', text)

    # Convert _italic_ to <i>italic</i>
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)

    return text


def generate_trip_pdf(
    final_itinerary: str,
    graph_state: dict[str, Any],
) -> bytes:
    """Generate a PDF from the trip planning data.

    Args:
        final_itinerary: The formatted itinerary text from the AI
        graph_state: The complete travel state containing selected flights, hotels, budget, etc.

    Returns:
        PDF bytes ready to be downloaded
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
    )

    styles = getSampleStyleSheet()

    # Define custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )

    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666'),
        spaceAfter=24,
        alignment=TA_CENTER,
        fontName='Helvetica-Oblique',
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold',
    )

    subheading_style = ParagraphStyle(
        'SubHeading',
        parent=styles['Heading3'],
        fontSize=11,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=8,
        spaceBefore=8,
        fontName='Helvetica-Bold',
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
    )

    # Build story (list of elements to add to PDF)
    story = []

    # Title and subtitle
    story.append(Paragraph("TripBreeze AI", title_style))
    timestamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    story.append(Paragraph(f"Trip Itinerary • Generated {timestamp}", subtitle_style))

    # Trip details summary
    selected_flight = graph_state.get("selected_flight", {})
    selected_hotel = graph_state.get("selected_hotel", {})
    budget = graph_state.get("budget", {})

    if selected_flight or selected_hotel or budget:
        story.append(Paragraph("Trip Summary", heading_style))

        # Build summary data
        summary_data = []

        if selected_flight:
            # Flight info - use outbound_summary for route details
            outbound_summary = selected_flight.get("outbound_summary", "")
            return_summary = selected_flight.get("return_summary", "")
            airline = selected_flight.get("airline", "Unknown")
            duration = selected_flight.get("duration", "")
            stops = selected_flight.get("stops", 0)
            stops_text = "Non-stop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
            total_price = selected_flight.get("total_price", selected_flight.get("price", 0))
            currency = selected_flight.get("currency", "EUR")
            adults = selected_flight.get("adults", 1)

            flight_details = f"<b>{airline}</b><br/>"
            if outbound_summary:
                flight_details += f"Outbound: {outbound_summary}<br/>"
            if return_summary and "require selecting" not in return_summary.lower():
                flight_details += f"Return: {return_summary}<br/>"
            flight_details += f"<font size=9>{duration} · {stops_text}</font><br/>"
            flight_details += f"<font size=9 color='#666666'>Total: {currency} {total_price} ({adults} traveler{'s' if adults > 1 else ''})</font>"

            summary_data.append([
                Paragraph("<b>Flight</b>", normal_style),
                Paragraph(flight_details, normal_style)
            ])

        if selected_hotel:
            # Hotel info
            hotel_name = selected_hotel.get("name", "Unknown Hotel")
            hotel_class = selected_hotel.get("hotel_class")
            stars = "⭐" * hotel_class if hotel_class else ""
            rating = selected_hotel.get("rating", "")
            total_price = selected_hotel.get("total_price", 0)
            price_per_night = selected_hotel.get("price_per_night", 0)
            currency = selected_hotel.get("currency", "EUR")
            check_in = selected_hotel.get("check_in", "")
            check_out = selected_hotel.get("check_out", "")

            hotel_details = f"<b>{hotel_name}</b>"
            if stars:
                hotel_details += f" {stars}"
            hotel_details += "<br/>"
            if check_in and check_out:
                hotel_details += f"<font size=9>{check_in} to {check_out}</font><br/>"
            if rating:
                hotel_details += f"<font size=9>Rating: {rating}/5</font><br/>"
            hotel_details += f"<font size=9 color='#666666'>{currency} {price_per_night}/night · Total: {currency} {total_price}</font>"

            summary_data.append([
                Paragraph("<b>Hotel</b>", normal_style),
                Paragraph(hotel_details, normal_style)
            ])

        if budget:
            total_estimated = budget.get("total_estimated", 0)
            budget_limit = budget.get("budget_limit")
            currency = budget.get("currency", "EUR")

            cost_text = f"<b>{currency} {total_estimated}</b>"
            if budget_limit:
                cost_text += f" / {currency} {budget_limit} budget"
            summary_data.append([
                Paragraph("<b>Total Cost</b>", normal_style),
                Paragraph(cost_text, normal_style)
            ])

        if summary_data:
            summary_table = Table(summary_data, colWidths=[1.5*inch, 4*inch])
            summary_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#DDDDDD')),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 0.25*inch))

    # Main itinerary content
    story.append(Paragraph("Your Itinerary", heading_style))
    story.append(Spacer(1, 0.1*inch))

    # Style for bullet points with proper indentation
    bullet_style = ParagraphStyle(
        'BulletStyle',
        parent=normal_style,
        leftIndent=20,
        bulletIndent=10,
        spaceAfter=4,
    )

    # Convert markdown-style itinerary to PDF-friendly format
    itinerary_paragraphs = final_itinerary.split('\n')
    current_bullets = []

    def flush_bullets():
        """Add accumulated bullet points as a list."""
        nonlocal current_bullets
        if current_bullets:
            for bullet_text in current_bullets:
                story.append(Paragraph(f"<bullet>&bull;</bullet> {_convert_inline_markdown(bullet_text)}", bullet_style))
            current_bullets = []

    for para in itinerary_paragraphs:
        para = para.strip()
        if not para:
            flush_bullets()
            story.append(Spacer(1, 0.05*inch))
        elif para.startswith('##### '):
            # Level 5 heading - treat as bold text
            flush_bullets()
            story.append(Paragraph(f"<b>{_convert_inline_markdown(para[6:])}</b>", normal_style))
        elif para.startswith('#### '):
            # Level 4 heading - treat as bold text
            flush_bullets()
            story.append(Paragraph(f"<b>{_convert_inline_markdown(para[5:])}</b>", normal_style))
        elif para.startswith('### '):
            flush_bullets()
            story.append(Paragraph(f"<b>{_convert_inline_markdown(para[4:])}</b>", normal_style))
        elif para.startswith('## '):
            flush_bullets()
            story.append(Paragraph(_convert_inline_markdown(para[3:]), subheading_style))
        elif para.startswith('# '):
            flush_bullets()
            story.append(Spacer(1, 0.1*inch))
            story.append(Paragraph(_convert_inline_markdown(para[2:]), heading_style))
        elif para.startswith('**') and para.endswith('**'):
            flush_bullets()
            story.append(Paragraph(f"<b>{_escape_xml(para[2:-2])}</b>", normal_style))
        elif para.startswith('- ') or para.startswith('* '):
            # Collect bullet points
            current_bullets.append(para[2:])
        else:
            flush_bullets()
            story.append(Paragraph(_convert_inline_markdown(para), normal_style))

    # Flush any remaining bullets
    flush_bullets()

    # Build PDF
    doc.build(story)

    # Get bytes and reset buffer
    buffer.seek(0)
    return buffer.getvalue()
