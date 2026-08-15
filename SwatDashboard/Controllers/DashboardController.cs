using Microsoft.AspNetCore.Mvc;
using SwatDashboard.Models;
using SwatDashboard.Services;
using System.Net;

namespace SwatDashboard.Controllers
{
    public class DashboardController : Controller
    {
        private readonly DatabaseService _databaseService;
        private readonly MlInferenceService _mlInferenceService;
        private readonly ExportService _exportService;
        private readonly ILogger<DashboardController> _logger;
        private readonly IHttpClientFactory _httpClientFactory;

        // Shared browser-mimicking client for ServiceStatus checks.
        // Static so it's not recreated on every request.
        private static readonly HttpClient _statusClient = new HttpClient(
            new SocketsHttpHandler
            {
                AutomaticDecompression = DecompressionMethods.GZip
                                       | DecompressionMethods.Deflate
                                       | DecompressionMethods.Brotli,
                AllowAutoRedirect = true,
            })
        {
            Timeout = TimeSpan.FromSeconds(30)
        };

        public DashboardController(
            DatabaseService databaseService,
            MlInferenceService mlInferenceService,
            ExportService exportService,
            ILogger<DashboardController> logger,
            IHttpClientFactory httpClientFactory)
        {
            _databaseService = databaseService;
            _mlInferenceService = mlInferenceService;
            _exportService = exportService;
            _logger = logger;
            _httpClientFactory = httpClientFactory;
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
                return StatusCode(500, new { error = "An error occurred processing your request." });
            }
        }

        [HttpGet]
        public async Task<IActionResult> GetRecentData(int count = 60)
        {
            try
            {
                // Clamp to a sane range — the dashboard itself only ever asks for
                // a small window (SparklineRows), this just stops a crafted
                // ?count=2000000000 from forcing a huge scan/sort.
                count = Math.Clamp(count, 1, 5000);
                var data = await _databaseService.GetLatestNDataAsync(count);
                return Json(data);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting recent data");
                return StatusCode(500, new { error = "An error occurred processing your request." });
            }
        }

        [HttpGet]
        public async Task<IActionResult> ServiceStatus()
        {
            var services = new[]
            {
                new { name = "ML API",       url = "https://ariadaikalam-swat-ml-api.hf.space/health" },
                new { name = "Ingest",       url = "https://ariadaikalam-swat-ingest.hf.space/health" },
                new { name = "Plant Sender", url = "https://ariadaikalam-swat-plant-sender.hf.space/health" },
                new { name = "RAG API",      url = "https://swat-rag-api.onrender.com/health" }
            };

            var tasks = services.Select(async svc =>
            {
                try
                {
                    // Use browser-like headers so the health check is not blocked
                    // by Cloudflare (HF) or Render's bot-detection layer
                    var req = new HttpRequestMessage(HttpMethod.Get, svc.url);
                    req.Headers.TryAddWithoutValidation("User-Agent",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
                        "AppleWebKit/537.36 (KHTML, like Gecko) " +
                        "Chrome/124.0.0.0 Safari/537.36");
                    req.Headers.TryAddWithoutValidation("Accept", "application/json, text/plain, */*");
                    req.Headers.TryAddWithoutValidation("Accept-Language", "en-US,en;q=0.9");
                    req.Headers.TryAddWithoutValidation("Accept-Encoding", "gzip, deflate, br");
                    req.Headers.TryAddWithoutValidation("Sec-Fetch-Dest", "empty");
                    req.Headers.TryAddWithoutValidation("Sec-Fetch-Mode", "cors");
                    req.Headers.TryAddWithoutValidation("Sec-Fetch-Site", "same-origin");
                    req.Headers.TryAddWithoutValidation("Cache-Control", "no-cache");

                    var resp = await _statusClient.SendAsync(req, HttpCompletionOption.ResponseHeadersRead);
                    return new { svc.name, ok = resp.IsSuccessStatusCode };
                }
                catch
                {
                    return new { svc.name, ok = false };
                }
            });

            var results = await Task.WhenAll(tasks);
            var allReady = results.All(r => r.ok);

            return Json(new { allReady, services = results });
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
                return StatusCode(500, new { error = "An error occurred processing your request." });
            }
        }
    }
}
