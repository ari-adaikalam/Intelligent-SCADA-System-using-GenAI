using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SwatDashboard.Hubs;
using SwatDashboard.Models;

namespace SwatDashboard.Services
{
    public class LiveDataBackgroundService : BackgroundService
    {
        private readonly IServiceProvider _serviceProvider;
        private readonly ILogger<LiveDataBackgroundService> _logger;
        private readonly int _refreshIntervalMs;
        private readonly int _offlineThresholdSeconds;

        private int? _lastSeenDbId;
        private MlInferenceResult? _lastMlResult;

        // Online/offline transition tracking
        private bool _wasOnline = false;

        // In-memory cache for sparklines (last 60 rows)
        private readonly List<RawPlantData> _recentCache = new();
        private readonly object _cacheLock = new();
        private int? _lastCachedId;

        private const int RECENT_CACHE_SIZE = 60;

        // One shared HttpClient
        private static readonly HttpClient _http = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(2)
        };

        public LiveDataBackgroundService(
            IServiceProvider serviceProvider,
            IConfiguration configuration,
            ILogger<LiveDataBackgroundService> logger)
        {
            _serviceProvider = serviceProvider;
            _logger = logger;
            _refreshIntervalMs = configuration.GetValue<int>("SwatSettings:RefreshIntervalMs", 1000);
            _offlineThresholdSeconds = configuration.GetValue<int>("SwatSettings:OfflineThresholdSeconds", 5);
        }

        private async Task ResetMlBufferAsync(CancellationToken ct)
        {
            try
            {
                using var req = new HttpRequestMessage(HttpMethod.Post, "http://127.0.0.1:5000/api/buffer/reset");
                using var resp = await _http.SendAsync(req, ct);

                if (resp.IsSuccessStatusCode)
                    _logger.LogInformation("✅ ML buffer reset successfully.");
                else
                    _logger.LogWarning("⚠️ ML buffer reset failed: {Status}", resp.StatusCode);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "⚠️ Failed to reset ML buffer.");
            }
        }

        protected override async Task ExecuteAsync(CancellationToken stoppingToken)
        {
            _logger.LogInformation(
                "Live Data Background Service starting... RefreshIntervalMs={Ms}",
                _refreshIntervalMs
            );

            // ✅ Initialize cache ONCE at startup
            await WarmRecentCacheOnce(stoppingToken);

            while (!stoppingToken.IsCancellationRequested)
            {
                var loopStartUtc = DateTime.UtcNow;

                try
                {
                    using var scope = _serviceProvider.CreateScope();
                    var dbService = scope.ServiceProvider.GetRequiredService<DatabaseService>();
                    var hubContext = scope.ServiceProvider.GetRequiredService<IHubContext<LiveDataHub>>();

                    // 1) Get latest row
                    var t0 = DateTime.UtcNow;
                    var latestData = await dbService.GetLatestDataAsync();
                    var latestMs = (DateTime.UtcNow - t0).TotalMilliseconds;

                    if (latestData != null)
                    {
                        // 2) Determine online/offline
                        var freshnessSeconds = (int)(DateTime.Now - latestData.Ts).TotalSeconds;
                        var isOnline = freshnessSeconds <= _offlineThresholdSeconds;

                        // ✅ OFFLINE -> ONLINE transition: reset ML buffer once
                        if (!_wasOnline && isOnline)
                        {
                            _logger.LogInformation("🔄 OFFLINE → ONLINE detected. Resetting ML buffer...");

                            await ResetMlBufferAsync(stoppingToken);

                            // Clear stale ML state so UI doesn't show old alarms
                            _lastMlResult = null;
                            _lastSeenDbId = null;
                        }

                        _wasOnline = isOnline;

                        var status = new SystemStatus
                        {
                            IsOnline = isOnline,
                            FreshnessSeconds = freshnessSeconds,
                            LastUpdate = latestData.Ts,
                            StatusMessage = isOnline ? "System Online" : "System Offline"
                        };

                        // 3) Update cache only when new DB row arrives
                        if (_lastCachedId == null || latestData.Id > _lastCachedId)
                        {
                            AppendToRecentCache(latestData);
                            _lastCachedId = latestData.Id;
                        }

                        // 4) Run ML only for new row and only if online
                        bool shouldRunMl = isOnline && (_lastSeenDbId == null || latestData.Id > _lastSeenDbId);

                        if (shouldRunMl)
                        {
                            try
                            {
                                using var mlScope = _serviceProvider.CreateScope();
                                var mlSvc = mlScope.ServiceProvider.GetRequiredService<MlInferenceService>();

                                var r = await mlSvc.RunInferenceAsync(latestData);
                                if (r != null)
                                {
                                    _lastMlResult = r;
                                    _lastSeenDbId = latestData.Id;
                                }
                            }
                            catch (Exception ex)
                            {
                                _logger.LogError(ex, "ML inference failed (DbId={DbId})", latestData.Id);
                            }
                        }

                        // 5) Snapshot cache
                        List<RawPlantData> recentSnapshot;
                        lock (_cacheLock)
                        {
                            recentSnapshot = _recentCache.ToList();
                        }


                        // 7) Send update
                        var dashboardData = new LiveDashboardData
                        {
                            LatestData = latestData,
                            RecentData = recentSnapshot,
                            Status = status,
                            MlResult = _lastMlResult
                        };

                        await hubContext.Clients.All.SendAsync("ReceiveLiveUpdate", dashboardData, stoppingToken);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error in Live Data Background Service loop");
                }

               

                // Keep loop close to refresh interval
                var loopElapsedMs = (DateTime.UtcNow - loopStartUtc).TotalMilliseconds;
                if (loopElapsedMs > _refreshIntervalMs * 0.9)
                {
                    _logger.LogWarning(
                        "Loop work took {Ms:0.0}ms (refresh={Refresh}ms)",
                        loopElapsedMs, _refreshIntervalMs
                    );
                }

                var remainingDelayMs = _refreshIntervalMs - (int)loopElapsedMs;
                if (remainingDelayMs > 0)
                    await Task.Delay(remainingDelayMs, stoppingToken);
                else
                    await Task.Yield();
            }

            _logger.LogInformation("Live Data Background Service stopping...");
        }

        private async Task WarmRecentCacheOnce(CancellationToken stoppingToken)
        {
            try
            {
                using var scope = _serviceProvider.CreateScope();
                var dbService = scope.ServiceProvider.GetRequiredService<DatabaseService>();

                var t = DateTime.UtcNow;
                var warm = await dbService.GetLatestNDataAsync(RECENT_CACHE_SIZE);
                var ms = (DateTime.UtcNow - t).TotalMilliseconds;

                lock (_cacheLock)
                {
                    _recentCache.Clear();
                    _recentCache.AddRange(warm.OrderBy(d => d.Ts));
                    _lastCachedId = _recentCache.Count > 0 ? _recentCache.Max(d => d.Id) : null;
                }

                _logger.LogInformation("Recent cache warmed: {Count}/60 in {Ms:0.0}ms", warm.Count, ms);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Failed to warm recent cache");
            }
        }

        private void AppendToRecentCache(RawPlantData latest)
        {
            lock (_cacheLock)
            {
                if (_recentCache.Count > 0 && _recentCache[^1].Id == latest.Id)
                    return;

                _recentCache.Add(latest);

                if (_recentCache.Count > RECENT_CACHE_SIZE)
                {
                    int extra = _recentCache.Count - RECENT_CACHE_SIZE;
                    _recentCache.RemoveRange(0, extra);
                }
            }
        }
    }
}
