using Microsoft.AspNetCore.Mvc;
using SwatDashboard.Models;
using SwatDashboard.Services;

namespace SwatDashboard.Controllers
{
    [Route("api/[controller]")]
    [ApiController]
    public class AnalyticsController : ControllerBase
    {
        private readonly DatabaseService _databaseService;
        private readonly ILogger<AnalyticsController> _logger;

        public AnalyticsController(
            DatabaseService databaseService,
            ILogger<AnalyticsController> logger)
        {
            _databaseService = databaseService;
            _logger = logger;
        }

        [HttpGet("range")]
        public async Task<IActionResult> GetDataRange(
            [FromQuery] DateTime startTime,
            [FromQuery] DateTime endTime,
            [FromQuery] string? plantId = null)
        {
            try
            {
                var data = await _databaseService.GetDataRangeAsync(startTime, endTime, plantId);
                return Ok(data);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting data range");
                return StatusCode(500, new { error = ex.Message });
            }
        }

        [HttpGet("count")]
        public async Task<IActionResult> GetDataCount(
            [FromQuery] DateTime startTime,
            [FromQuery] DateTime endTime,
            [FromQuery] string? plantId = null)
        {
            try
            {
                var count = await _databaseService.GetDataCountAsync(startTime, endTime, plantId);
                return Ok(new { count });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting data count");
                return StatusCode(500, new { error = ex.Message });
            }
        }
    }
}
