using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using SwatDashboard.Models;
using SwatDashboard.Services;

namespace SwatDashboard.Controllers
{
    /// <summary>
    /// API controller for AI chat functionality
    /// Handles chat messages, session management, and health checks
    /// </summary>
    [Route("api/[controller]")]
    [ApiController]
    public class ChatController : ControllerBase
    {
        private readonly ChatService _chatService;
        private readonly DatabaseService _databaseService;
        private readonly ILogger<ChatController> _logger;

        // In-memory session storage (thread-safe)
        // Key: SessionId, Value: ChatSession
        private static readonly ConcurrentDictionary<string, ChatSession> _sessions = new();

        // Request deduplication cache (prevent duplicate processing)
        private static readonly ConcurrentDictionary<string, DateTime> _recentRequests = new();
        private static readonly TimeSpan RequestDeduplicationWindow = TimeSpan.FromSeconds(5);

        // Cleanup timer
        private static DateTime _lastCleanup = DateTime.UtcNow;
        private static readonly TimeSpan CleanupInterval = TimeSpan.FromMinutes(30);

        public ChatController(
            ChatService chatService,
            DatabaseService databaseService,
            ILogger<ChatController> logger)
        {
            _chatService = chatService;
            _databaseService = databaseService;
            _logger = logger;
        }

        /// <summary>
        /// Check if this is a duplicate request
        /// </summary>
        private bool IsDuplicateRequest(string sessionId, string message)
        {
            var requestKey = $"{sessionId}:{message.GetHashCode()}";
            var now = DateTime.UtcNow;

            // Check if we've seen this exact request recently
            if (_recentRequests.TryGetValue(requestKey, out var lastSeen))
            {
                if ((now - lastSeen) < RequestDeduplicationWindow)
                {
                    _logger.LogWarning(
                        "Duplicate request detected for session {SessionId} within {Seconds}s window",
                        sessionId,
                        (now - lastSeen).TotalSeconds
                    );
                    return true;
                }
            }

            // Add/update this request
            _recentRequests[requestKey] = now;

            // Cleanup old entries (keep last 100 only)
            if (_recentRequests.Count > 100)
            {
                var oldEntries = _recentRequests
                    .Where(kvp => (now - kvp.Value) > RequestDeduplicationWindow)
                    .Select(kvp => kvp.Key)
                    .ToList();

                foreach (var key in oldEntries)
                {
                    _recentRequests.TryRemove(key, out _);
                }
            }

            return false;
        }

        // ====================================================================
        // CHAT ENDPOINTS
        // ====================================================================

        /// <summary>
        /// Process a chat message
        /// POST /api/chat/message
        /// </summary>
        [HttpPost("message")]
        public async Task<IActionResult> SendMessage([FromBody] ChatRequest request)
        {
            try
            {
                // Validate request
                if (string.IsNullOrWhiteSpace(request.SessionId))
                {
                    return BadRequest(new { error = "SessionId is required" });
                }

                if (string.IsNullOrWhiteSpace(request.Message))
                {
                    return BadRequest(new { error = "Message cannot be empty" });
                }

                if (request.Message.Length > 2000)
                {
                    return BadRequest(new { error = "Message too long (max 2000 characters)" });
                }

                // Check for duplicate requests
                if (IsDuplicateRequest(request.SessionId, request.Message))
                {
                    _logger.LogInformation(
                        "Ignoring duplicate request from session {SessionId}",
                        request.SessionId
                    );

                    return Ok(new ChatResponse
                    {
                        Success = true,
                        Text = "Processing your previous request...",
                        Error = null
                    });
                }

                _logger.LogInformation(
                    "Received chat message from session {SessionId}: {MessagePreview}",
                    request.SessionId,
                    request.Message.Substring(0, Math.Min(50, request.Message.Length))
                );

                // Get or create session
                var session = _sessions.GetOrAdd(request.SessionId, _ => new ChatSession());

                // Periodic cleanup of expired sessions
                CleanupExpiredSessionsIfNeeded();

                // Get real-time data if requested
                RawPlantData? realtimeData = null;
                if (request.IncludeRealtime)
                {
                    _logger.LogDebug("Fetching real-time data for session {SessionId}", request.SessionId);
                    realtimeData = await _databaseService.GetLatestDataAsync();

                    if (realtimeData == null)
                    {
                        _logger.LogWarning("No real-time data available");
                    }
                }

                // Get conversation history for context
                var conversationHistory = session.GetRecentHistory(maxMessages: 10);

                // Process message through ChatService
                var response = await _chatService.ProcessMessageAsync(
                    request.Message,
                    conversationHistory,
                    realtimeData
                );

                // Store in session history if successful
                if (response.Success)
                {
                    session.AddMessage(request.Message, response.Text);

                    _logger.LogInformation(
                        "Chat message processed successfully for session {SessionId}. " +
                        "Session now has {MessageCount} messages",
                        request.SessionId,
                        session.ConversationHistory.Count
                    );
                }
                else
                {
                    _logger.LogWarning(
                        "Chat message processing failed for session {SessionId}: {Error}",
                        request.SessionId,
                        response.Error
                    );
                }

                return Ok(response);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error in SendMessage endpoint");

                return StatusCode(500, new ChatResponse
                {
                    Success = false,
                    Text = "An unexpected error occurred. Please try again.",
                    Error = ex.Message
                });
            }
        }

        /// <summary>
        /// Get conversation history for a session
        /// GET /api/chat/history?sessionId={sessionId}
        /// </summary>
        [HttpGet("history")]
        public IActionResult GetHistory([FromQuery] string sessionId)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(sessionId))
                {
                    return BadRequest(new { error = "SessionId is required" });
                }

                if (_sessions.TryGetValue(sessionId, out var session))
                {
                    return Ok(new
                    {
                        sessionId,
                        messageCount = session.ConversationHistory.Count,
                        createdAt = session.CreatedAt,
                        lastActivity = session.LastActivity,
                        messages = session.ConversationHistory.Select(m => new
                        {
                            role = m.Role,
                            content = m.Content,
                            timestamp = m.Timestamp
                        })
                    });
                }

                // Session not found - return empty history
                return Ok(new
                {
                    sessionId,
                    messageCount = 0,
                    messages = Array.Empty<object>()
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting chat history for session {SessionId}", sessionId);
                return StatusCode(500, new { error = "Failed to retrieve chat history" });
            }
        }

        /// <summary>
        /// Clear a chat session
        /// POST /api/chat/clear
        /// </summary>
        [HttpPost("clear")]
        public IActionResult ClearSession([FromBody] ClearSessionRequest request)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(request.SessionId))
                {
                    return BadRequest(new { error = "SessionId is required" });
                }

                if (_sessions.TryRemove(request.SessionId, out var session))
                {
                    _logger.LogInformation(
                        "Cleared session {SessionId} with {MessageCount} messages",
                        request.SessionId,
                        session.ConversationHistory.Count
                    );

                    return Ok(new
                    {
                        success = true,
                        message = "Session cleared successfully",
                        messagesCleared = session.ConversationHistory.Count
                    });
                }

                // Session didn't exist, but that's fine
                return Ok(new
                {
                    success = true,
                    message = "Session not found or already cleared",
                    messagesCleared = 0
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error clearing session {SessionId}", request.SessionId);
                return StatusCode(500, new { error = "Failed to clear session" });
            }
        }

        // ====================================================================
        // HEALTH & STATUS ENDPOINTS
        // ====================================================================

        /// <summary>
        /// Check chat service health
        /// GET /api/chat/status
        /// </summary>
        [HttpGet("status")]
        public async Task<IActionResult> GetStatus()
        {
            try
            {
                var health = await _chatService.CheckHealthAsync();
                health.ActiveSessions = _sessions.Count;

                var statusCode = health.Status switch
                {
                    "ok" => 200,
                    "degraded" => 200, // Still return 200 but with degraded status
                    _ => 503
                };

                return StatusCode(statusCode, health);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error checking chat service status");

                return StatusCode(503, new ChatHealthStatus
                {
                    Status = "error",
                    RagApiAvailable = false,
                    MlApiAvailable = false,
                    DatabaseAvailable = false,
                    ActiveSessions = _sessions.Count,
                    CheckedAt = DateTime.UtcNow
                });
            }
        }

        /// <summary>
        /// Get session statistics
        /// GET /api/chat/stats
        /// </summary>
        [HttpGet("stats")]
        public IActionResult GetStatistics()
        {
            try
            {
                var stats = new
                {
                    totalSessions = _sessions.Count,
                    activeSessions = _sessions.Count(s => !s.Value.IsExpired),
                    expiredSessions = _sessions.Count(s => s.Value.IsExpired),
                    totalMessages = _sessions.Values.Sum(s => s.ConversationHistory.Count),
                    oldestSession = _sessions.Values.Any()
                        ? _sessions.Values.Min(s => s.CreatedAt)
                        : (DateTime?)null,
                    newestSession = _sessions.Values.Any()
                        ? _sessions.Values.Max(s => s.CreatedAt)
                        : (DateTime?)null,
                    lastCleanup = _lastCleanup
                };

                return Ok(stats);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error getting chat statistics");
                return StatusCode(500, new { error = "Failed to retrieve statistics" });
            }
        }

        // ====================================================================
        // SESSION MANAGEMENT (INTERNAL)
        // ====================================================================

        /// <summary>
        /// Clean up expired sessions periodically
        /// </summary>
        private void CleanupExpiredSessionsIfNeeded()
        {
            // Only run cleanup every 30 minutes
            if ((DateTime.UtcNow - _lastCleanup) < CleanupInterval)
            {
                return;
            }

            try
            {
                var expiredSessions = _sessions
                    .Where(kvp => kvp.Value.IsExpired)
                    .Select(kvp => kvp.Key)
                    .ToList();

                if (expiredSessions.Any())
                {
                    foreach (var sessionId in expiredSessions)
                    {
                        if (_sessions.TryRemove(sessionId, out var session))
                        {
                            _logger.LogInformation(
                                "Cleaned up expired session {SessionId} " +
                                "(inactive for {Hours:F1} hours, {MessageCount} messages)",
                                sessionId,
                                (DateTime.UtcNow - session.LastActivity).TotalHours,
                                session.ConversationHistory.Count
                            );
                        }
                    }

                    _logger.LogInformation(
                        "Session cleanup completed: removed {Count} expired sessions",
                        expiredSessions.Count
                    );
                }

                _lastCleanup = DateTime.UtcNow;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error during session cleanup");
            }
        }

        /// <summary>
        /// Force cleanup all expired sessions (can be called manually for testing)
        /// POST /api/chat/cleanup
        /// </summary>
        [HttpPost("cleanup")]
        public IActionResult ForceCleanup()
        {
            try
            {
                var expiredSessions = _sessions
                    .Where(kvp => kvp.Value.IsExpired)
                    .Select(kvp => kvp.Key)
                    .ToList();

                foreach (var sessionId in expiredSessions)
                {
                    _sessions.TryRemove(sessionId, out _);
                }

                _lastCleanup = DateTime.UtcNow;

                return Ok(new
                {
                    success = true,
                    sessionsRemoved = expiredSessions.Count,
                    remainingSessions = _sessions.Count
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error during forced cleanup");
                return StatusCode(500, new { error = "Cleanup failed" });
            }
        }
    }

    // ====================================================================
    // REQUEST MODELS (specific to controller endpoints)
    // ====================================================================

    /// <summary>
    /// Request model for clearing a session
    /// </summary>
    public class ClearSessionRequest
    {
        public string SessionId { get; set; } = string.Empty;
    }
}
