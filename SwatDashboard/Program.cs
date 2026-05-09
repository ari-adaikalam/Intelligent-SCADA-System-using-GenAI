using SwatDashboard.Hubs;
using SwatDashboard.Services;
using System.Net.Http;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.
builder.Services.AddControllersWithViews();

// Add SignalR for real-time updates
builder.Services.AddSignalR();

// Register services (Scoped because you create scopes in the BackgroundService)
builder.Services.AddScoped<DatabaseService>();
builder.Services.AddScoped<MlInferenceService>();
builder.Services.AddScoped<ExportService>();
builder.Services.AddHostedService<MlApiHostedService>();
builder.Services.AddScoped<ChatService>();


// Add HttpClient for Python ML API (tuned for fast localhost reuse)
builder.Services.AddHttpClient("PythonML", client =>
{
    client.BaseAddress = new Uri("http://127.0.0.1:5000"); // Python service
    client.Timeout = TimeSpan.FromSeconds(10);
})
.ConfigurePrimaryHttpMessageHandler(() => new SocketsHttpHandler
{
    PooledConnectionLifetime = TimeSpan.FromMinutes(10),
    PooledConnectionIdleTimeout = TimeSpan.FromMinutes(2),
    MaxConnectionsPerServer = 50,

    // If your .NET version supports these, keep them; otherwise delete them.
    KeepAlivePingDelay = TimeSpan.FromSeconds(30),
    KeepAlivePingTimeout = TimeSpan.FromSeconds(10),
    KeepAlivePingPolicy = HttpKeepAlivePingPolicy.Always,
});

// Add background service for live data updates
builder.Services.AddHostedService<LiveDataBackgroundService>();

var app = builder.Build();

// Configure the HTTP request pipeline.
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Home/Error");
    app.UseHsts();
}

app.UseHttpsRedirection();
app.UseStaticFiles();

app.UseRouting();

app.UseAuthorization();

// Map SignalR hub
app.MapHub<LiveDataHub>("/liveDataHub");

app.MapControllerRoute(
    name: "default",
    pattern: "{controller=Dashboard}/{action=Index}/{id?}");

app.Run();
