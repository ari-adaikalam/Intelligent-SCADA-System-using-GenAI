using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using SwatDashboard.Models;
using SwatDashboard.Services;

namespace SwatDashboard.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    [EnableRateLimiting("export")]
    public class ExportController : ControllerBase
    {
        private readonly DatabaseService _databaseService;
        private readonly ExportService _exportService;
        private readonly ILogger<ExportController> _logger;

        public ExportController(
            DatabaseService databaseService,
            ExportService exportService,
            ILogger<ExportController> logger)
        {
            _databaseService = databaseService;
            _exportService = exportService;
            _logger = logger;
        }

        [HttpPost("excel")]
        public async Task<IActionResult> ExportToExcel([FromBody] ExportRequest request)
        {
            try
            {
                var data = await _databaseService.GetDataRangeAsync(
                    request.StartTime, 
                    request.EndTime, 
                    request.PlantId);

                var excelBytes = await _exportService.ExportToExcelAsync(data, request.Summary);
                
                var fileName = $"SwatData_{DateTime.Now:yyyyMMdd_HHmmss}.xlsx";
                return File(excelBytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", fileName);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error exporting to Excel");
                return StatusCode(500, new { error = "An error occurred processing your request." });
            }
        }

        [HttpPost("csv")]
        public async Task<IActionResult> ExportToCsv([FromBody] ExportRequest request)
        {
            try
            {
                var data = await _databaseService.GetDataRangeAsync(
                    request.StartTime, 
                    request.EndTime, 
                    request.PlantId);

                var csvBytes = _exportService.ExportToCsv(data);
                
                var fileName = $"SwatData_{DateTime.Now:yyyyMMdd_HHmmss}.csv";
                return File(csvBytes, "text/csv", fileName);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error exporting to CSV");
                return StatusCode(500, new { error = "An error occurred processing your request." });
            }
        }

        [HttpPost("pdf")]
        public async Task<IActionResult> ExportToPdf([FromBody] ExportRequest request)
        {
            try
            {
                var data = await _databaseService.GetDataRangeAsync(
                    request.StartTime, 
                    request.EndTime, 
                    request.PlantId);

                var pdfBytes = _exportService.ExportToPdf(data, request.Summary);
                
                var fileName = $"SwatData_{DateTime.Now:yyyyMMdd_HHmmss}.pdf";
                return File(pdfBytes, "application/pdf", fileName);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error exporting to PDF");
                return StatusCode(500, new { error = "An error occurred processing your request." });
            }
        }
    }

    public class ExportRequest
    {
        public DateTime StartTime { get; set; }
        public DateTime EndTime { get; set; }
        public string? PlantId { get; set; }
        public AnalyticsSummary? Summary { get; set; }
    }
}
