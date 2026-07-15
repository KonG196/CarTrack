"""PDF service-history report generation (reportlab platypus, A4 portrait)."""

from __future__ import annotations

import datetime as dt
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Car, LogEntry, ServiceInterval
from app.services.fuel import compute_fuel_stats
from app.services.intervals import compute_interval_status, effective_avg_daily_km
from app.services.stats import build_refuel_points

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_NAME = "DejaVuSans"
FONT_NAME_BOLD = "DejaVuSans-Bold"

FUEL_TYPE_LABELS = {
    "petrol": "Бензин",
    "diesel": "Дизель",
    "lpg": "ГБО",
    "electric": "Електро",
    "hybrid": "Гібрид",
}

STATUS_LABELS = {
    "ok": "ОК",
    "due_soon": "скоро",
    "overdue": "прострочено",
}

_fonts_registered = False


def _register_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_NAME_BOLD, str(FONTS_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        FONT_NAME,
        normal=FONT_NAME,
        bold=FONT_NAME_BOLD,
        italic=FONT_NAME,
        boldItalic=FONT_NAME_BOLD,
    )
    _fonts_registered = True


def _fmt_date(day: dt.date | None) -> str:
    if day is None:
        return "—"
    return day.strftime("%d.%m.%Y")


def _fmt_number(value: float) -> str:
    """Group thousands with spaces, keep cents only when non-zero."""
    if value == int(value):
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ")


def _fmt_money(value: float) -> str:
    return f"{_fmt_number(round(value, 2))} грн"


def _fmt_km(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{_fmt_number(round(float(value)))} км"


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title", fontName=FONT_NAME_BOLD, fontSize=16, leading=20,
            textColor=colors.HexColor("#111827"),
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName=FONT_NAME, fontSize=11, leading=15,
            textColor=colors.HexColor("#374151"),
        ),
        "muted": ParagraphStyle(
            "muted", fontName=FONT_NAME, fontSize=9, leading=12,
            textColor=colors.HexColor("#6b7280"),
        ),
        "heading": ParagraphStyle(
            "heading", fontName=FONT_NAME_BOLD, fontSize=12, leading=16,
            spaceBefore=6, textColor=colors.HexColor("#111827"),
        ),
        "body": ParagraphStyle(
            "body", fontName=FONT_NAME, fontSize=9.5, leading=13,
            textColor=colors.HexColor("#1f2937"),
        ),
        "cell": ParagraphStyle(
            "cell", fontName=FONT_NAME, fontSize=8.5, leading=11.5,
            textColor=colors.HexColor("#1f2937"),
        ),
        "cell_bold": ParagraphStyle(
            "cell_bold", fontName=FONT_NAME_BOLD, fontSize=8.5, leading=11.5,
            textColor=colors.HexColor("#111827"),
        ),
    }


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(doc.leftMargin, 11 * mm, "Kapot Tracker")
    canvas.drawRightString(A4[0] - doc.rightMargin, 11 * mm, f"Сторінка {canvas.getPageNumber()}")
    canvas.restoreState()


def _base_table_style() -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, 0), FONT_NAME_BOLD),
            ("FONTNAME", (0, 1), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
    )


def _service_log_description(log: LogEntry) -> str:
    parts: list[str] = []
    if log.type == "maintenance" and log.maintenance is not None:
        items = ", ".join(log.maintenance.items or [])
        if items:
            parts.append(items)
    elif log.type == "repair" and log.repair is not None:
        repair = log.repair.category or ""
        if log.repair.part_name:
            repair = f"{repair}: {log.repair.part_name}" if repair else log.repair.part_name
        if repair:
            parts.append(repair)
    if log.notes:
        parts.append(log.notes)
    return " — ".join(parts) if parts else "—"


def build_car_report(db: Session, car: Car) -> bytes:
    _register_fonts()
    styles = _styles()

    logs = (
        db.execute(
            select(LogEntry)
            .where(LogEntry.car_id == car.id)
            .order_by(LogEntry.date, LogEntry.odometer)
            .options(
                selectinload(LogEntry.refuel),
                selectinload(LogEntry.maintenance),
                selectinload(LogEntry.repair),
                selectinload(LogEntry.expense),
            )
        )
        .scalars()
        .all()
    )
    intervals = (
        db.execute(
            select(ServiceInterval)
            .where(ServiceInterval.car_id == car.id)
            .order_by(ServiceInterval.id)
        )
        .scalars()
        .all()
    )

    story: list = []

    # --- 1. Header -------------------------------------------------------
    story.append(Paragraph("Kapot Tracker — Сервісна історія", styles["title"]))
    story.append(Spacer(1, 3 * mm))
    car_title = f"{car.brand} {car.model}, {car.year}"
    story.append(Paragraph(escape(car_title), styles["subtitle"]))
    details = " · ".join(part for part in (car.generation, car.engine) if part)
    if details:
        story.append(Paragraph(escape(details), styles["muted"]))
    story.append(
        Paragraph(f"Звіт згенеровано: {_fmt_date(dt.date.today())}", styles["muted"])
    )
    story.append(Spacer(1, 5 * mm))

    # --- 2. Car summary ---------------------------------------------------
    story.append(Paragraph("Авто", styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    avg_daily = round(effective_avg_daily_km(car, logs), 1) if len(logs) >= 2 else None
    fuel_label = FUEL_TYPE_LABELS.get(car.fuel_type, car.fuel_type)
    summary_lines = [
        f"Поточний пробіг: {_fmt_km(car.current_odometer)}",
        f"Тип пального: {fuel_label}",
        f"Середній добовий пробіг: {f'{avg_daily} км/день' if avg_daily is not None else '—'}",
    ]
    for line in summary_lines:
        story.append(Paragraph(line, styles["body"]))
    story.append(Spacer(1, 5 * mm))

    # --- 3. Spending summary ----------------------------------------------
    story.append(Paragraph("Підсумки витрат", styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    if not logs:
        story.append(Paragraph("Записів поки немає.", styles["body"]))
    else:
        by_type = {"refuel": 0.0, "maintenance": 0.0, "repair": 0.0, "expense": 0.0}
        for log in logs:
            by_type[log.type] += float(log.total_cost or 0)
        all_time = sum(by_type.values())
        # The car's own fuel, matching the `fuel.*` block of the analytics
        # screen: a ГБО car's report is about its gas, not about a blend.
        fuel_stats = compute_fuel_stats(
            build_refuel_points(logs, car), fuel_kind=car.fuel_type
        )
        avg_consumption = (
            f"{fuel_stats.avg_consumption_l_100km} л/100 км"
            if fuel_stats.avg_consumption_l_100km is not None
            else "—"
        )
        cost_per_km = (
            f"{fuel_stats.avg_cost_per_km:.2f} грн/км"
            if fuel_stats.avg_cost_per_km is not None
            else "—"
        )
        first_date, last_date = logs[0].date, logs[-1].date
        spending_lines = [
            f"Сума за весь час: {_fmt_money(all_time)}",
            (
                f"Заправки: {_fmt_money(by_type['refuel'])} · "
                f"ТО: {_fmt_money(by_type['maintenance'])} · "
                f"Ремонти: {_fmt_money(by_type['repair'])} · "
                f"Інші: {_fmt_money(by_type['expense'])}"
            ),
            f"Середній розхід: {avg_consumption}",
            f"Вартість 1 км: {cost_per_km}",
            f"Період даних: {_fmt_date(first_date)} — {_fmt_date(last_date)}",
        ]
        for line in spending_lines:
            story.append(Paragraph(line, styles["body"]))
    story.append(Spacer(1, 5 * mm))

    # --- 4. Service history table ------------------------------------------
    story.append(Paragraph("Сервісна історія", styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    service_logs = [log for log in logs if log.type in ("maintenance", "repair")]
    if not service_logs:
        story.append(Paragraph("Записів про ТО та ремонти поки немає.", styles["body"]))
    else:
        rows = [
            [
                Paragraph("Дата", styles["cell_bold"]),
                Paragraph("Пробіг", styles["cell_bold"]),
                Paragraph("Опис", styles["cell_bold"]),
                Paragraph("Вартість", styles["cell_bold"]),
            ]
        ]
        for log in service_logs:
            rows.append(
                [
                    Paragraph(_fmt_date(log.date), styles["cell"]),
                    Paragraph(_fmt_km(log.odometer), styles["cell"]),
                    Paragraph(escape(_service_log_description(log)), styles["cell"]),
                    Paragraph(_fmt_money(float(log.total_cost or 0)), styles["cell"]),
                ]
            )
        table = Table(rows, colWidths=[22 * mm, 24 * mm, 95 * mm, 26 * mm], repeatRows=1)
        table.setStyle(_base_table_style())
        story.append(table)
    story.append(Spacer(1, 5 * mm))

    # --- 5. Refuels summary --------------------------------------------------
    story.append(Paragraph("Заправки", styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    refuel_logs = [log for log in logs if log.type == "refuel" and log.refuel is not None]
    if not refuel_logs:
        story.append(Paragraph("Заправок поки немає.", styles["body"]))
    else:
        total_liters = sum(float(log.refuel.liters) for log in refuel_logs)
        total_cost = sum(float(log.total_cost or 0) for log in refuel_logs)
        story.append(
            Paragraph(
                (
                    f"Кількість заправок: {len(refuel_logs)} · "
                    f"Всього літрів: {_fmt_number(round(total_liters, 2))} л · "
                    f"Всього: {_fmt_money(total_cost)}"
                ),
                styles["body"],
            )
        )
    story.append(Spacer(1, 5 * mm))

    # --- 6. Service intervals table ------------------------------------------
    story.append(Paragraph("Сервісні інтервали", styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    if not intervals:
        story.append(Paragraph("Сервісних інтервалів поки немає.", styles["body"]))
    else:
        avg_daily_km = effective_avg_daily_km(car, logs)
        rows = [
            [
                Paragraph("Назва", styles["cell_bold"]),
                Paragraph("Останнє виконання", styles["cell_bold"]),
                Paragraph("Наступне", styles["cell_bold"]),
                Paragraph("Статус", styles["cell_bold"]),
            ]
        ]
        for interval in intervals:
            computed = compute_interval_status(
                interval=interval,
                current_odometer=car.current_odometer,
                avg_daily_km=avg_daily_km,
            )
            last_text = f"{_fmt_km(interval.last_odometer)} / {_fmt_date(interval.last_date)}"
            next_text = (
                f"{_fmt_km(computed['due_odometer'])} / "
                f"{_fmt_date(computed['predicted_due_date'])}"
            )
            rows.append(
                [
                    Paragraph(escape(interval.title), styles["cell"]),
                    Paragraph(last_text, styles["cell"]),
                    Paragraph(next_text, styles["cell"]),
                    Paragraph(STATUS_LABELS.get(computed["status"], computed["status"]), styles["cell"]),
                ]
            )
        table = Table(rows, colWidths=[55 * mm, 42 * mm, 42 * mm, 28 * mm], repeatRows=1)
        table.setStyle(_base_table_style())
        story.append(table)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"Kapot Tracker — {car_title}",
        author="Kapot Tracker",
    )
    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
