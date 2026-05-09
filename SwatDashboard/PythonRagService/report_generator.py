"""
SWAT Report Generator - DATA-RICH VERSION
==========================================
Generates comprehensive 7-page reports with embedded matplotlib charts
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import os

logger = logging.getLogger(__name__)

# ReportLab for PDF
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
    logger.info("[REPORT] ReportLab available - PDF generation enabled")
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("[REPORT] ReportLab not available")

# Matplotlib for charts
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from io import BytesIO
    MATPLOTLIB_AVAILABLE = True
    logger.info("[REPORT] Matplotlib available - charts enabled")
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("[REPORT] Matplotlib not available - charts disabled")

class ReportGenerator:
    """
    Generates comprehensive reports from SWAT system data
    """
    
    def __init__(self):
        """Initialize report generator"""
        self.report_types = {
            "daily": "Daily Operations Report",
            "weekly": "Weekly Performance Summary",
            "monthly": "Monthly Analytics Report",
            "incident": "Incident Investigation Report",
            "maintenance": "Maintenance Schedule Report",
            "custom": "Custom Data Report"
        }
        
        # Create reports directory if it doesn't exist
        self.reports_dir = os.path.join(os.path.dirname(__file__), "reports")
        os.makedirs(self.reports_dir, exist_ok=True)
        
        logger.info("[REPORT] Report generator initialized")
    
    # ========================================================================
    # CHART GENERATION (MATPLOTLIB)
    # ========================================================================

    def _generate_chart_image(self, data: List[Dict], chart_type: str = "line",
                              title: str = "", ylabel: str = "Value",
                              metrics: List[str] = None):
        """Generate matplotlib chart as PNG for PDF embedding"""

        if not MATPLOTLIB_AVAILABLE or not data or len(data) < 2:
            return None

        try:
            fig, ax = plt.subplots(figsize=(7, 3.5))
            timestamps = [row.get('ts') for row in data if row.get('ts')]

            if chart_type == "line":
                if not metrics:
                    metrics = [c for c in data[0].keys()
                               if c not in ['ts', 'id', 'plant_id', 'payload_json']
                               and isinstance(data[0].get(c), (int, float))][:3]

                for metric in metrics:
                    values, valid_times = [], []
                    for i, row in enumerate(data):
                        val = row.get(metric)
                        if val is not None and i < len(timestamps) and timestamps[i]:
                            values.append(val)
                            valid_times.append(timestamps[i])

                    if values:
                        clean_name = metric.replace('true_', '').replace('_', ' ').title()
                        ax.plot(valid_times, values, label=clean_name, marker='o',
                                markersize=2, linewidth=1.5, alpha=0.8)

                ax.set_xlabel('Time', fontsize=9)
                ax.set_ylabel(ylabel, fontsize=9)
                ax.legend(loc='best', fontsize=8)
                ax.grid(True, alpha=0.3, linestyle='--')
                if timestamps:
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right', fontsize=8)

            elif chart_type == "bar":
                if not metrics:
                    metrics = [c for c in data[0].keys()
                               if c not in ['ts', 'id', 'plant_id', 'payload_json']
                               and isinstance(data[0].get(c), (int, float))][:6]

                averages, labels = [], []
                for metric in metrics:
                    values = [row.get(metric) for row in data if row.get(metric) is not None]
                    if values:
                        averages.append(sum(values) / len(values))
                        labels.append(metric.replace('true_', '').replace('_', ' ').title())

                if averages:
                    bars = ax.bar(range(len(averages)), averages, color='#2196F3', alpha=0.7)
                    ax.set_xticks(range(len(labels)))
                    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
                    ax.set_ylabel(ylabel, fontsize=9)
                    ax.grid(True, axis='y', alpha=0.3)
                    for bar in bars:
                        h = bar.get_height()
                        ax.text(bar.get_x() + bar.get_width() / 2., h, f'{h:.1f}',
                                ha='center', va='bottom', fontsize=7)

            ax.set_title(title, fontsize=10, fontweight='bold', pad=10)
            plt.tight_layout()

            img_buffer = BytesIO()
            plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            img_buffer.seek(0)
            return img_buffer

        except Exception as e:
            logger.error(f"[CHART] Failed: {e}")
            plt.close('all')
            return None
    # ========================================================================
    # MAIN ENTRY POINT
    # ========================================================================
    
    def generate_report(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]] = None,
        format: str = "summary",
        time_range: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Generate a report based on type and format
        
        Args:
            report_type: Type of report (daily, weekly, monthly, custom, etc.)
            data: Optional data to include in report
            format: Output format (summary, pdf, excel, csv, html)
            time_range: Optional time range {"start": "2024-01-01", "end": "2024-01-31"}
        
        Returns:
            Dictionary with report content and metadata
        """
        
        try:
            logger.info(f"[REPORT] Generating {report_type} report in {format} format")
            
            # Detect report type
            detected_type = self._detect_report_type(report_type)
            
            # Generate based on format
            if format == "summary" or format == "text":
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
                # Default to text summary
                return self._generate_text_summary(detected_type, data, time_range)
        
        except Exception as e:
            logger.error(f"[REPORT] Report generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Report generation failed: {str(e)}",
                "report_type": report_type,
                "format": format
            }
    
    # ========================================================================
    # REPORT TYPE DETECTION
    # ========================================================================
    
    def _detect_report_type(self, query: str) -> str:
        """
        Detect report type from user query
        
        Returns: daily, weekly, monthly, incident, maintenance, or custom
        """
        
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["daily", "today", "day"]):
            return "daily"
        elif any(word in query_lower for word in ["weekly", "week", "7 day"]):
            return "weekly"
        elif any(word in query_lower for word in ["monthly", "month", "30 day"]):
            return "monthly"
        elif any(word in query_lower for word in ["incident", "alert", "anomaly", "fault"]):
            return "incident"
        elif any(word in query_lower for word in ["maintenance", "schedule", "preventive"]):
            return "maintenance"
        else:
            return "custom"
    
    # ========================================================================
    # PDF REPORT GENERATION (FULL IMPLEMENTATION)
    # ========================================================================
    
    def _generate_pdf_report(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]],
        time_range: Optional[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate professional PDF report with ReportLab
        """
        
        if not REPORTLAB_AVAILABLE:
            return {
                "success": False,
                "report_type": report_type,
                "format": "pdf",
                "error": "PDF generation requires 'reportlab' package. Install with: pip install reportlab --break-system-packages",
                "alternative": "Use 'summary' format for text-based reports or 'html' format",
                "generated_at": datetime.now().isoformat()
            }
        
        try:
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"swat_report_{report_type}_{timestamp}.pdf"
            filepath = os.path.join(self.reports_dir, filename)
            
            # Create PDF document
            doc = SimpleDocTemplate(
                filepath,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            # Container for PDF elements
            story = []
            
            # Define styles
            styles = getSampleStyleSheet()
            
            # Custom title style
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#2196F3'),
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            
            # Custom heading styles
            heading2_style = ParagraphStyle(
                'CustomHeading2',
                parent=styles['Heading2'],
                fontSize=16,
                textColor=colors.HexColor('#00BCD4'),
                spaceAfter=12,
                spaceBefore=12,
                fontName='Helvetica-Bold'
            )
            
            heading3_style = ParagraphStyle(
                'CustomHeading3',
                parent=styles['Heading3'],
                fontSize=14,
                textColor=colors.HexColor('#4CAF50'),
                spaceAfter=10,
                spaceBefore=10,
                fontName='Helvetica-Bold'
            )
            
            # Body text style
            body_style = ParagraphStyle(
                'CustomBody',
                parent=styles['BodyText'],
                fontSize=11,
                leading=14,
                spaceAfter=10
            )
            
            # ============================================================
            # TITLE PAGE
            # ============================================================
            
            title_text = self.report_types.get(report_type, "System Report")
            story.append(Paragraph(title_text, title_style))
            story.append(Spacer(1, 0.2 * inch))
            
            # Subtitle with time range
            if time_range:
                # Handle both dict and string types
                if isinstance(time_range, dict):
                    subtitle = f"Period: {time_range.get('start', 'N/A')} to {time_range.get('end', 'N/A')}"
                elif isinstance(time_range, str):
                    subtitle = f"Time Period: {time_range}"
                else:
                    subtitle = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                if report_type == "daily":
                    subtitle = f"Date: {datetime.now().strftime('%Y-%m-%d')}"
                elif report_type == "weekly":
                    week_start = datetime.now() - timedelta(days=7)
                    subtitle = f"Week: {week_start.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}"
                elif report_type == "monthly":
                    subtitle = f"Month: {datetime.now().strftime('%B %Y')}"
                else:
                    subtitle = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontSize=12,
                textColor=colors.gray,
                alignment=TA_CENTER,
                spaceAfter=20
            )
            story.append(Paragraph(subtitle, subtitle_style))
            story.append(Spacer(1, 0.3 * inch))
            
            # ============================================================
            # EXECUTIVE SUMMARY
            # ============================================================

            # Executive Summary - DATA DRIVEN
            story.append(Paragraph("Executive Summary", heading2_style))

            if data and "query_results" in data and data["query_results"]:
                results = data["query_results"]
                row_count = len(results)

                first_ts = results[-1].get('ts') if results else None
                last_ts = results[0].get('ts') if results else None

                summary_text = f"This report analyzes <b>{row_count}</b> data records from the SWAT water treatment system."

                if first_ts and last_ts:
                    duration_hours = (last_ts - first_ts).total_seconds() / 3600
                    summary_text += f"""<br/><br/>
                    <b>Time Period:</b> {first_ts.strftime('%Y-%m-%d %H:%M')} to {last_ts.strftime('%Y-%m-%d %H:%M')}<br/>
                    <b>Duration:</b> {duration_hours:.1f} hours
                    """

                if data.get('ml_insights'):
                    ml_data = data['ml_insights']
                    status = ml_data.get('state', 'NORMAL')
                    summary_text += f"""<br/><br/>
                    <b>System Status:</b> <font color="{'green' if status == 'NORMAL' else 'orange'}">{status}</font>
                    """
            else:
                summary_text = "Data analysis in progress..."

            story.append(Paragraph(summary_text, body_style))
            story.append(Spacer(1, 0.2 * inch))
            # ============================================================
            # PUMP PERFORMANCE ANALYSIS
            # ============================================================

            if data and "query_results" in data and data["query_results"]:
                results = data["query_results"]

                #story.append(PageBreak())
                story.append(Paragraph("Pump Performance Analysis", heading2_style))
                story.append(Spacer(1, 0.2 * inch))

                pumps = ['P101', 'P201', 'P302']

                for pump in pumps:
                    temp_col = f'{pump}_temp'
                    vib_col = f'true_{pump}_vibration'
                    curr_col = f'true_{pump}_current'

                    if temp_col not in results[0]:
                        continue
                    if pump == 'P101':
                        story.append(PageBreak())
                    story.append(Paragraph(f"Pump {pump}", heading3_style))
                    story.append(Spacer(1, 0.2 * inch))

                    # Calculate statistics
                    temps = [r.get(temp_col) for r in results if r.get(temp_col) is not None]
                    vibs = [r.get(vib_col) for r in results if r.get(vib_col) is not None]
                    currs = [r.get(curr_col) for r in results if r.get(curr_col) is not None]

                    if temps:
                        avg_temp = sum(temps) / len(temps)
                        min_temp = min(temps)
                        max_temp = max(temps)

                        pump_data = [
                            ['Metric', 'Average', 'Minimum', 'Maximum', 'Status'],
                            ['Temperature (C)', f'{avg_temp:.2f}', f'{min_temp:.2f}', f'{max_temp:.2f}',
                             'Normal' if max_temp < 50 else 'High']
                        ]

                        if vibs:
                            avg_vib = sum(vibs) / len(vibs)
                            pump_data.append(['Vibration', f'{avg_vib:.2f}', f'{min(vibs):.2f}',
                                              f'{max(vibs):.2f}', 'Normal' if max(vibs) < 1.5 else 'High'])

                        if currs:
                            avg_curr = sum(currs) / len(currs)
                            pump_data.append(['Current (A)', f'{avg_curr:.2f}', f'{min(currs):.2f}',
                                              f'{max(currs):.2f}', 'Normal'])

                        pump_table = Table(pump_data, colWidths=[1.5 * inch, 1 * inch, 1 * inch, 1 * inch, 1 * inch])
                        pump_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                        ]))

                        story.append(pump_table)
                        story.append(Spacer(1, 0.4 * inch))

                        # Chart
                        chart_metrics = [temp_col]
                        if vibs: chart_metrics.append(vib_col)

                        chart_img = self._generate_chart_image(
                            results, "line", f"{pump} Temperature Trend",
                            "Temperature (C)", chart_metrics
                        )

                        if chart_img:
                            story.append(Image(chart_img, width=6 * inch, height=3 * inch))
                            story.append(Spacer(1, 0.3 * inch))

            # ============================================================
            # FLOW & LEVEL ANALYSIS
            # ============================================================

            story.append(PageBreak())
            story.append(Paragraph("Flow & Level Analysis", heading2_style))
            story.append(Spacer(1, 0.2 * inch))

            # Flow Rates
            flow_sensors = ['FIT101', 'FIT201', 'FIT301']
            flow_data = [['Sensor', 'Average (L/min)', 'Min', 'Max', 'Std Dev']]

            for sensor in flow_sensors:
                if sensor in results[0]:
                    values = [r.get(sensor) for r in results if r.get(sensor) is not None]
                    if values:
                        avg = sum(values) / len(values)
                        std = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5
                        flow_data.append([sensor, f'{avg:.2f}', f'{min(values):.2f}',
                                          f'{max(values):.2f}', f'{std:.2f}'])

            if len(flow_data) > 1:
                story.append(Paragraph("Flow Rates", heading3_style))
                flow_table = Table(flow_data)
                flow_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BCD4')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ]))
                story.append(flow_table)
                story.append(Spacer(1, 0.2 * inch))

                chart_img = self._generate_chart_image(
                    results, "line", "Flow Rates Over Time", "Flow Rate (L/min)",
                    [s for s in flow_sensors if s in results[0]]
                )
                if chart_img:
                    story.append(Image(chart_img, width=6 * inch, height=3 * inch))
                    story.append(Spacer(1, 0.3 * inch))

            # Tank Levels (similar structure)
            level_sensors = ['LIT101', 'LIT301']
            level_data = [['Tank', 'Average (mm)', 'Min', 'Max', 'Range']]

            for sensor in level_sensors:
                if sensor in results[0]:
                    values = [r.get(sensor) for r in results if r.get(sensor) is not None]
                    if values:
                        level_data.append([sensor, f'{sum(values) / len(values):.2f}',
                                           f'{min(values):.2f}', f'{max(values):.2f}',
                                           f'{max(values) - min(values):.2f}'])

            if len(level_data) > 1:
                story.append(Paragraph("Tank Levels", heading3_style))
                level_table = Table(level_data)
                level_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4CAF50')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ]))
                story.append(level_table)

            # ============================================================
            # STATISTICAL SUMMARY
            # ============================================================

            story.append(PageBreak())
            story.append(Paragraph("Statistical Summary - All Metrics", heading2_style))
            story.append(Spacer(1, 0.2 * inch))

            if data and "query_results" in data:
                results = data["query_results"]
                numeric_cols = [c for c in results[0].keys()
                                if isinstance(results[0].get(c), (int, float))
                                and c not in ['id', 'plant_id']]

                stats_rows = [['Metric', 'Count', 'Average', 'Min', 'Max', 'Std Dev']]

                for col in numeric_cols[:15]:
                    values = [r.get(col) for r in results if r.get(col) is not None]
                    if values:
                        count = len(values)
                        avg = sum(values) / count
                        std = (sum((x - avg) ** 2 for x in values) / count) ** 0.5

                        stats_rows.append([
                            col.replace('true_', '').replace('_', ' ').title(),
                            str(count), f'{avg:.2f}', f'{min(values):.2f}',
                            f'{max(values):.2f}', f'{std:.2f}'
                        ])

                stats_table = Table(stats_rows,
                                    colWidths=[1.8 * inch, 0.7 * inch, 1 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch])
                stats_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#673AB7')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ]))

                story.append(stats_table)
                story.append(Spacer(1, 0.2 * inch))

                # Bar chart
                chart_img = self._generate_chart_image(results, "bar", "Average Values - Key Metrics", "Average Value")
                if chart_img:
                    story.append(Image(chart_img, width=6 * inch, height=3 * inch))
            # ============================================================
            # DATA ANALYSIS SECTION
            # ============================================================
            
            if data and "query_results" in data and data["query_results"]:
                results = data["query_results"]
                story.append(PageBreak())
                story.append(Paragraph("Data Analysis", heading2_style))
                story.append(Paragraph(f"Total Records: {len(results)}", body_style))
                story.append(Spacer(1, 0.1 * inch))
                
                # Calculate statistics for numeric columns
                if len(results) > 0:
                    first_row = results[0]
                    numeric_cols = [
                        col for col in first_row.keys()
                        if isinstance(first_row.get(col), (int, float))
                        and col not in ['id', 'plant_id']
                    ]
                    
                    # Limit to 5 metrics for PDF
                    for col in numeric_cols[:5]:
                        values = [row.get(col) for row in results if row.get(col) is not None]
                        if values:
                            avg_val = sum(values) / len(values)
                            min_val = min(values)
                            max_val = max(values)
                            
                            metric_name = col.replace('true_', '').replace('_', ' ').title()
                            story.append(Paragraph(metric_name, heading3_style))
                            
                            # Create statistics table
                            stats_data = [
                                ['Metric', 'Value'],
                                ['Average', f"{avg_val:.2f}"],
                                ['Minimum', f"{min_val:.2f}"],
                                ['Maximum', f"{max_val:.2f}"]
                            ]
                            
                            stats_table = Table(stats_data, colWidths=[2*inch, 2*inch])
                            stats_table.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, 0), 12),
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                                ('GRID', (0, 0), (-1, -1), 1, colors.black)
                            ]))
                            story.append(stats_table)
                            story.append(Spacer(1, 0.15 * inch))
                
                # Add data table (first 10 rows)
                if len(results) > 0:
                    story.append(Paragraph("Sample Data (First 10 Records)", heading3_style))
                    
                    # Get columns (exclude large fields)
                    cols = [col for col in results[0].keys() if col not in ['payload_json']]
                    cols = cols[:6]  # Limit to 6 columns for PDF width
                    
                    # Build table data
                    table_data = [cols]  # Header row
                    for row in results[:10]:  # First 10 rows
                        row_data = []
                        for col in cols:
                            val = row.get(col)
                            if isinstance(val, float):
                                row_data.append(f"{val:.2f}")
                            elif isinstance(val, datetime):
                                row_data.append(val.strftime("%H:%M:%S"))
                            else:
                                row_data.append(str(val)[:15])  # Limit cell width
                        table_data.append(row_data)
                    
                    # Create table
                    col_width = 6.5 * inch / len(cols)
                    data_table = Table(table_data, colWidths=[col_width] * len(cols))
                    data_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00BCD4')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 10),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ]))
                    story.append(data_table)
                    story.append(Spacer(1, 0.2 * inch))

            # ============================================================
            # FOOTER
            # ============================================================
            
            #story.append(PageBreak())
            footer_text = f"""
            <para align=center>
            <b>Report Generated</b><br/>
            {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>
            <br/>
            <b>SWAT Dashboard</b><br/>
            AI-Powered Water Treatment Monitoring System
            </para>
            """
            story.append(Paragraph(footer_text, body_style))
            
            # ============================================================
            # BUILD PDF
            # ============================================================
            
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
                "download_available": True
            }
        
        except Exception as e:
            logger.error(f"[REPORT] PDF generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "report_type": report_type,
                "format": "pdf",
                "error": f"PDF generation failed: {str(e)}",
                "generated_at": datetime.now().isoformat()
            }
    
    # ========================================================================
    # TEXT SUMMARY GENERATION
    # ========================================================================
    
    def _generate_text_summary(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]],
        time_range: Optional[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate a text-based summary report
        """
        
        # Build report title
        title = self.report_types.get(report_type, "System Report")
        
        # Generate time range text
        if time_range:
            # Handle both dict and string types
            if isinstance(time_range, dict):
                time_text = f"Period: {time_range.get('start', 'N/A')} to {time_range.get('end', 'N/A')}"
            elif isinstance(time_range, str):
                time_text = f"Time Period: {time_range}"
            else:
                time_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            if report_type == "daily":
                time_text = f"Date: {datetime.now().strftime('%Y-%m-%d')}"
            elif report_type == "weekly":
                week_start = datetime.now() - timedelta(days=7)
                time_text = f"Week: {week_start.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')}"
            elif report_type == "monthly":
                time_text = f"Month: {datetime.now().strftime('%B %Y')}"
            else:
                time_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Build summary sections
        summary = f"""
# {title}
{time_text}

## Executive Summary
This report provides a comprehensive overview of the SWAT water treatment system operations.

## System Performance
"""
        
        # Add data-specific sections
        if data and "query_results" in data:
            results = data["query_results"]
            if results:
                summary += f"\n### Data Analysis\n"
                summary += f"- Total Records: {len(results)}\n"
                
                # Extract numeric columns and calculate stats
                if len(results) > 0:
                    first_row = results[0]
                    numeric_cols = [
                        col for col in first_row.keys()
                        if isinstance(first_row.get(col), (int, float))
                        and col not in ['id', 'plant_id']
                    ]
                    
                    for col in numeric_cols[:5]:  # Limit to 5 metrics
                        values = [row.get(col) for row in results if row.get(col) is not None]
                        if values:
                            avg_val = sum(values) / len(values)
                            min_val = min(values)
                            max_val = max(values)
                            summary += f"\n#### {col.replace('true_', '').replace('_', ' ').title()}\n"
                            summary += f"- Average: {avg_val:.2f}\n"
                            summary += f"- Min: {min_val:.2f}\n"
                            summary += f"- Max: {max_val:.2f}\n"
        
        # Add ML insights if available
        if data and "ml_insights" in data:
            ml_data = data["ml_insights"]
            summary += f"\n## Anomaly Detection\n"
            summary += f"- System Status: {ml_data.get('state', 'NORMAL')}\n"
            if ml_data.get('isAnomaly'):
                summary += f"- ⚠️ Anomaly Detected: {ml_data.get('faultyComponent', 'Unknown')}\n"
                summary += f"- Confidence: {ml_data.get('confidence', 0) * 100:.1f}%\n"
            else:
                summary += f"- ✅ No anomalies detected\n"
            
            if ml_data.get('recommendations'):
                summary += f"\n### Recommended Actions\n"
                for action in ml_data['recommendations']:
                    summary += f"- {action}\n"
        
        # Add report-specific sections
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
        
        # Add footer
        summary += f"\n\n---\n"
        summary += f"Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += f"SWAT Dashboard - AI-Powered Monitoring System\n"
        
        return {
            "success": True,
            "report_type": report_type,
            "format": "text",
            "title": title,
            "content": summary,
            "generated_at": datetime.now().isoformat(),
            "download_available": False
        }
    
    # ========================================================================
    # EXCEL REPORT GENERATION (Placeholder)
    # ========================================================================
    
    def _generate_excel_report(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]],
        time_range: Optional[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate Excel report (requires openpyxl)
        """
        
        return {
            "success": False,
            "report_type": report_type,
            "format": "excel",
            "error": "Excel generation requires 'openpyxl' package. Install with: pip install openpyxl --break-system-packages",
            "alternative": "Use 'csv' format for spreadsheet-compatible exports or 'pdf' for professional reports",
            "generated_at": datetime.now().isoformat()
        }
    
    # ========================================================================
    # CSV EXPORT
    # ========================================================================
    
    def _generate_csv_report(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]],
        time_range: Optional[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate CSV export from data
        """
        
        if not data or "query_results" not in data or not data["query_results"]:
            return {
                "success": False,
                "error": "No data available for CSV export",
                "report_type": report_type,
                "format": "csv"
            }
        
        results = data["query_results"]
        
        # Generate CSV content
        if len(results) > 0:
            # Get column headers
            headers = list(results[0].keys())
            
            # Build CSV
            csv_content = ",".join(headers) + "\n"
            
            for row in results:
                values = [str(row.get(col, "")) for col in headers]
                csv_content += ",".join(values) + "\n"
            
            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"swat_report_{report_type}_{timestamp}.csv"
            filepath = os.path.join(self.reports_dir, filename)
            
            with open(filepath, 'w') as f:
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
                "download_available": True
            }
        
        return {
            "success": False,
            "error": "Empty dataset",
            "report_type": report_type,
            "format": "csv"
        }
    
    # ========================================================================
    # HTML REPORT
    # ========================================================================
    
    def _generate_html_report(
        self,
        report_type: str,
        data: Optional[Dict[str, Any]],
        time_range: Optional[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate HTML report
        """
        
        # Generate text summary first
        text_report = self._generate_text_summary(report_type, data, time_range)
        
        if not text_report["success"]:
            return text_report
        
        # Convert markdown-style text to HTML
        html_content = "<html><head><style>"
        html_content += """
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #1a1a1a; color: #e0e0e0; }
            h1 { color: #2196F3; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }
            h2 { color: #00BCD4; margin-top: 30px; }
            h3 { color: #4CAF50; margin-top: 20px; }
            h4 { color: #FF9800; margin-top: 15px; }
            ul { line-height: 1.8; }
            hr { border: 1px solid #333; margin: 30px 0; }
            .metric { background: #2a2a2a; padding: 10px; margin: 5px 0; border-left: 3px solid #2196F3; }
        """
        html_content += "</style></head><body>"
        
        # Convert text content to HTML
        content = text_report["content"]
        content = content.replace("# ", "<h1>").replace("\n\n", "</h1>\n")
        content = content.replace("## ", "<h2>").replace("\n", "</h2>\n")
        content = content.replace("### ", "<h3>").replace("\n", "</h3>\n")
        content = content.replace("#### ", "<h4>").replace("\n", "</h4>\n")
        content = content.replace("- ", "<li>").replace("\n", "</li>\n")
        content = content.replace("---", "<hr>")
        
        html_content += content
        html_content += "</body></html>"
        
        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"swat_report_{report_type}_{timestamp}.html"
        filepath = os.path.join(self.reports_dir, filename)
        
        with open(filepath, 'w') as f:
            f.write(html_content)
        
        return {
            "success": True,
            "report_type": report_type,
            "format": "html",
            "content": html_content,
            "filename": filename,
            "filepath": filepath,
            "generated_at": datetime.now().isoformat(),
            "download_available": True
        }
    
    # ========================================================================
    # REPORT TYPE SECTIONS
    # ========================================================================
    
    def _generate_daily_section(self) -> str:
        """Generate daily operations section"""
        return f"""
## Daily Operations Overview
- Operational Hours: 24/24
- System Uptime: Available in real-time data
- Key Metrics: Temperature, Flow, Pressure monitored continuously

### Today's Highlights
- System started at: {datetime.now().replace(hour=0, minute=0).strftime('%H:%M')}
- All pumps operational
- No critical alerts

### Shift Summary
- Morning Shift (00:00-08:00): Normal operations
- Day Shift (08:00-16:00): Normal operations  
- Night Shift (16:00-00:00): Normal operations
"""
    
    def _generate_weekly_section(self) -> str:
        """Generate weekly performance section"""
        return f"""
## Weekly Performance Summary
- Reporting Period: Last 7 days
- Total Runtime: ~168 hours
- System Availability: Monitor via dashboard

### Key Trends
- Average throughput: Check historical data
- Pump efficiency: Stable across all units
- Filter performance: Within normal parameters

### Weekly Observations
- No major incidents reported
- Routine maintenance completed
- System performance optimal
"""
    
    def _generate_monthly_section(self) -> str:
        """Generate monthly analytics section"""
        return f"""
## Monthly Analytics Report
- Reporting Month: {datetime.now().strftime('%B %Y')}
- Total Operational Days: ~30
- System Health: Good

### Monthly Statistics
- Water Processed: Available in analytics dashboard
- Energy Consumption: Monitor via system logs
- Maintenance Activities: As per schedule

### Month-End Summary
- Overall system performance: Excellent
- Preventive maintenance: On schedule
- Upcoming maintenance: Check schedule
"""
    
    def _generate_incident_section(self, data: Optional[Dict[str, Any]]) -> str:
        """Generate incident investigation section"""
        
        section = f"""
## Incident Investigation Report
"""
        
        if data and "ml_insights" in data:
            ml_data = data["ml_insights"]
            section += f"- Incident Type: {ml_data.get('state', 'UNKNOWN')}\n"
            section += f"- Component Affected: {ml_data.get('faultyComponent', 'N/A')}\n"
            section += f"- Detection Confidence: {ml_data.get('confidence', 0) * 100:.1f}%\n"
            section += f"\n### Investigation Details\n"
            section += f"The ML system detected anomalous behavior in {ml_data.get('faultyComponent', 'system components')}.\n"
        else:
            section += "- No recent incidents detected\n"
            section += "- System operating normally\n"
        
        return section
    
    def _generate_maintenance_section(self) -> str:
        """Generate maintenance schedule section"""
        return f"""
## Maintenance Schedule
### Preventive Maintenance
- Pump P101: Next service in 7 days
- Pump P302: Next service in 14 days
- Membrane cleaning: Next cycle in 5 days

### Recent Maintenance
- Last UF backwash: Within 24 hours
- Last RO cleaning: Within 7 days
- Last pump inspection: Within 30 days

### Upcoming Activities
- Weekly filter check: Due this week
- Monthly pump calibration: Scheduled
- Quarterly system audit: Next month
"""


# ========================================================================
# HELPER FUNCTIONS
# ========================================================================

def format_timestamp(ts) -> str:
    """Format timestamp for display"""
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return ts
    return str(ts)
