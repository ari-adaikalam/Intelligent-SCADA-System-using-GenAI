using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using SwatDashboard.Models;

namespace SwatDashboard.Services
{
    /// <summary>
    /// Service for integrating with Python RAG API
    /// Handles communication, error recovery, and retry logic
    /// </summary>
    public class ChatService
    {
        private readonly IHttpClientFactory _httpClientFactory;
        private readonly IConfiguration _configuration;
        private readonly ILogger<ChatService> _logger;
        private readonly string _ragApiUrl;
        private readonly string _mlApiUrl;
        private readonly DatabaseConnectionInfo _dbConnectionInfo;
        
        // JSON serialization options
        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            WriteIndented = false
        };
        
        public ChatService(
            IHttpClientFactory httpClientFactory,
            IConfiguration configuration,
            ILogger<ChatService> logger)
        {
            _httpClientFactory = httpClientFactory;
            _configuration = configuration;
            _logger = logger;
            
            // Get RAG API URL from configuration
            _ragApiUrl = configuration["SwatSettings:PythonRagApiUrl"] 
                ?? "http://127.0.0.1:5001";
            
            // Get ML API URL from configuration
            _mlApiUrl = configuration["SwatSettings:PythonMlApiUrl"] 
                ?? "http://127.0.0.1:5000";
            
            // Build database connection info
            var connectionString = configuration.GetConnectionString("SwatDatabase") 
                ?? throw new InvalidOperationException("Database connection string not found");
            
            _dbConnectionInfo = ParseConnectionString(connectionString);
            
            _logger.LogInformation(
                "ChatService initialized - RAG API: {RagUrl}, ML API: {MlUrl}", 
                _ragApiUrl, _mlApiUrl
            );
        }
        
        // ====================================================================
        // PUBLIC METHODS
        // ====================================================================
        
        /// <summary>
        /// Process a chat message with full error handling and retry logic
        /// </summary>
        public async Task<ChatResponse> ProcessMessageAsync(
            string userMessage,
            List<ChatMessage> conversationHistory,
            RawPlantData? realtimeData = null)
        {
            var stopwatch = Stopwatch.StartNew();
            if (string.IsNullOrWhiteSpace(userMessage))
            {
                _logger.LogWarning("Received empty message");
                return new ChatResponse
                {
                    Success = false,
                    Text = "Please enter a message",
                    Error = "Message cannot be empty"
                };
            }
            try
            {
                _logger.LogInformation(
                    "Processing chat message: {Message} (Session has {HistoryCount} messages)",
                    userMessage.Substring(0, Math.Min(50, userMessage.Length)) + "...",
                    conversationHistory.Count
                );
                
                // Build request payload
                var ragRequest = BuildRagRequest(
                    userMessage,
                    conversationHistory,
                    realtimeData
                );
                
                // Call RAG API with retry logic
                var ragResponse = await CallRagApiWithRetryAsync(ragRequest);
                
                // Convert RAG response to ChatResponse
                var chatResponse = ConvertToChatResponse(ragResponse, stopwatch.ElapsedMilliseconds);
                
                _logger.LogInformation(
                    "Chat message processed successfully in {ElapsedMs}ms",
                    stopwatch.ElapsedMilliseconds
                );
                
                return chatResponse;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error processing chat message");
                
                return new ChatResponse
                {
                    Success = false,
                    Text = GetUserFriendlyErrorMessage(ex),
                    Error = ex.Message,
                    Metadata = new ChatMetadata
                    {
                        ProcessingTimeMs = stopwatch.ElapsedMilliseconds
                    }
                };
            }
        }
        
        /// <summary>
        /// Check if RAG API is available
        /// </summary>
        public async Task<ChatHealthStatus> CheckHealthAsync()
        {
            var status = new ChatHealthStatus
            {
                CheckedAt = DateTime.UtcNow
            };
            
            try
            {
                // Check RAG API
                var client = _httpClientFactory.CreateClient();
                client.Timeout = TimeSpan.FromSeconds(5);
                
                var response = await client.GetAsync($"{_ragApiUrl}/health");
                status.RagApiAvailable = response.IsSuccessStatusCode;
                
                // Check ML API
                var mlResponse = await client.GetAsync($"{_mlApiUrl}/health");
                status.MlApiAvailable = mlResponse.IsSuccessStatusCode;
                
                // Database check would require DatabaseService injection
                status.DatabaseAvailable = true; // Assume true for now
                
                status.Status = status.RagApiAvailable && status.MlApiAvailable 
                    ? "ok" 
                    : "degraded";
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Health check failed");
                status.Status = "offline";
                status.RagApiAvailable = false;
                status.MlApiAvailable = false;
            }
            
            return status;
        }

        // ====================================================================
        // PRIVATE METHODS - REQUEST BUILDING
        // ====================================================================

        private RagApiRequest BuildRagRequest(
    string message,
    List<ChatMessage> conversationHistory,
    RawPlantData? realtimeData)
        {
            _logger.LogInformation($"Building RAG request - Message: '{message}' (Length: {message?.Length ?? 0})");

            // Convert conversation history
            var historyForRag = conversationHistory.Select(m => new Dictionary<string, object>
            {
                ["role"] = m.Role,
                ["content"] = m.Content
            }).ToList();

            // Build realtime data payload
            object? realtimePayload = null;
            if (realtimeData != null && realtimeData.Payload != null)
            {
                realtimePayload = new Dictionary<string, object>
                {
                    ["timestamp"] = realtimeData.Ts,
                    ["plant_id"] = realtimeData.PlantId,
                    ["payload"] = realtimeData.Payload  // This is already a Dictionary
                };
            }

            var request = new RagApiRequest
            {
                SessionId = Guid.NewGuid().ToString(),
                Message = message,  // Ensure message is passed correctly
                ConversationHistory = historyForRag,
                RealtimeData = realtimePayload,
                DatabaseConnection = _dbConnectionInfo
            };

            _logger.LogInformation($"RAG Request built - SessionId: {request.SessionId}, Message: '{request.Message}'");

            return request;
        }

        // ====================================================================
        // PRIVATE METHODS - RAG API COMMUNICATION
        // ====================================================================

        private async Task<RagApiResponse> CallRagApiWithRetryAsync(
            RagApiRequest request,
            int maxRetries = 3)
        {
            Exception? lastException = null;
            
            for (int attempt = 1; attempt <= maxRetries; attempt++)
            {
                try
                {
                    var requestJson = JsonSerializer.Serialize(request);
                    _logger.LogInformation($"Sending to RAG API: {requestJson}");
                    _logger.LogDebug("RAG API call attempt {Attempt}/{MaxRetries}", attempt, maxRetries);
                    
                    return await CallRagApiAsync(request);
                }
                catch (HttpRequestException ex) when (attempt < maxRetries)
                {
                    lastException = ex;
                    var delay = TimeSpan.FromMilliseconds(Math.Pow(2, attempt) * 500); // Exponential backoff
                    
                    _logger.LogWarning(
                        ex,
                        "RAG API call failed (attempt {Attempt}/{MaxRetries}), retrying in {DelayMs}ms",
                        attempt, maxRetries, delay.TotalMilliseconds
                    );
                    
                    await Task.Delay(delay);
                }
                
            }
            
            // All retries failed
            throw new InvalidOperationException(
                $"RAG API call failed after {maxRetries} attempts",
                lastException
            );
        }
        
        private async Task<RagApiResponse> CallRagApiAsync(RagApiRequest request)
        {
            var client = _httpClientFactory.CreateClient();
            client.Timeout = TimeSpan.FromSeconds(120); // Generous timeout for LLM inference
            
            var jsonContent = new StringContent(
                JsonSerializer.Serialize(request, JsonOptions),
                Encoding.UTF8,
                "application/json"
            );
            
            _logger.LogDebug("Calling RAG API: POST {Url}/api/chat", _ragApiUrl);
            
            var response = await client.PostAsync(
                $"{_ragApiUrl}/api/chat",
                jsonContent
            );
            
            if (!response.IsSuccessStatusCode)
            {
                var errorContent = await response.Content.ReadAsStringAsync();
                _logger.LogError(
                    "RAG API returned error status {StatusCode}: {Error}",
                    response.StatusCode, errorContent
                );
                
                throw new HttpRequestException(
                    $"RAG API error: {response.StatusCode}"
                );
            }
            
            var responseJson = await response.Content.ReadAsStringAsync();
            
            var ragResponse = JsonSerializer.Deserialize<RagApiResponse>(responseJson, JsonOptions)
                ?? throw new InvalidOperationException("Failed to deserialize RAG API response");
            
            if (!ragResponse.Success)
            {
                throw new InvalidOperationException(
                    $"RAG API returned failure: {ragResponse.Error ?? "Unknown error"}"
                );
            }
            
            return ragResponse;
        }
        
        // ====================================================================
        // PRIVATE METHODS - RESPONSE CONVERSION
        // ====================================================================
        
        private ChatResponse ConvertToChatResponse(RagApiResponse ragResponse, long processingTimeMs)
        {
            var chatResponse = new ChatResponse
            {
                Success = ragResponse.Success,
                Text = ragResponse.Text,
                ChartConfig = ragResponse.ChartConfig,
                DownloadLinks = ragResponse.DownloadLinks,
                Error = ragResponse.Error,
                Metadata = new ChatMetadata
                {
                    SqlQuery = ragResponse.SqlQuery,
                    RowCount = ragResponse.RowCount,
                    ProcessingTimeMs = processingTimeMs
                }
            };
            
            // Convert ML insights if present
            if (ragResponse.MlInsights != null)
            {
                chatResponse.MlInsights = new MlInsights
                {
                    IsAnomaly = ragResponse.MlInsights.IsAnomaly,
                    State = ragResponse.MlInsights.State,
                    FaultyComponent = ragResponse.MlInsights.FaultyComponent,
                    Confidence = ragResponse.MlInsights.Confidence,
                    Recommendations = ragResponse.MlInsights.Recommendations
                };
            }
            
            return chatResponse;
        }
        
        // ====================================================================
        // PRIVATE METHODS - ERROR HANDLING
        // ====================================================================
        
        private string GetUserFriendlyErrorMessage(Exception ex)
        {
            return ex switch
            {
                HttpRequestException => 
                    "I'm having trouble connecting to the AI service. Please check that the RAG service is running on port 5001.",
                
                TaskCanceledException => 
                    "The request took too long to process. Please try a simpler query or try again later.",
                
                InvalidOperationException when ex.Message.Contains("RAG API") => 
                    "The AI service encountered an error processing your request. Please try rephrasing your question.",
                
                JsonException => 
                    "I received an unexpected response format. Please try again.",
                
                _ => 
                    "I encountered an unexpected error. Please try again or contact support if the issue persists."
            };
        }
        
        // ====================================================================
        // PRIVATE METHODS - UTILITY
        // ====================================================================
        
        private DatabaseConnectionInfo ParseConnectionString(string connectionString)
        {
            // Simple parser for SQL Server connection string
            var parts = connectionString.Split(';')
                .Select(p => p.Trim())
                .Where(p => !string.IsNullOrWhiteSpace(p))
                .Select(p =>
                {
                    var kvp = p.Split('=', 2);
                    return new { Key = kvp[0].Trim().ToLower(), Value = kvp.Length > 1 ? kvp[1].Trim() : "" };
                })
                .ToDictionary(x => x.Key, x => x.Value);
            
            return new DatabaseConnectionInfo
            {
                Server = parts.GetValueOrDefault("server") ?? parts.GetValueOrDefault("data source") ?? "localhost",
                Database = parts.GetValueOrDefault("database") ?? parts.GetValueOrDefault("initial catalog") ?? "swat",
                Username = parts.GetValueOrDefault("user id") ?? parts.GetValueOrDefault("uid") ?? "swat_ingest",
                Password = parts.GetValueOrDefault("password") ?? parts.GetValueOrDefault("pwd") ?? ""
            };
        }
    }
}
