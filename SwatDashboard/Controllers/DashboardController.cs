using Microsoft.AspNetCore.Mvc;
using SwatDashboard.Models;
using SwatDashboard.Services;

namespace SwatDashboard.Controllers
{
    public class DashboardController : Controller
    {
        private readonly DatabaseService _databaseService;
        private readonly MlInferenceService _mlInferenceService;
        private readonly ExportService _exportService;
        private readonly ILogger<DashboardController> _logger;

        public DashboardController(
            DatabaseService databaseService,
            MlInferenceService mlInferenceService,
            ExportService exportService,
            ILogger<DashboardController> logger)
        {
            _databaseService = databaseService;
            _mlInferenceService = mlInferenceService;
            _exportService = exportService;
            _logger = logger;
        }

        public IActionResult Index()
        {
            return View();
        }

        [HttpGet]
        public async Task<IActionResult> GetLatestData()
        {
            try
            {
                var data = await _databaseService.GetLatestDataAsync();
                return Json(data);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting latest data");
                return StatusCode(500, new { error = ex.Message });
            }
        }

        [HttpGet]
        public async Task<IActionResult> GetRecentData(int count = 60)
        {
            try
            {
                var data = await _databaseService.GetLatestNDataAsync(count);
                return Json(data);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting recent data");
                return StatusCode(500, new { error = ex.Message });
            }
        }

        [HttpGet]
        public async Task<IActionResult> GetPlantIds()
        {
            try
            {
                var plantIds = await _databaseService.GetPlantIdsAsync();
                return Json(plantIds);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting plant IDs");
                return StatusCode(500, new { error = ex.Message });
            }
        }
    }
}
