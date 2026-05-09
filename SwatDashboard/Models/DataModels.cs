using System.Text.Json;

namespace SwatDashboard.Models
{
    public class RawPlantData
    {
        public int Id { get; set; }
        public DateTime Ts { get; set; }
        public string PlantId { get; set; } = string.Empty;
        public string PayloadJson { get; set; } = string.Empty;
        
        private Dictionary<string, object>? _payload;
        
        public Dictionary<string, object> Payload
        {
            get
            {
                if (_payload == null && !string.IsNullOrEmpty(PayloadJson))
                {
                    try
                    {
                        _payload = JsonSerializer.Deserialize<Dictionary<string, object>>(PayloadJson) 
                                   ?? new Dictionary<string, object>();
                    }
                    catch
                    {
                        _payload = new Dictionary<string, object>();
                    }
                }
                return _payload ?? new Dictionary<string, object>();
            }
        }
    }

    public class LiveDashboardData
    {
        public RawPlantData? LatestData { get; set; }
        public List<RawPlantData> RecentData { get; set; } = new();
        public SystemStatus Status { get; set; } = new();
        public MlInferenceResult? MlResult { get; set; }
    }

    public class SystemStatus
    {
        public bool IsOnline { get; set; }
        public int FreshnessSeconds { get; set; }
        public DateTime? LastUpdate { get; set; }
        public string StatusMessage { get; set; } = string.Empty;
    }

    public class MlInferenceResult
    {
        public bool Success { get; set; }
        public string? Error { get; set; }
        
        public Stage1Result Stage1 { get; set; } = new();
        public Stage2Result Stage2 { get; set; } = new();
        public Stage3Result Stage3 { get; set; } = new();
        
        public Dictionary<string, ComponentHealth> ComponentHealth { get; set; } = new();
        public List<string> RecommendedActions { get; set; } = new();
        public Dictionary<string, bool> AlertsSent { get; set; } = new();
        public BufferStatus BufferStatus { get; set; } = new();
    }

    public class Stage1Result
    {
        public bool IsAnomaly { get; set; }
        public double Confidence { get; set; }
    }

    public class Stage2Result
    {
        public string State { get; set; } = "NORMAL";
        public double Confidence { get; set; }
    }

    public class Stage3Result
    {
        public string? Component { get; set; }
        public double Confidence { get; set; }
        public List<ComponentPrediction> Top3 { get; set; } = new();
    }

    public class ComponentPrediction
    {
        public string Component { get; set; } = string.Empty;
        public double Confidence { get; set; }
    }

    public class ComponentHealth
    {
        public string Status { get; set; } = "NORMAL";
        public string Icon { get; set; } = "✅";
        public string Message { get; set; } = string.Empty;
    }

    public class BufferStatus
    {
        public int Size { get; set; }
        public bool Ready { get; set; }
        public bool UsingBuffer { get; set; }
    }

    public class AnalyticsSummary
    {
        public int TotalSamples { get; set; }
        public double OnlinePercentage { get; set; }
        public double DowntimePercentage { get; set; }
        public double OfflineSeconds { get; set; }
        public double DowntimeSeconds { get; set; }
        public double SamplingIntervalSeconds { get; set; }
        public DateTime StartTime { get; set; }
        public DateTime EndTime { get; set; }
    }

    public class SignalStats
    {
        public string SignalName { get; set; } = string.Empty;
        public double Average { get; set; }
        public double Min { get; set; }
        public double Max { get; set; }
        public double StdDev { get; set; }
    }

    public class ActuatorStats
    {
        public string ActuatorName { get; set; } = string.Empty;
        public double OnPercentage { get; set; }
        public int SwitchCount { get; set; }
    }
}
