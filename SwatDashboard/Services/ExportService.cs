using SwatDashboard.Models;
using OfficeOpenXml;
using System.Text;
using iText.Kernel.Pdf;
using iText.Layout;
using iText.Layout.Element;
using iText.Layout.Properties;

namespace SwatDashboard.Services
{
    public class ExportService
    {
        private readonly ILogger<ExportService> _logger;

        public ExportService(ILogger<ExportService> logger)
        {
            _logger = logger;
            // Set EPPlus license context (required for version 5+)
            ExcelPackage.LicenseContext = LicenseContext.NonCommercial;
        }

        public async Task<byte[]> ExportToExcelAsync(List<RawPlantData> data, AnalyticsSummary? summary = null)
        {
            try
            {
                using var package = new ExcelPackage();
                
                // Summary sheet
                if (summary != null)
                {
                    var summarySheet = package.Workbook.Worksheets.Add("Summary");
                    summarySheet.Cells["A1"].Value = "Metric";
                    summarySheet.Cells["B1"].Value = "Value";
                    
                    summarySheet.Cells["A2"].Value = "Total Samples";
                    summarySheet.Cells["B2"].Value = summary.TotalSamples;
                    
                    summarySheet.Cells["A3"].Value = "Online %";
                    summarySheet.Cells["B3"].Value = summary.OnlinePercentage;
                    
                    summarySheet.Cells["A4"].Value = "Downtime %";
                    summarySheet.Cells["B4"].Value = summary.DowntimePercentage;
                    
                    summarySheet.Cells["A5"].Value = "Start Time";
                    summarySheet.Cells["B5"].Value = summary.StartTime.ToString("yyyy-MM-dd HH:mm:ss");
                    
                    summarySheet.Cells["A6"].Value = "End Time";
                    summarySheet.Cells["B6"].Value = summary.EndTime.ToString("yyyy-MM-dd HH:mm:ss");
                    
                    summarySheet.Cells["A1:B1"].Style.Font.Bold = true;
                    summarySheet.Cells.AutoFitColumns();
                }

                // Raw data sheet
                var dataSheet = package.Workbook.Worksheets.Add("Raw Data");
                dataSheet.Cells["A1"].Value = "ID";
                dataSheet.Cells["B1"].Value = "Timestamp";
                dataSheet.Cells["C1"].Value = "Plant ID";
                dataSheet.Cells["D1"].Value = "Payload JSON";
                
                int row = 2;
                foreach (var item in data)
                {
                    dataSheet.Cells[$"A{row}"].Value = item.Id;
                    dataSheet.Cells[$"B{row}"].Value = item.Ts.ToString("yyyy-MM-dd HH:mm:ss");
                    dataSheet.Cells[$"C{row}"].Value = item.PlantId;
                    dataSheet.Cells[$"D{row}"].Value = item.PayloadJson;
                    row++;
                }
                
                dataSheet.Cells["A1:D1"].Style.Font.Bold = true;
                dataSheet.Cells.AutoFitColumns();

                return await package.GetAsByteArrayAsync();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error exporting to Excel");
                throw;
            }
        }

        public byte[] ExportToCsv(List<RawPlantData> data)
        {
            try
            {
                var csv = new StringBuilder();
                csv.AppendLine("ID,Timestamp,Plant ID,Payload JSON");

                foreach (var item in data)
                {
                    csv.AppendLine($"{item.Id},{item.Ts:yyyy-MM-dd HH:mm:ss},{item.PlantId},\"{item.PayloadJson.Replace("\"", "\"\"")}\"");
                }

                return Encoding.UTF8.GetBytes(csv.ToString());
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error exporting to CSV");
                throw;
            }
        }

        public byte[] ExportToPdf(List<RawPlantData> data, AnalyticsSummary? summary = null)
        {
            try
            {
                using var memoryStream = new MemoryStream();
                using var writer = new PdfWriter(memoryStream);
                using var pdf = new PdfDocument(writer);
                using var document = new Document(pdf);

                // Title
                document.Add(new Paragraph("Sewage Water Treatment Plant - Analytics Report")
                    .SetFontSize(20)
                    .SetBold()
                    .SetTextAlignment(TextAlignment.CENTER));

                document.Add(new Paragraph($"Generated: {DateTime.Now:yyyy-MM-dd HH:mm:ss}")
                    .SetFontSize(10)
                    .SetTextAlignment(TextAlignment.CENTER));

                document.Add(new Paragraph("\n"));

                // Summary section
                if (summary != null)
                {
                    document.Add(new Paragraph("Summary")
                        .SetFontSize(16)
                        .SetBold());

                    var summaryTable = new Table(2);
                    summaryTable.AddHeaderCell("Metric");
                    summaryTable.AddHeaderCell("Value");
                    
                    summaryTable.AddCell("Total Samples");
                    summaryTable.AddCell(summary.TotalSamples.ToString());
                    
                    summaryTable.AddCell("Online %");
                    summaryTable.AddCell($"{summary.OnlinePercentage:F2}%");
                    
                    summaryTable.AddCell("Downtime %");
                    summaryTable.AddCell($"{summary.DowntimePercentage:F2}%");
                    
                    summaryTable.AddCell("Time Range");
                    summaryTable.AddCell($"{summary.StartTime:yyyy-MM-dd HH:mm:ss} to {summary.EndTime:yyyy-MM-dd HH:mm:ss}");
                    
                    document.Add(summaryTable);
                    document.Add(new Paragraph("\n"));
                }

                // Data table (limited to first 100 rows for PDF)
                document.Add(new Paragraph("Sample Data (First 100 Rows)")
                    .SetFontSize(16)
                    .SetBold());

                var dataTable = new Table(new float[] { 1, 3, 2 });
                dataTable.AddHeaderCell("ID");
                dataTable.AddHeaderCell("Timestamp");
                dataTable.AddHeaderCell("Plant ID");

                foreach (var item in data.Take(100))
                {
                    dataTable.AddCell(item.Id.ToString());
                    dataTable.AddCell(item.Ts.ToString("yyyy-MM-dd HH:mm:ss"));
                    dataTable.AddCell(item.PlantId);
                }

                document.Add(dataTable);

                document.Close();
                return memoryStream.ToArray();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error exporting to PDF");
                throw;
            }
        }
    }
}
