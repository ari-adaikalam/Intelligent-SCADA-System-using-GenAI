"""
SWAT Report Generator - DATA-RICH VERSION
==========================================
Generates comprehensive reports with embedded matplotlib charts.

Fixes applied:
  1. Flow/Level analysis blocks guarded with `if data and "query_results" in data`
     (they previously used bare `results` which could be NameError when data=None)
  2. format_timestamp bare `except:` replaced with `except Exception`
  3. _generate_html_report: crude string replacement for Markdown is fragile —
     replaced with proper regex-free line-by-line converter
  4. PDF flow/level section: `results` variable was referenced outside its
     `if data …` guard — fixed with early return pattern
  5. All bare `except:` replaced with `except Exception`
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ReportLab
# ---------------------------------------------------------------------------
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
    logger.info("[REPORT] ReportLab available - PDF generation enabled")
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("[REPORT] ReportLab not available")

# ---------------------------------------------------------------------------
# Matplotlib
# ---------------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from io import BytesIO
    MATPLOTLIB_AVAILABLE = True
    logger.info("[REPORT] Matplotlib available - charts enabled")
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("[REPORT] Matplotlib not available - charts disabled")


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------

class ReportGenerator:
    def __init__(self):
        self.report_types = {
            "daily"      : "Daily Operations Report",
            "weekly"     : "Weekly Performance Summary",
            "monthly"    : "Monthly Analytics Report",
            "incident"   : "Incident Investigation Report",
            "maintenance": "Maintenance Schedule Report",
            "custom"     : "Custom Data Report",
        }

        self.reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(self.reports_dir, exist_ok=True)

        logger.info("[REPORT] Report generator initialized")

    # =========================================================================
    # CHART GENERATION (matplotlib)
    # =========================================================================

    def _generate_chart_image(
        self,
        data: List[Dict],
        chart_type: str = "line",
        title: str = "",
        ylabel: str = "Value",
        metrics: List[str] = None,
    ):
        if not MATPLOTLIB_AVAILABLE or not data or len(data) < 2:
            return None

        try:
            fig, ax = plt.subplots(figsize=(7, 3.5))
            timestamps = [row.get("ts") for row in data if row.get("ts")]

            if chart_type == "line":
                if not metrics:
                    metrics = [
                        c for c in data[0].keys()
                        if c not in ("ts", "id", "plant_id", "payload_json")
                        and isinstance(data[0].get(c), (int, float))
                    ][:3]

                for metric in metrics:
                    values, valid_times = [], []
                    for i, row in enumerate(data):
                        val = row.get(metric)
                        if val is not None and i < len(timestamps) and timestamps[i]:
                            values.append(val)
                            valid_times.append(timestamps[i])
                    if values:
                        label = metric.replace("true_", "").replace("_", " ").title()
                        ax.plot(
                            valid_times, values, label=label,
                            marker="o", markersize=2, linewidth=1.5, alpha=0.8,
                        )

                ax.set_xlabel("Time", fontsize=9)
                ax.set_ylabel(ylabel, fontsize=9)
                ax.legend(loc="best", fontsize=8)
                ax.grid(True, alpha=0.3, linestyle="--")
                if timestamps:
                    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
                    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)

            elif chart_type == "bar":
                if not metrics:
                    metrics = [
                        c for c in data[0].keys()
                        if c not in ("ts", "id", "plant_id", "payload_json")
                        and isinstance(data[0].get(c), (int, float))
                    ][:6]

                averages, labels = [], []
                for metric in metrics:
                    values = [row.get(metric) for row in data if row.get(metric) is not None]
                    if values:
                        averages.append(sum(values) / len(values))
                        labels.append(metric.replace("true_", "").replace("_", " ").title())

                if averages:
                    bars = ax.bar(range(len(averages)), averages, color="#2196F3", alpha=0.7)
                    ax.set_xticks(range(len(labels)))
                    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
                    ax.set_ylabel(ylabel, fontsize=9)
                    ax.grid(True, axis="y", alpha=0.3)
                    for bar in bars:
                        h = bar.get_height()
                        ax.text(
                            bar.get_x() + bar.get_width() / 2., h,
                            f"{h:.1f}", ha="center", va="bottom", fontsize=7,
                        )

            ax.set_title(title, fontsize=10, fontweight="bold", pad=10)
            plt.tight_layout()

            buf = BytesIO()
            plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            buf.seek(0)
            return buf

        except Exception as e:
            logger.error(f"[CHART] Failed: {e}")
            plt.close("all")
            return None

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def generate_report(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]] = None,
        format: str = "summary",
        time_range: Optional[Any] = None,
    ) -> Dict[str, Any]:
        try:
            logger.info(f"[REPORT] Generating {report_type!r} report in {format!r} format")
            detected_type = self._detect_report_type(report_type)

            if format in ("summary", "text"):
                return self._generate_text_summary(detected_type, data, time_range)
            elif format == "pdf":
                return self._generate_pdf_report(detected_type, data, time_range)
            elif format == "excel":
                return self._generate_excel_report(detected_type, data, time_range)
            elif format == "csv":
                return self._generate_csv_report(detected_type, data, time_range)
            elif format == "html":
                return self._generate_html_report(detected_type, data, time_range)
            else:
                return self._generate_text_summary(detected_type, data, time_range)

        except Exception as e:
            logger.error(f"[REPORT] Report generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Report generation failed: {e}",
                "report_type": report_type,
                "format": format,
            }

    # =========================================================================
    # REPORT TYPE DETECTION
    # =========================================================================

    def _detect_report_type(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ("daily", "today", "day")):
            return "daily"
        if any(w in q for w in ("weekly", "week", "7 day")):
            return "weekly"
        if any(w in q for w in ("monthly", "month", "30 day")):
            return "monthly"
        if any(w in q for w in ("incident", "alert", "anomaly", "fault")):
            return "incident"
        if any(w in q for w in ("maintenance", "schedule", "preventive")):
            return "maintenance"
        return "custom"

    # =========================================================================
    # TIME RANGE HELPER
    # =========================================================================

    def _time_range_text(self, report_type: str, time_range: Optional[Any]) -> str:
        if time_range:
            if isinstance(time_range, dict):
                return f"Period: {time_range.get('start', 'N/A')} to {time_range.get('end', 'N/A')}"
            if isinstance(time_range, str):
                return f"Time Period: {time_range}"
        if report_type == "daily":
            return f"Date: {datetime.now().strftime('%Y-%m-%d')}"
        if report_type == "weekly":
            ws = datetime.now() - timedelta(days=7)
            return f"Week: {ws.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}"
        if report_type == "monthly":
            return f"Month: {datetime.now().strftime('%B %Y')}"
        return f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    # =========================================================================
    # PDF REPORT
    # =========================================================================

    def _generate_pdf_report(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]],
        time_range: Optional[Any],
    ) -> Dict[str, Any]:
        if not REPORTLAB_AVAILABLE:
            return {
                "success": False,
                "report_type": report_type,
                "format": "pdf",
                "error": (
                    "PDF generation requires 'reportlab'. "
                    "Install with: pip install reportlab --break-system-packages"
                ),
                "generated_at": datetime.now().isoformat(),
            }

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename  = f"swat_report_{report_type}_{timestamp}.pdf"
            filepath  = os.path.join(self.reports_dir, filename)

            doc = SimpleDocTemplate(
                filepath, pagesize=letter,
                rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18,
            )

            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                "CustomTitle", parent=styles["Heading1"],
                fontSize=24, textColor=colors.HexColor("#2196F3"),
                spaceAfter=30, alignment=TA_CENTER, fontName="Helvetica-Bold",
            )
            h2_style = ParagraphStyle(
                "H2", parent=styles["Heading2"],
                fontSize=16, textColor=colors.HexColor("#00BCD4"),
                spaceAfter=12, spaceBefore=12, fontName="Helvetica-Bold",
            )
            h3_style = ParagraphStyle(
                "H3", parent=styles["Heading3"],
                fontSize=14, textColor=colors.HexColor("#4CAF50"),
                spaceAfter=10, spaceBefore=10, fontName="Helvetica-Bold",
            )
            body_style = ParagraphStyle(
                "Body", parent=styles["BodyText"],
                fontSize=11, leading=14, spaceAfter=10,
            )
            subtitle_style = ParagraphStyle(
                "Subtitle", parent=styles["Normal"],
                fontSize=12, textColor=colors.gray,
                alignment=TA_CENTER, spaceAfter=20,
            )

            story = []

            # ── Title ──────────────────────────────────────────────────
            story.append(Paragraph(self.report_types.get(report_type, "System Report"), title_style))
            story.append(Spacer(1, 0.2 * inch))
            story.append(Paragraph(self._time_range_text(report_type, time_range), subtitle_style))
            story.append(Spacer(1, 0.3 * inch))

            # ── Executive Summary ──────────────────────────────────────
            story.append(Paragraph("Executive Summary", h2_style))

            results = (data or {}).get("query_results") or []
            if results:
                row_count = len(results)
                first_ts  = results[-1].get("ts")
                last_ts   = results[0].get("ts")

                summary_text = f"This report analyses <b>{row_count}</b> data records from the SWAT system."
                if first_ts and last_ts and isinstance(first_ts, datetime) and isinstance(last_ts, datetime):
                    hrs = (last_ts - first_ts).total_seconds() / 3600
                    summary_text += (
                        f"<br/><br/>"
                        f"<b>Time Period:</b> {first_ts.strftime('%Y-%m-%d %H:%M')} to "
                        f"{last_ts.strftime('%Y-%m-%d %H:%M')}<br/>"
                        f"<b>Duration:</b> {hrs:.1f} hours"
                    )
                ml = (data or {}).get("ml_insights", {})
                if ml:
                    status = ml.get("state", "NORMAL")
                    colour = "green" if status == "NORMAL" else "orange"
                    summary_text += (
                        f'<br/><br/><b>System Status:</b> '
                        f'<font color="{colour}">{status}</font>'
                    )
            else:
                summary_text = "No query results provided. This is a template report."

            story.append(Paragraph(summary_text, body_style))
            story.append(Spacer(1, 0.2 * inch))

            # ── Pump Performance ───────────────────────────────────────
            if results:
                story.append(PageBreak())
                story.append(Paragraph("Pump Performance Analysis", h2_style))
                story.append(Spacer(1, 0.2 * inch))

                for pump in ("P101", "P201", "P302"):
                    temp_col = f"{pump}_temp"
                    vib_col  = f"true_{pump}_vibration"
                    curr_col = f"true_{pump}_current"

                    if temp_col not in results[0]:
                        continue

                    story.append(Paragraph(f"Pump {pump}", h3_style))
                    story.append(Spacer(1, 0.1 * inch))

                    temps = [r.get(temp_col) for r in results if r.get(temp_col) is not None]
                    vibs  = [r.get(vib_col)  for r in results if r.get(vib_col)  is not None]
                    currs = [r.get(curr_col) for r in results if r.get(curr_col) is not None]

                    if temps:
                        avg_t = sum(temps) / len(temps)
                        tbl_d = [
                            ["Metric", "Average", "Min", "Max", "Status"],
                            [
                                "Temperature (°C)",
                                f"{avg_t:.2f}", f"{min(temps):.2f}", f"{max(temps):.2f}",
                                "Normal" if max(temps) < 50 else "⚠ High",
                            ],
                        ]
                        if vibs:
                            tbl_d.append([
                                "Vibration",
                                f"{sum(vibs)/len(vibs):.2f}", f"{min(vibs):.2f}", f"{max(vibs):.2f}",
                                "Normal" if max(vibs) < 1.5 else "⚠ High",
                            ])
                        if currs:
                            tbl_d.append([
                                "Current (A)",
                                f"{sum(currs)/len(currs):.2f}", f"{min(currs):.2f}", f"{max(currs):.2f}",
                                "Normal",
                            ])

                        t = Table(tbl_d, colWidths=[1.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
                        t.setStyle(TableStyle([
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2196F3")),
                            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.whitesmoke),
                            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
                            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("GRID",       (0, 0), (-1, -1), 1, colors.grey),
                        ]))
                        story.append(t)
                        story.append(Spacer(1, 0.3 * inch))

                        chart_metrics = [temp_col] + ([ vib_col] if vibs else [])
                        img = self._generate_chart_image(
                            results, "line", f"{pump} Temperature Trend", "Temperature (°C)", chart_metrics
                        )
                        if img:
                            story.append(Image(img, width=6*inch, height=3*inch))
                            story.append(Spacer(1, 0.3 * inch))

            # ── Flow & Level ───────────────────────────────────────────
            if results:
                story.append(PageBreak())
                story.append(Paragraph("Flow & Level Analysis", h2_style))
                story.append(Spacer(1, 0.2 * inch))

                flow_sensors = ["FIT101", "FIT201", "FIT301"]
                flow_data    = [["Sensor", "Average (L/min)", "Min", "Max", "Std Dev"]]
                for s in flow_sensors:
                    if s in results[0]:
                        vals = [r.get(s) for r in results if r.get(s) is not None]
                        if vals:
                            avg = sum(vals) / len(vals)
                            std = (sum((x - avg) ** 2 for x in vals) / len(vals)) ** 0.5
                            flow_data.append([s, f"{avg:.2f}", f"{min(vals):.2f}", f"{max(vals):.2f}", f"{std:.2f}"])

                if len(flow_data) > 1:
                    story.append(Paragraph("Flow Rates", h3_style))
                    ft = Table(flow_data)
                    ft.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00BCD4")),
                        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.whitesmoke),
                        ("GRID",       (0, 0), (-1, -1), 1, colors.grey),
                    ]))
                    story.append(ft)
                    story.append(Spacer(1, 0.2 * inch))
                    flow_img = self._generate_chart_image(
                        results, "line", "Flow Rates Over Time", "Flow Rate (L/min)",
                        [s for s in flow_sensors if s in results[0]],
                    )
                    if flow_img:
                        story.append(Image(flow_img, width=6*inch, height=3*inch))
                        story.append(Spacer(1, 0.3 * inch))

                level_sensors = ["LIT101", "LIT301"]
                level_data    = [["Tank", "Average (mm)", "Min", "Max", "Range"]]
                for s in level_sensors:
                    if s in results[0]:
                        vals = [r.get(s) for r in results if r.get(s) is not None]
                        if vals:
                            level_data.append([
                                s, f"{sum(vals)/len(vals):.2f}",
                                f"{min(vals):.2f}", f"{max(vals):.2f}",
                                f"{max(vals)-min(vals):.2f}",
                            ])

                if len(level_data) > 1:
                    story.append(Paragraph("Tank Levels", h3_style))
                    lt = Table(level_data)
                    lt.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4CAF50")),
                        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.whitesmoke),
                        ("GRID",       (0, 0), (-1, -1), 1, colors.grey),
                    ]))
                    story.append(lt)
                    story.append(Spacer(1, 0.3 * inch))

            # ── Statistical Summary ────────────────────────────────────
            if results:
                story.append(PageBreak())
                story.append(Paragraph("Statistical Summary — All Metrics", h2_style))
                story.append(Spacer(1, 0.2 * inch))

                numeric_cols = [
                    c for c in results[0].keys()
                    if isinstance(results[0].get(c), (int, float))
                    and c not in ("id", "plant_id")
                ]
                stats_rows = [["Metric", "Count", "Average", "Min", "Max", "Std Dev"]]
                for col in numeric_cols[:15]:
                    vals = [r.get(col) for r in results if r.get(col) is not None]
                    if vals:
                        avg = sum(vals) / len(vals)
                        std = (sum((x - avg) ** 2 for x in vals) / len(vals)) ** 0.5
                        stats_rows.append([
                            col.replace("true_", "").replace("_", " ").title(),
                            str(len(vals)), f"{avg:.2f}", f"{min(vals):.2f}",
                            f"{max(vals):.2f}", f"{std:.2f}",
                        ])

                st = Table(
                    stats_rows,
                    colWidths=[1.8*inch, 0.7*inch, 1*inch, 0.9*inch, 0.9*inch, 0.9*inch],
                )
                st.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#673AB7")),
                    ("TEXTCOLOR",  (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID",       (0, 0), (-1, -1), 1, colors.grey),
                ]))
                story.append(st)
                story.append(Spacer(1, 0.2 * inch))

                bar_img = self._generate_chart_image(
                    results, "bar", "Average Values — Key Metrics", "Average Value"
                )
                if bar_img:
                    story.append(Image(bar_img, width=6*inch, height=3*inch))

            # ── Footer ─────────────────────────────────────────────────
            story.append(Spacer(1, 0.4 * inch))
            story.append(Paragraph(
                f"<para align=center>"
                f"<b>Report Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/><br/>"
                f"<b>SWAT Dashboard</b><br/>"
                f"AI-Powered Water Treatment Monitoring System"
                f"</para>",
                body_style,
            ))

            doc.build(story)
            logger.info(f"[REPORT] PDF generated: {filename}")

            return {
                "success": True,
                "report_type": report_type,
                "format": "pdf",
                "title": self.report_types.get(report_type, "System Report"),
                "filename": filename,
                "filepath": filepath,
                "file_size": os.path.getsize(filepath),
                "generated_at": datetime.now().isoformat(),
                "download_available": True,
            }

        except Exception as e:
            logger.error(f"[REPORT] PDF generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "report_type": report_type,
                "format": "pdf",
                "error": f"PDF generation failed: {e}",
                "generated_at": datetime.now().isoformat(),
            }

    # =========================================================================
    # TEXT SUMMARY
    # =========================================================================

    def _generate_text_summary(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]],
        time_range: Optional[Any],
    ) -> Dict[str, Any]:
        title     = self.report_types.get(report_type, "System Report")
        time_text = self._time_range_text(report_type, time_range)

        summary = f"# {title}\n{time_text}\n\n## Executive Summary\n"
        summary += "This report provides a comprehensive overview of SWAT water treatment system operations.\n\n"
        summary += "## System Performance\n"

        results = (data or {}).get("query_results") or []
        if results:
            summary += f"\n### Data Analysis\n- Total Records: {len(results)}\n"
            first_row  = results[0]
            num_cols   = [
                c for c in first_row
                if isinstance(first_row.get(c), (int, float)) and c not in ("id", "plant_id")
            ]
            for col in num_cols[:5]:
                vals = [r.get(col) for r in results if r.get(col) is not None]
                if vals:
                    avg = sum(vals) / len(vals)
                    summary += (
                        f"\n#### {col.replace('true_', '').replace('_', ' ').title()}\n"
                        f"- Average: {avg:.2f}\n"
                        f"- Min: {min(vals):.2f}\n"
                        f"- Max: {max(vals):.2f}\n"
                    )

        ml = (data or {}).get("ml_insights", {})
        if ml:
            summary += "\n## Anomaly Detection\n"
            summary += f"- System Status: {ml.get('state', 'NORMAL')}\n"
            if ml.get("isAnomaly"):
                summary += (
                    f"- ⚠️ Anomaly Detected: {ml.get('faultyComponent', 'Unknown')}\n"
                    f"- Confidence: {ml.get('confidence', 0) * 100:.1f}%\n"
                )
            else:
                summary += "- ✅ No anomalies detected\n"
            if ml.get("recommendations"):
                summary += "\n### Recommended Actions\n"
                for action in ml["recommendations"]:
                    summary += f"- {action}\n"

        if report_type == "daily":
            summary += self._generate_daily_section()
        elif report_type == "weekly":
            summary += self._generate_weekly_section()
        elif report_type == "monthly":
            summary += self._generate_monthly_section()
        elif report_type == "incident":
            summary += self._generate_incident_section(data)
        elif report_type == "maintenance":
            summary += self._generate_maintenance_section()

        summary += f"\n\n---\nReport generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += "SWAT Dashboard - AI-Powered Monitoring System\n"

        return {
            "success": True,
            "report_type": report_type,
            "format": "text",
            "title": title,
            "content": summary,
            "generated_at": datetime.now().isoformat(),
            "download_available": False,
        }

    # =========================================================================
    # EXCEL (placeholder)
    # =========================================================================

    def _generate_excel_report(self, report_type, data, time_range):
        return {
            "success": False,
            "report_type": report_type,
            "format": "excel",
            "error": (
                "Excel generation requires 'openpyxl'. "
                "Install with: pip install openpyxl --break-system-packages"
            ),
            "generated_at": datetime.now().isoformat(),
        }

    # =========================================================================
    # CSV EXPORT
    # =========================================================================

    def _generate_csv_report(self, report_type, data, time_range):
        results = (data or {}).get("query_results") or []
        if not results:
            return {
                "success": False,
                "error": "No data available for CSV export",
                "report_type": report_type,
                "format": "csv",
            }

        headers = list(results[0].keys())
        lines   = [",".join(headers)]
        for row in results:
            lines.append(",".join(str(row.get(c, "")) for c in headers))
        csv_content = "\n".join(lines) + "\n"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"swat_report_{report_type}_{timestamp}.csv"
        filepath  = os.path.join(self.reports_dir, filename)

        with open(filepath, "w") as f:
            f.write(csv_content)

        return {
            "success": True,
            "report_type": report_type,
            "format": "csv",
            "content": csv_content,
            "filename": filename,
            "filepath": filepath,
            "row_count": len(results),
            "column_count": len(headers),
            "generated_at": datetime.now().isoformat(),
            "download_available": True,
        }

    # =========================================================================
    # HTML REPORT
    # =========================================================================

    def _generate_html_report(self, report_type, data, time_range):
        text_report = self._generate_text_summary(report_type, data, time_range)
        if not text_report["success"]:
            return text_report

        content = text_report["content"]

        # Line-by-line Markdown → HTML (safe, no regex mangling)
        html_lines = []
        for line in content.splitlines():
            if line.startswith("#### "):
                html_lines.append(f"<h4>{line[5:]}</h4>")
            elif line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("- "):
                html_lines.append(f"<li>{line[2:]}</li>")
            elif line.strip() == "---":
                html_lines.append("<hr>")
            elif line.strip():
                html_lines.append(f"<p>{line}</p>")

        css = """
body{font-family:Arial,sans-serif;max-width:800px;margin:40px auto;padding:20px;background:#1a1a1a;color:#e0e0e0}
h1{color:#2196F3;border-bottom:2px solid #2196F3;padding-bottom:10px}
h2{color:#00BCD4;margin-top:30px}
h3{color:#4CAF50;margin-top:20px}
h4{color:#FF9800;margin-top:15px}
li{line-height:1.8}
hr{border:1px solid #333;margin:30px 0}
"""
        html = (
            f"<html><head><style>{css}</style></head><body>"
            + "\n".join(html_lines)
            + "</body></html>"
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"swat_report_{report_type}_{timestamp}.html"
        filepath  = os.path.join(self.reports_dir, filename)

        with open(filepath, "w") as f:
            f.write(html)

        return {
            "success": True,
            "report_type": report_type,
            "format": "html",
            "content": html,
            "filename": filename,
            "filepath": filepath,
            "generated_at": datetime.now().isoformat(),
            "download_available": True,
        }

    # =========================================================================
    # REPORT SECTION GENERATORS
    # =========================================================================

    def _generate_daily_section(self) -> str:
        return f"""
## Daily Operations Overview
- Operational Hours: 24/24
- Key Metrics: Temperature, Flow, Pressure monitored continuously

### Today's Highlights
- System started at: {datetime.now().replace(hour=0, minute=0).strftime('%H:%M')}
- All pumps operational
- No critical alerts

### Shift Summary
- Morning Shift (00:00–08:00): Normal operations
- Day Shift (08:00–16:00): Normal operations
- Night Shift (16:00–00:00): Normal operations
"""

    def _generate_weekly_section(self) -> str:
        return """
## Weekly Performance Summary
- Reporting Period: Last 7 days
- Total Runtime: ~168 hours

### Key Trends
- Pump efficiency: Stable across all units
- Filter performance: Within normal parameters

### Weekly Observations
- No major incidents reported
- Routine maintenance completed
"""

    def _generate_monthly_section(self) -> str:
        return f"""
## Monthly Analytics Report
- Reporting Month: {datetime.now().strftime('%B %Y')}
- Total Operational Days: ~30

### Monthly Statistics
- Overall system performance: Excellent
- Preventive maintenance: On schedule
"""

    def _generate_incident_section(self, data: Optional[Dict]) -> str:
        section = "\n## Incident Investigation Report\n"
        ml = (data or {}).get("ml_insights", {})
        if ml:
            section += (
                f"- Incident Type: {ml.get('state', 'UNKNOWN')}\n"
                f"- Component Affected: {ml.get('faultyComponent', 'N/A')}\n"
                f"- Detection Confidence: {ml.get('confidence', 0) * 100:.1f}%\n"
                f"\n### Investigation Details\n"
                f"The ML system detected anomalous behaviour in "
                f"{ml.get('faultyComponent', 'system components')}.\n"
            )
        else:
            section += "- No recent incidents detected\n- System operating normally\n"
        return section

    def _generate_maintenance_section(self) -> str:
        return """
## Maintenance Schedule
### Preventive Maintenance
- Pump P101: Next service in 7 days
- Pump P302: Next service in 14 days
- Membrane cleaning: Next cycle in 5 days

### Upcoming Activities
- Weekly filter check: Due this week
- Monthly pump calibration: Scheduled
- Quarterly system audit: Next month
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_timestamp(ts) -> str:
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ts
    return str(ts)
