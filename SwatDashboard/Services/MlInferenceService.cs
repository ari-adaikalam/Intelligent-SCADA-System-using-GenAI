using SwatDashboard.Models;
using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace SwatDashboard.Services
{
    public class MlInferenceService
    {
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly ILogger<MlInferenceService> _logger;
        private readonly string _mlApiUrl;

        private static readonly JsonSerializerOptions JsonOpts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        public MlInferenceService(
            IHttpClientFactory httpClientFactory,
            IConfiguration configuration,
            ILogger<MlInferenceService> logger)
        {
            _httpClientFactory = httpClientFactory;
            _logger = logger;
            _mlApiUrl = configuration["SwatSettings:PythonMlApiUrl"] ?? "http://127.0.0.1:5000";
        }

        public async Task<MlInferenceResult?> RunInferenceAsync(RawPlantData data)
        {
            var sw = Stopwatch.StartNew();

            try
            {
                var client = _httpClientFactory.CreateClient("PythonML");

                // Make sure the client points at the configured base URL.
                // (If you already set BaseAddress in Program.cs for "PythonML", this is harmless.)
                if (client.BaseAddress == null)
                    client.BaseAddress = new Uri(_mlApiUrl);

                // Prepare the request payload
                var payloadObj = new
                {
                    id = data.Id,
                    ts = data.Ts.ToString("o"),
                    plant_id = data.PlantId,
                    payload = data.Payload
                };

                var tSerStart = sw.ElapsedMilliseconds;
                var json = JsonSerializer.Serialize(payloadObj);
                var tSerEnd = sw.ElapsedMilliseconds;

                using var jsonContent = new StringContent(json, Encoding.UTF8, "application/json");

                var tPostStart = sw.ElapsedMilliseconds;
                using var response = await client.PostAsync("/api/inference", jsonContent);
                var tPostEnd = sw.ElapsedMilliseconds;

                if (!response.IsSuccessStatusCode)
                {
                    _logger.LogWarning("ML API returned status code: {StatusCode}", response.StatusCode);

                    

                    return new MlInferenceResult
                    {
                        Success = false,
                        Error = $"ML API returned status code: {response.StatusCode}"
                    };
                }

                var tReadStart = sw.ElapsedMilliseconds;
                var responseContent = await response.Content.ReadAsStringAsync();
                var tReadEnd = sw.ElapsedMilliseconds;

                var tDeserStart = sw.ElapsedMilliseconds;
                var result = JsonSerializer.Deserialize<MlInferenceResult>(responseContent, JsonOpts);
                var tDeserEnd = sw.ElapsedMilliseconds;

                
                return result ?? new MlInferenceResult
                {
                    Success = false,
                    Error = "Failed to deserialize ML API response"
                };
            }
            catch (HttpRequestException ex)
            {
                _logger.LogError(ex, "HTTP error calling ML API (DbId={DbId})", data.Id);

                _logger.LogInformation(
                    "ML timings DbId={DbId}: total={Total}ms (failed HttpRequestException)",
                    data.Id,
                    sw.ElapsedMilliseconds
                );

                return new MlInferenceResult
                {
                    Success = false,
                    Error = "ML API is not available. Make sure Python service is running."
                };
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error running ML inference (DbId={DbId})", data.Id);

                _logger.LogInformation(
                    "ML timings DbId={DbId}: total={Total}ms (failed Exception)",
                    data.Id,
                    sw.ElapsedMilliseconds
                );

                return new MlInferenceResult
                {
                    Success = false,
                    Error = $"ML inference error: {ex.Message}"
                };
            }
        }

        public async Task<MlInferenceResult?> RunInferenceBatchAsync(List<RawPlantData> dataList)
        {
            var sw = Stopwatch.StartNew();

            try
            {
                var client = _httpClientFactory.CreateClient("PythonML");

                if (client.BaseAddress == null)
                    client.BaseAddress = new Uri(_mlApiUrl);

                var payloadObj = dataList.Select(d => new
                {
                    id = d.Id,
                    ts = d.Ts.ToString("o"),
                    plant_id = d.PlantId,
                    payload = d.Payload
                }).ToList();

                var tSerStart = sw.ElapsedMilliseconds;
                var json = JsonSerializer.Serialize(payloadObj);
                var tSerEnd = sw.ElapsedMilliseconds;

                using var jsonContent = new StringContent(json, Encoding.UTF8, "application/json");

                var tPostStart = sw.ElapsedMilliseconds;
                using var response = await client.PostAsync("/api/inference/batch", jsonContent);
                var tPostEnd = sw.ElapsedMilliseconds;

                if (!response.IsSuccessStatusCode)
                {
                    _logger.LogWarning("Batch ML API returned status code: {StatusCode}", response.StatusCode);

                    _logger.LogInformation(
                        "Batch ML timings: total={Total}ms serialize={Ser}ms post={Post}ms",
                        sw.ElapsedMilliseconds,
                        (tSerEnd - tSerStart),
                        (tPostEnd - tPostStart)
                    );

                    return new MlInferenceResult
                    {
                        Success = false,
                        Error = $"ML API returned status code: {response.StatusCode}"
                    };
                }

                var tReadStart = sw.ElapsedMilliseconds;
                var responseContent = await response.Content.ReadAsStringAsync();
                var tReadEnd = sw.ElapsedMilliseconds;

                var tDeserStart = sw.ElapsedMilliseconds;
                var result = JsonSerializer.Deserialize<MlInferenceResult>(responseContent, JsonOpts);
                var tDeserEnd = sw.ElapsedMilliseconds;

                _logger.LogInformation(
                    "Batch ML timings: total={Total}ms serialize={Ser}ms post={Post}ms read={Read}ms deserialize={Deser}ms items={Count}",
                    sw.ElapsedMilliseconds,
                    (tSerEnd - tSerStart),
                    (tPostEnd - tPostStart),
                    (tReadEnd - tReadStart),
                    (tDeserEnd - tDeserStart),
                    dataList.Count
                );

                return result ?? new MlInferenceResult
                {
                    Success = false,
                    Error = "Failed to deserialize batch ML API response"
                };
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error running batch ML inference");

                _logger.LogInformation(
                    "Batch ML timings: total={Total}ms (failed Exception)",
                    sw.ElapsedMilliseconds
                );

                return new MlInferenceResult
                {
                    Success = false,
                    Error = $"Batch ML inference error: {ex.Message}"
                };
            }
        }
    }
}
