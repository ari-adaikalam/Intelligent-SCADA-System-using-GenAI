using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

public class MlApiHostedService : IHostedService
{
    private readonly ILogger<MlApiHostedService> _logger;
    private Process? _mlProcess;


    private static readonly HttpClient _http = new HttpClient
    {
        Timeout = TimeSpan.FromSeconds(2)
    };

    public MlApiHostedService(ILogger<MlApiHostedService> logger)
    {
        _logger = logger;
    }

    private void KillProcessUsingPort5000()
    {
        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/c for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do taskkill /F /PID %a",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };

            using var p = Process.Start(psi);
            p?.WaitForExit(2000);

            _logger.LogInformation("Checked/killed any process listening on port 5000 (if existed).");
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to kill existing port 5000 listener.");
        }
    }

    private static string FindPythonExe(string projectRoot)
    {
        var candidates = new[]
        {
            Path.Combine(projectRoot, ".venv", "Scripts", "python.exe"),
            Path.Combine(projectRoot, "venv",  "Scripts", "python.exe"),
            Path.Combine(projectRoot, "..", ".venv", "Scripts", "python.exe"),
            Path.Combine(projectRoot, "..", "venv",  "Scripts", "python.exe"),
        };

        foreach (var p in candidates)
            if (File.Exists(p)) return Path.GetFullPath(p);

        return "python";
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var webRoot = AppContext.BaseDirectory;
        var projectRoot = Path.GetFullPath(Path.Combine(webRoot, "..", "..", ".."));

        var pythonExe = FindPythonExe(projectRoot);
        var mlDir = Path.Combine(projectRoot, "PythonMlService");
        var mlScript = Path.Combine(mlDir, "ml_api.py");

        _logger.LogInformation("ProjectRoot: {ProjectRoot}", projectRoot);
        _logger.LogInformation("PythonExe:   {PythonExe}", pythonExe);
        _logger.LogInformation("MlDir:       {MlDir}", mlDir);
        _logger.LogInformation("MlScript:    {MlScript}", mlScript);

        if (!Directory.Exists(mlDir))
            throw new DirectoryNotFoundException($"ML directory not found: {mlDir}");
        if (!File.Exists(mlScript))
            throw new FileNotFoundException($"ML script not found: {mlScript}");

        if (_mlProcess is { HasExited: false })
        {
            _logger.LogInformation("ML API process already running.");
            return;
        }

        var psi = new ProcessStartInfo
        {
            FileName = pythonExe,
            Arguments = $"\"{mlScript}\"",
            WorkingDirectory = mlDir,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8
        };

        // UTF-8 safe output for Windows console
        psi.Environment["PYTHONUTF8"] = "1";
        psi.Environment["PYTHONIOENCODING"] = "utf-8";
        psi.Environment["PYTHONUNBUFFERED"] = "1";
        psi.Environment["SWAT_API_MODE"] = "1";


        _mlProcess = new Process { StartInfo = psi, EnableRaisingEvents = true };

        _mlProcess.OutputDataReceived += (_, e) =>
        {
            if (!string.IsNullOrWhiteSpace(e.Data))
                _logger.LogInformation("[ML] {Line}", e.Data);
        };
        _mlProcess.ErrorDataReceived += (_, e) =>
        {
            if (string.IsNullOrWhiteSpace(e.Data)) return;

            var line = e.Data;

            // Treat common TF/Flask noise as INFO
            if (line.Contains("oneDNN custom operations are on") ||
                line.Contains("cpu_feature_guard") ||
                line.Contains("missing ScriptRunContext") ||
                line.Contains("This is a development server") ||
                line.Contains("Running on http://") ||
                line.Contains("Press CTRL+C") ||
                line.Contains("To enable the following instructions"))
            {
                //_logger.LogInformation("[ML] {Line}", line);
                return;
            }

            // Anything else -> warning (not error)
            //_logger.LogWarning("[ML] {Line}", line);
        };

        // ✅ IMPORTANT: kill any old Flask/python already using 5000
        KillProcessUsingPort5000();

        _logger.LogInformation("Starting ML API process...");
        _mlProcess.Start();
        _mlProcess.BeginOutputReadLine();
        _mlProcess.BeginErrorReadLine();

        await WaitForMlReadyAsync(cancellationToken);
    }

    private async Task WaitForMlReadyAsync(CancellationToken ct)
    {
        var deadline = DateTime.UtcNow.AddSeconds(60);
        bool? lastAvail = null;
        int pollCount = 0;

        while (DateTime.UtcNow < deadline && !ct.IsCancellationRequested)
        {
            pollCount++;

            try
            {
                if (_mlProcess is { HasExited: true })
                {
                    _logger.LogError("ML API process exited early. ExitCode={ExitCode}", _mlProcess.ExitCode);
                    return;
                }

                var resp = await _http.GetAsync("http://127.0.0.1:5000/health", ct);
                var body = await resp.Content.ReadAsStringAsync(ct);

                var isAvail = body.Contains("\"ml_available\":true", StringComparison.OrdinalIgnoreCase)
                           || body.Contains("\"ml_available\": true", StringComparison.OrdinalIgnoreCase);

                if (lastAvail == null || isAvail != lastAvail || pollCount % 10 == 0)
                {
                    _logger.LogInformation("ML health: available={Avail} body={Body}", isAvail, body);
                    lastAvail = isAvail;
                }

                if (resp.IsSuccessStatusCode && isAvail)
                {
                    _logger.LogInformation("ML API is READY (ml_available=true).");
                    return;
                }
            }
            catch
            {
                if (pollCount % 10 == 0)
                    _logger.LogInformation("Waiting for ML API... (not reachable yet)");
            }

            await Task.Delay(500, ct);
        }

        _logger.LogWarning("Timed out waiting for ML API readiness.");
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        try
        {
            if (_mlProcess is { HasExited: false })
            {
                _logger.LogInformation("Stopping ML API...");
                _mlProcess.Kill(entireProcessTree: true);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to stop ML API cleanly.");
        }

        return Task.CompletedTask;
    }
}
