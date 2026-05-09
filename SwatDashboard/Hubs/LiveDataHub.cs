using Microsoft.AspNetCore.SignalR;
using SwatDashboard.Models;

namespace SwatDashboard.Hubs
{
    public class LiveDataHub : Hub
    {
        private readonly ILogger<LiveDataHub> _logger;

        public LiveDataHub(ILogger<LiveDataHub> logger)
        {
            _logger = logger;
        }

        public override async Task OnConnectedAsync()
        {
            _logger.LogInformation("Client connected: {ConnectionId}", Context.ConnectionId);
            await base.OnConnectedAsync();
        }

        public override async Task OnDisconnectedAsync(Exception? exception)
        {
            _logger.LogInformation("Client disconnected: {ConnectionId}", Context.ConnectionId);
            await base.OnDisconnectedAsync(exception);
        }

        // This will be called from the background service to push updates to all clients
        public async Task SendLiveUpdate(LiveDashboardData data)
        {
            await Clients.All.SendAsync("ReceiveLiveUpdate", data);
        }
    }
}
