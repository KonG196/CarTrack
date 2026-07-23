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

from app.domain_labels import fuel_type_label, maintenance_item_label, repair_category_label
from app.currency import currency_symbol, format_money as _money
from app.i18n import normalize_lang, t
from app.models import Car, LogEntry, ServiceInterval
from app.services.fuel import compute_fuel_stats
from app.services.intervals import compute_interval_status, effective_avg_daily_km
from app.services.stats import build_refuel_points

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONT_NAME = "DejaVuSans"
FONT_NAME_BOLD = "DejaVuSans-Bold"

_STATUS_KEYS = {"ok": "report.status.ok", "due_soon": "report.status.dueSoon", "overdue": "report.status.overdue"}

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


def _fmt_money(value: float, currency: str) -> str:
    return _money(value, currency)


def _fmt_km(value: int | float | None, lang: str, units: str = "metric") -> str:
    if value is None:
        return "—"
    from app.units import distance_from_km, distance_unit

    shown = distance_from_km(float(value), units)
    return f"{_fmt_number(round(shown))} {distance_unit(units)}"


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


def _footer_drawer(lang: str):
    def _draw_footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(FONT_NAME, 8)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(doc.leftMargin, 11 * mm, "Kapot Tracker")
        canvas.drawRightString(
            A4[0] - doc.rightMargin, 11 * mm, t("report.page", lang, n=canvas.getPageNumber())
        )
        canvas.restoreState()

    return _draw_footer


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


def _service_log_description(log: LogEntry, lang: str) -> str:
    parts: list[str] = []
    if log.type == "maintenance" and log.maintenance is not None:
        items = ", ".join(maintenance_item_label(item, lang) for item in (log.maintenance.items or []))
        if items:
            parts.append(items)
    elif log.type == "repair" and log.repair is not None:
        repair = repair_category_label(log.repair.category, lang) or ""
        if log.repair.part_name:
            repair = f"{repair}: {log.repair.part_name}" if repair else log.repair.part_name
        if repair:
            parts.append(repair)
    if log.notes:
        parts.append(log.notes)
    return " — ".join(parts) if parts else "—"


def build_car_report(
    db: Session, car: Car, lang: str = "en", currency: str = "USD", units: str = "metric"
) -> bytes:
    lang = normalize_lang(lang)
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
    story.append(Paragraph(t("report.title", lang), styles["title"]))
    story.append(Spacer(1, 3 * mm))
    car_title = f"{car.brand} {car.model}, {car.year}"
    story.append(Paragraph(escape(car_title), styles["subtitle"]))
    details = " · ".join(part for part in (car.generation, car.engine) if part)
    if details:
        story.append(Paragraph(escape(details), styles["muted"]))
    story.append(
        Paragraph(t("report.generated", lang, date=_fmt_date(dt.date.today())), styles["muted"])
    )
    story.append(Spacer(1, 5 * mm))

    # --- 2. Car summary ---------------------------------------------------
    story.append(Paragraph(t("report.carHeading", lang), styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    avg_daily = round(effective_avg_daily_km(car, logs), 1) if len(logs) >= 2 else None
    summary_lines = [
        t("report.currentMileage", lang, km=_fmt_km(car.current_odometer, lang, units)),
        t("report.fuelType", lang, fuel=fuel_type_label(car.fuel_type, lang)),
        t(
            "report.avgDaily",
            lang,
            value=t("report.kmPerDay", lang, km=avg_daily) if avg_daily is not None else "—",
        ),
    ]
    for line in summary_lines:
        story.append(Paragraph(line, styles["body"]))
    story.append(Spacer(1, 5 * mm))

    # --- 3. Spending summary ----------------------------------------------
    story.append(Paragraph(t("report.spendingHeading", lang), styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    if not logs:
        story.append(Paragraph(t("report.noEntries", lang), styles["body"]))
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
        from app.units import (
            consumption_from_l100,
            consumption_unit,
            cost_per_distance_from_per_km,
            distance_unit,
        )

        cons = consumption_from_l100(fuel_stats.avg_consumption_l_100km, units)
        avg_consumption = (
            f"{cons:.1f} {consumption_unit(units)}" if cons is not None else "—"
        )
        cost_per_km = (
            f"{cost_per_distance_from_per_km(fuel_stats.avg_cost_per_km, units):.2f} "
            f"{currency_symbol(currency)}/{distance_unit(units)}"
            if fuel_stats.avg_cost_per_km is not None
            else "—"
        )
        first_date, last_date = logs[0].date, logs[-1].date
        spending_lines = [
            t("report.totalAllTime", lang, money=_fmt_money(all_time, currency)),
            t(
                "report.byTypeLine",
                lang,
                refuel=_fmt_money(by_type["refuel"], currency),
                maintenance=_fmt_money(by_type["maintenance"], currency),
                repair=_fmt_money(by_type["repair"], currency),
                expense=_fmt_money(by_type["expense"], currency),
            ),
            t("report.avgConsumption", lang, value=avg_consumption),
            t("report.costPerKm", lang, value=cost_per_km),
            t("report.dataPeriod", lang, start=_fmt_date(first_date), end=_fmt_date(last_date)),
        ]
        for line in spending_lines:
            story.append(Paragraph(line, styles["body"]))
    story.append(Spacer(1, 5 * mm))

    # --- 4. Service history table ------------------------------------------
    story.append(Paragraph(t("report.serviceHistoryHeading", lang), styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    service_logs = [log for log in logs if log.type in ("maintenance", "repair")]
    if not service_logs:
        story.append(Paragraph(t("report.noServiceEntries", lang), styles["body"]))
    else:
        rows = [
            [
                Paragraph(t("report.colDate", lang), styles["cell_bold"]),
                Paragraph(t("report.colMileage", lang), styles["cell_bold"]),
                Paragraph(t("report.colDescription", lang), styles["cell_bold"]),
                Paragraph(t("report.colCost", lang), styles["cell_bold"]),
            ]
        ]
        for log in service_logs:
            rows.append(
                [
                    Paragraph(_fmt_date(log.date), styles["cell"]),
                    Paragraph(_fmt_km(log.odometer, lang, units), styles["cell"]),
                    Paragraph(escape(_service_log_description(log, lang)), styles["cell"]),
                    Paragraph(_fmt_money(float(log.total_cost or 0), currency), styles["cell"]),
                ]
            )
        table = Table(rows, colWidths=[22 * mm, 24 * mm, 95 * mm, 26 * mm], repeatRows=1)
        table.setStyle(_base_table_style())
        story.append(table)
    story.append(Spacer(1, 5 * mm))

    # --- 5. Refuels summary --------------------------------------------------
    story.append(Paragraph(t("report.refuelsHeading", lang), styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    refuel_logs = [log for log in logs if log.type == "refuel" and log.refuel is not None]
    if not refuel_logs:
        story.append(Paragraph(t("report.noRefuels", lang), styles["body"]))
    else:
        total_liters = sum(float(log.refuel.liters) for log in refuel_logs)
        total_cost = sum(float(log.total_cost or 0) for log in refuel_logs)
        story.append(
            Paragraph(
                t(
                    "report.refuelsLine",
                    lang,
                    count=len(refuel_logs),
                    liters=_fmt_number(round(total_liters, 2)),
                    money=_fmt_money(total_cost, currency),
                ),
                styles["body"],
            )
        )
    story.append(Spacer(1, 5 * mm))

    # --- 6. Service intervals table ------------------------------------------
    story.append(Paragraph(t("report.intervalsHeading", lang), styles["heading"]))
    story.append(Spacer(1, 2 * mm))
    if not intervals:
        story.append(Paragraph(t("report.noIntervals", lang), styles["body"]))
    else:
        avg_daily_km = effective_avg_daily_km(car, logs)
        rows = [
            [
                Paragraph(t("report.colName", lang), styles["cell_bold"]),
                Paragraph(t("report.colLast", lang), styles["cell_bold"]),
                Paragraph(t("report.colNext", lang), styles["cell_bold"]),
                Paragraph(t("report.colStatus", lang), styles["cell_bold"]),
            ]
        ]
        for interval in intervals:
            computed = compute_interval_status(
                interval=interval,
                current_odometer=car.current_odometer,
                avg_daily_km=avg_daily_km,
            )
            last_text = f"{_fmt_km(interval.last_odometer, lang, units)} / {_fmt_date(interval.last_date)}"
            next_text = (
                f"{_fmt_km(computed['due_odometer'], lang, units)} / "
                f"{_fmt_date(computed['predicted_due_date'])}"
            )
            rows.append(
                [
                    Paragraph(escape(interval.title), styles["cell"]),
                    Paragraph(last_text, styles["cell"]),
                    Paragraph(next_text, styles["cell"]),
                    Paragraph(
                        t(_STATUS_KEYS.get(computed["status"], "report.status.ok"), lang),
                        styles["cell"],
                    ),
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
    footer = _footer_drawer(lang)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
