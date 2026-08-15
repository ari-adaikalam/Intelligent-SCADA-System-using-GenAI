using System.Threading.RateLimiting;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.RateLimiting;
using SwatDashboard.Hubs;
using SwatDashboard.Services;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.
builder.Services.AddControllersWithViews();

// Add SignalR for real-time updates
builder.Services.AddSignalR();

// Rate limiting — this app has no authentication (it's a public portfolio
// dashboard by design), so per-IP limits are the main defense against a
// visitor hammering the chat endpoint (each call triggers a billed LLM call)
// or bulk-exporting the dataset repeatedly.
static string ClientKey(HttpContext ctx) => ctx.Connection.RemoteIpAddress?.ToString() ?? "unknown";

builder.Services.AddRateLimiter(options =>
{
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;

    // Default limiter for everything else.
    options.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(ctx =>
        RateLimitPartition.GetFixedWindowLimiter(ClientKey(ctx), _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 120,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));

    // Chat triggers an LLM call (and, indirectly, a DB query) — keep this tight.
    options.AddPolicy("chat", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(ClientKey(ctx), _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 10,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));

    // Exports can pull large datasets — keep this the tightest.
    options.AddPolicy("export", ctx =>
        RateLimitPartition.GetFixedWindowLimiter(ClientKey(ctx), _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 5,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));
});

// Register services
builder.Services.AddScoped<DatabaseService>();
builder.Services.AddScoped<MlInferenceService>();
builder.Services.AddScoped<ExportService>();
builder.Services.AddScoped<ChatService>();

// Background services
builder.Services.AddHostedService<MlApiHostedService>();
builder.Services.AddHostedService<LiveDataBackgroundService>();
builder.Services.AddHostedService<WakeUpService>();  // uses its own static browser-mimicking clients

// HttpClient for Python ML API
builder.Services.AddHttpClient("PythonML", client =>
{
    var mlUrl = builder.Configuration["SwatSettings:PythonMlApiUrl"]
                ?? "https://ariadaikalam-swat-ml-api.hf.space";
    client.BaseAddress = new Uri(mlUrl);
    client.Timeout = TimeSpan.FromSeconds(30);
})
.ConfigurePrimaryHttpMessageHandler(() => new SocketsHttpHandler
{
    PooledConnectionLifetime = TimeSpan.FromMinutes(10),
    PooledConnectionIdleTimeout = TimeSpan.FromMinutes(2),
    MaxConnectionsPerServer = 50,
    KeepAlivePingDelay = TimeSpan.FromSeconds(30),
    KeepAlivePingTimeout = TimeSpan.FromSeconds(10),
    KeepAlivePingPolicy = HttpKeepAlivePingPolicy.Always,
});

// NOTE: "WakeUp" named client kept for any other code that still uses it,
// but WakeUpService now uses its own static clients with browser headers.
builder.Services.AddHttpClient("WakeUp", client =>
{
    client.Timeout = TimeSpan.FromSeconds(30);
});

var app = builder.Build();

// Render sits in front of this app as a reverse proxy — trust its
// X-Forwarded-For header so RemoteIpAddress (used for rate limiting above)
// reflects the real client IP instead of Render's internal proxy IP.
app.UseForwardedHeaders(new ForwardedHeadersOptions
{
    ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto
});

// Configure the HTTP request pipeline.
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Home/Error");
    app.UseHsts();
}

// Security headers on every response.
// CSP note: the app has no inline <script> tags (all JS is external, either
// same-origin or from the CDNs listed below), so script-src can be locked
// down without 'unsafe-inline'. Inline `style="..."` attributes and
// JS-driven `.style` updates ARE used extensively throughout dashboard.js /
// chat.js / the views, so style-src keeps 'unsafe-inline' rather than risk
// breaking layout.
app.Use(async (context, next) =>
{
    var headers = context.Response.Headers;
    headers["X-Content-Type-Options"] = "nosniff";
    headers["X-Frame-Options"] = "DENY";
    headers["Referrer-Policy"] = "strict-origin-when-cross-origin";
    headers["Content-Security-Policy"] =
        "default-src 'self'; " +
        "script-src 'self' https://cdn.jsdelivr.net https://cdn.plot.ly https://cdnjs.cloudflare.com; " +
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; " +
        "font-src 'self' https://cdn.jsdelivr.net; " +
        "img-src 'self' data:; " +
        "connect-src 'self' https://ariadaikalam-swat-ml-api.hf.space https://ariadaikalam-swat-ingest.hf.space https://ariadaikalam-swat-plant-sender.hf.space https://swat-rag-api.onrender.com; " +
        "frame-src https://ariadaikalam-swat-ml-api.hf.space https://ariadaikalam-swat-ingest.hf.space https://ariadaikalam-swat-plant-sender.hf.space https://swat-rag-api.onrender.com; " +
        "object-src 'none'; " +
        "base-uri 'self'; " +
        "frame-ancestors 'none'";
    await next();
});

// NOTE: Removed app.UseHttpsRedirection() — Render handles HTTPS externally
app.UseStaticFiles();
app.UseRouting();
app.UseRateLimiter();
app.UseAuthorization();

// Map SignalR hub
app.MapHub<LiveDataHub>("/liveDataHub");

app.MapControllerRoute(
    name: "default",
    pattern: "{controller=Dashboard}/{action=Index}/{id?}");

app.Run();
