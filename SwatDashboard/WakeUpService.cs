using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace SwatDashboard.Services
{
    /// <summary>
    /// Responsibility: keep-alive pings only.
    ///
    /// Waking services from cold start is the browser's job (iframes for HF,
    /// fetch+retry for Render). Server-to-server requests — even with browser
    /// headers — are still seen as API traffic at the CDN/edge level and may
    /// not trigger a cold wake on HF Spaces or Render.
    ///
    /// This service runs every 4 minutes to keep already-awake services warm
    /// so they never go back to sleep during an active session.
    /// </summary>
    public class WakeUpService : IHostedService
    {
        private readonly ILogger<WakeUpService> _logger;
        private Timer? _timer;

        private static readonly (string Name, string HealthUrl)[] AllServices =
        {
            ("ML API",       "https://ariadaikalam-swat-ml-api.hf.space/health"),
            ("Ingest",       "https://ariadaikalam-swat-ingest.hf.space/health"),
            ("Plant Sender", "https://ariadaikalam-swat-plant-sender.hf.space/health"),
            ("RAG API",      "https://swat-rag-api.onrender.com/health"),
        };

        // Single shared client — keep-alive pings are lightweight, 30s is fine
        private static readonly HttpClient _client = new HttpClient(
            new SocketsHttpHandler
            {
                AutomaticDecompression = DecompressionMethods.GZip
                                       | DecompressionMethods.Deflate
                                       | DecompressionMethods.Brotli,
                AllowAutoRedirect = true,
                PooledConnectionLifetime = TimeSpan.FromMinutes(10),
            })
        {
            Timeout = TimeSpan.FromSeconds(30)
        };

        public WakeUpService(ILogger<WakeUpService> logger)
        {
            _logger = logger;
        }

        public Task StartAsync(CancellationToken cancellationToken)
        {
            _logger.LogInformation(
                "[WakeUpService] Started. Keep-alive pings every 4 minutes. " +
                "Cold-start waking is handled by the browser (iframes / fetch).");

            // No immediate ping on startup — browser handles cold wakes.
            // First keep-alive tick fires after 4 minutes.
            _timer = new Timer(
                _ => _ = PingAll(CancellationToken.None),
                null,
                TimeSpan.FromMinutes(4),
                TimeSpan.FromMinutes(4));

            return Task.CompletedTask;
        }

        private async Task PingAll(CancellationToken ct)
        {
            _logger.LogInformation("[WakeUpService] Sending keep-alive pings...");

            var tasks = AllServices.Select(async svc =>
            {
                try
                {
                    var req = new HttpRequestMessage(HttpMethod.Get, svc.HealthUrl);
                    // Browser-like headers to avoid Cloudflare rate-limiting keep-alive checks
                    req.Headers.TryAddWithoutValidation("User-Agent",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
                        "AppleWebKit/537.36 (KHTML, like Gecko) " +
                        "Chrome/124.0.0.0 Safari/537.36");
                    req.Headers.TryAddWithoutValidation("Accept", "application/json, text/plain, */*");
                    req.Headers.TryAddWithoutValidation("Accept-Language", "en-US,en;q=0.9");
                    req.Headers.TryAddWithoutValidation("Cache-Control", "no-cache");

                    var resp = await _client.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
                    _logger.LogInformation("[WakeUpService] {Name} → HTTP {Status}", svc.Name, (int)resp.StatusCode);
                }
                catch (Exception ex)
                {
                    _logger.LogWarning("[WakeUpService] {Name} keep-alive failed: {Message}", svc.Name, ex.Message);
                }
            });

            await Task.WhenAll(tasks);
        }

        public Task StopAsync(CancellationToken cancellationToken)
        {
            _timer?.Dispose();
            return Task.CompletedTask;
        }
    }
}
