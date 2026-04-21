"""Generate PDF documents from trip planning data."""

import io
from datetime import datetime
from typing import Any


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
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise RuntimeError(
            "PDF generation requires the `reportlab` package. Install project dependencies with `uv sync`."
        ) from exc

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

    def add_markdown_block(text: str, *, heading_text: str | None = None) -> None:
        if not text or not text.strip():
            return
        if heading_text:
            story.append(Paragraph(heading_text, heading_style))
        lines = text.split('\n')
        bullet_buffer: list[str] = []

        def flush_local_bullets() -> None:
            nonlocal bullet_buffer
            if bullet_buffer:
                for bullet_text in bullet_buffer:
                    story.append(Paragraph(f"<bullet>&bull;</bullet> {_convert_inline_markdown(bullet_text)}", bullet_style))
                bullet_buffer = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                flush_local_bullets()
                story.append(Spacer(1, 0.04 * inch))
                continue
            if line.startswith("- ") or line.startswith("* "):
                bullet_buffer.append(line[2:])
                continue
            flush_local_bullets()
            if line.startswith("##### "):
                story.append(Paragraph(f"<b>{_convert_inline_markdown(line[6:])}</b>", normal_style))
            elif line.startswith("#### "):
                story.append(Paragraph(f"<b>{_convert_inline_markdown(line[5:])}</b>", normal_style))
            elif line.startswith("### "):
                story.append(Paragraph(f"<b>{_convert_inline_markdown(line[4:])}</b>", normal_style))
            elif line.startswith("## "):
                story.append(Paragraph(_convert_inline_markdown(line[3:]), subheading_style))
            elif line.startswith("# "):
                story.append(Paragraph(_convert_inline_markdown(line[2:]), heading_style))
            else:
                story.append(Paragraph(_convert_inline_markdown(line), normal_style))
        flush_local_bullets()

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

    bullet_style = ParagraphStyle(
        'BulletStyle',
        parent=normal_style,
        leftIndent=20,
        bulletIndent=10,
        spaceAfter=4,
    )

    itinerary_data = graph_state.get("itinerary_data", {}) if isinstance(graph_state, dict) else {}
    if not isinstance(itinerary_data, dict):
        itinerary_data = {}

    story.append(Paragraph("Your Itinerary", heading_style))
    story.append(Spacer(1, 0.1 * inch))

    if itinerary_data:
        add_markdown_block(str(itinerary_data.get("trip_overview", "")).strip(), heading_text="Overview")

        legs = itinerary_data.get("legs", [])
        if isinstance(legs, list) and legs:
            story.append(Paragraph("Trip Legs", heading_style))
            leg_rows = [[Paragraph("<b>Route</b>", normal_style), Paragraph("<b>Details</b>", normal_style)]]
            for leg in legs:
                if not isinstance(leg, dict):
                    continue
                route = f"{leg.get('origin', '?')} → {leg.get('destination', '?')}"
                details_parts = []
                if leg.get("departure_date"):
                    details_parts.append(str(leg["departure_date"]))
                if leg.get("flight_summary"):
                    details_parts.append(str(leg["flight_summary"]))
                if leg.get("hotel_summary"):
                    details_parts.append(str(leg["hotel_summary"]))
                leg_rows.append([
                    Paragraph(_convert_inline_markdown(route), normal_style),
                    Paragraph(_convert_inline_markdown("<br/>".join(details_parts)), normal_style),
                ])
            leg_table = Table(leg_rows, colWidths=[1.7 * inch, 3.8 * inch])
            leg_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5f7fa')),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#dddddd')),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(leg_table)
            story.append(Spacer(1, 0.18 * inch))

        add_markdown_block(str(itinerary_data.get("flight_details", "")).strip(), heading_text="Flight Details")
        add_markdown_block(str(itinerary_data.get("hotel_details", "")).strip(), heading_text="Hotel Details")
        add_markdown_block(str(itinerary_data.get("destination_highlights", "")).strip(), heading_text="Destination Highlights")

        daily_plans = itinerary_data.get("daily_plans", [])
        if isinstance(daily_plans, list) and daily_plans:
            story.append(Paragraph("Day-by-Day Plan", heading_style))
            for day in daily_plans:
                if not isinstance(day, dict):
                    continue
                day_number = day.get("day_number", "?")
                theme = str(day.get("theme", "")).strip()
                date_text = str(day.get("date", "")).strip()
                day_title = f"Day {day_number}"
                if theme:
                    day_title += f" • {theme}"
                story.append(Paragraph(day_title, subheading_style))
                if date_text:
                    story.append(Paragraph(_convert_inline_markdown(date_text), normal_style))
                weather = day.get("weather", {})
                if isinstance(weather, dict) and weather:
                    condition = str(weather.get("condition", "")).strip()
                    temp_min = weather.get("temp_min")
                    temp_max = weather.get("temp_max")
                    weather_text = condition
                    if temp_min is not None and temp_max is not None:
                        weather_text = f"{condition} • {temp_min}° to {temp_max}°" if condition else f"{temp_min}° to {temp_max}°"
                    if weather_text:
                        story.append(Paragraph(_convert_inline_markdown(weather_text), normal_style))
                activities = day.get("activities", [])
                if isinstance(activities, list):
                    for activity in activities:
                        if not isinstance(activity, dict):
                            continue
                        activity_name = str(activity.get("name", "Activity")).strip()
                        time_of_day = str(activity.get("time_of_day", "")).strip()
                        notes = str(activity.get("notes", "")).strip()
                        address = str(activity.get("address", "")).strip()
                        bullet_text = activity_name
                        if time_of_day:
                            bullet_text = f"{time_of_day.title()}: {bullet_text}"
                        if notes:
                            bullet_text += f" — {notes}"
                        if address:
                            bullet_text += f" ({address})"
                        story.append(Paragraph(f"<bullet>&bull;</bullet> {_convert_inline_markdown(bullet_text)}", bullet_style))
                story.append(Spacer(1, 0.08 * inch))

        add_markdown_block(str(itinerary_data.get("budget_breakdown", "")).strip(), heading_text="Budget Breakdown")
        add_markdown_block(str(itinerary_data.get("visa_entry_info", "")).strip(), heading_text="Visa & Entry Information")
        add_markdown_block(str(itinerary_data.get("packing_tips", "")).strip(), heading_text="Packing Tips")

        sources = itinerary_data.get("sources", [])
        if isinstance(sources, list) and sources:
            story.append(Paragraph("Sources", heading_style))
            for source in sources:
                if not isinstance(source, dict):
                    continue
                document = str(source.get("document", "Source")).strip()
                snippet = str(source.get("snippet", "")).strip()
                source_text = document if not snippet else f"{document}: {snippet}"
                story.append(Paragraph(f"<bullet>&bull;</bullet> {_convert_inline_markdown(source_text)}", bullet_style))
    else:
        add_markdown_block(final_itinerary)

    # Build PDF
    doc.build(story)

    # Get bytes and reset buffer
    buffer.seek(0)
    return buffer.getvalue()
