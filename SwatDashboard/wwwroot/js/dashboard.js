// dashboard.js - FIXED VERSION
// Fixes: broken template literal in updateTimeRange, IST timestamps on all charts

let connection = null;
let analyticsData = null;
let recentData = [];
let analyticsReqSeq = 0;
let windowDebounceTimer = null;
const analyticsCache = new Map();
let plotsNeedRender = true;

const STAGES = {
    "Stage 1 - Intake": ["true_FIT101", "true_LIT101", "MV101", "P101"],
    "Stage 2 - Pre-treatment": ["true_FIT201", "true_AIT201", "true_AIT202", "true_AIT203", "MV201", "P201", "P203", "P205"],
    "Stage 3 - Ultrafiltration (UF)": ["true_FIT301", "true_LIT301", "true_DPIT301", "MV301", "MV302", "MV303", "MV304", "P302"],
    "Stage 4 - Dechlorination (UV)": ["true_FIT401", "true_LIT401", "true_AIT401", "true_AIT402", "UV401", "P402", "P403"],
    "Stage 5 - Reverse Osmosis (RO)": ["true_FIT501", "true_PIT501", "true_AIT501", "P501"]
};
// ── SERVICE MAP ───────────────────────────────────────────────
const SERVICE_MAP = {
    "ML API":        "svc-ml",
    "Ingest":        "svc-ingest",
    "Plant Sender":  "svc-sender",
    "RAG API":       "svc-rag"
};
 
// ══════════════════════════════════════════════════════════════
// WAKE SYSTEM  (browser-only responsibility)
//
// Architecture:
//   Browser  → wakes services  (iframes for HF, fetch+retry for Render)
//   Server   → only checks status  (/Dashboard/ServiceStatus)
//
// Why browser, not server:
//   Server-to-server requests, even with browser headers, are still
//   seen as API calls at the CDN/edge level. Only a real browser
//   context produces the full request fingerprint HF/Render expect.
// ══════════════════════════════════════════════════════════════
 
// ── All services — one unified list ───────────────────────────
// Every service gets both treatment:
//   iframe  → triggers container boot (real browser navigation)
//   fetch   → retries until ready, tells us exactly when it's up
//
// Both run in parallel for every service. Belt-and-suspenders.
 
const ALL_WAKE_SERVICES = [
    { name: 'ML API',       url: 'https://ariadaikalam-swat-ml-api.hf.space/' },
    { name: 'Ingest',       url: 'https://ariadaikalam-swat-ingest.hf.space/' },
    { name: 'Plant Sender', url: 'https://ariadaikalam-swat-plant-sender.hf.space/' },
    { name: 'RAG API',      url: 'https://swat-rag-api.onrender.com/' },
];
 
// ── iframe wake ────────────────────────────────────────────────
function fireIframe(url, label) {
    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;border:none;top:-9999px;left:-9999px;';
    iframe.src = url;
    iframe.onload  = () => { console.log(`[WAKE] iframe loaded: ${label}`); };
    iframe.onerror = () => { console.log(`[WAKE] iframe error (cross-origin OK): ${label}`); };
    document.body.appendChild(iframe);
    setTimeout(() => { try { document.body.removeChild(iframe); } catch(e) {} }, 30000);
}
 
function wakeWithIframes() {
    ALL_WAKE_SERVICES.forEach(svc => {
        console.log(`[WAKE] Firing 3 iframes for: ${svc.name}`);
        fireIframe(svc.url, svc.name);
        setTimeout(() => fireIframe(svc.url, `${svc.name} #2`), 300);
        setTimeout(() => fireIframe(svc.url, `${svc.name} #3`), 600);
    });
}
 
// ── fetch + retry loop ─────────────────────────────────────────
const WAKE_MAX_ATTEMPTS  = 25;
const WAKE_INTERVAL_MS   = 20000;
const _wakeTimers        = new Map(); // name → intervalId
const _wakeAttempts      = new Map(); // name → attempt count
 
function wakeWithFetch() {
    ALL_WAKE_SERVICES.forEach(svc => {
        _wakeAttempts.set(svc.name, 0);
 
        const tryWake = async () => {
            const attempt = _wakeAttempts.get(svc.name) + 1;
            _wakeAttempts.set(svc.name, attempt);
            console.log(`[WAKE] ${svc.name} fetch attempt ${attempt}/${WAKE_MAX_ATTEMPTS}`);
 
            try {
                const resp = await fetch(svc.url, { cache: 'no-store' });
                if (resp.ok || resp.status < 500) {
                    console.log(`[WAKE] ✅ ${svc.name} awake (HTTP ${resp.status}) — stopping retries.`);
                    clearInterval(_wakeTimers.get(svc.name));
                    _wakeTimers.delete(svc.name);
                    return;
                }
            } catch(e) {
                console.log(`[WAKE] ${svc.name} not ready yet: ${e.message}`);
            }
 
            if (attempt >= WAKE_MAX_ATTEMPTS) {
                console.warn(`[WAKE] ⚠️ ${svc.name} did not respond after ${WAKE_MAX_ATTEMPTS} attempts.`);
                clearInterval(_wakeTimers.get(svc.name));
                _wakeTimers.delete(svc.name);
            }
        };
 
        tryWake();
        _wakeTimers.set(svc.name, setInterval(tryWake, WAKE_INTERVAL_MS));
    });
}
 
// ── Main entry point ───────────────────────────────────────────
function wakeAllServices() {
    console.log('[WAKE] Starting wake sequence — browser is responsible for waking all services.');
    wakeWithIframes(); // triggers container boot on all services
    wakeWithFetch();   // retries until each service is ready
}
 
if (document.body) {
    wakeAllServices();
} else {
    document.addEventListener('DOMContentLoaded', wakeAllServices);
}
 
async function pollServicesReady() {
    const splash = document.getElementById('splashScreen');
    const progress = document.getElementById('splashProgress');
    const msg = document.getElementById('splashMsg');
    if (!splash) return;
 
    let attempts = 0;
    const maxAttempts = 30; // 150s max
 
    while (attempts < maxAttempts) {
        attempts++;
 
        const elapsed = attempts * 5;
        const elapsedStr = elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed/60)}m ${elapsed%60}s`;
        msg.textContent = `Waking up all services... (${elapsedStr} elapsed)`;
 
        try {
            const resp = await fetch('/Dashboard/ServiceStatus');
            const data = await resp.json();
 
            let totalReady = 0;
 
            data.services.forEach(svc => {
                const rowId = SERVICE_MAP[svc.name];
                if (!rowId) return;
                const row = document.getElementById(rowId);
                if (!row) return;
 
                if (svc.ok) {
                    row.className = 'svc-row svc-ok';
                    row.querySelector('.svc-status').textContent = 'Ready ✅';
                    totalReady++;
                } else {
                    row.className = 'svc-row';
                    row.querySelector('.svc-status').textContent =
                        svc.name === 'RAG API'
                            ? (elapsed < 30 ? 'Starting up...' : elapsed < 70 ? 'Almost ready...' : 'Taking longer than usual...')
                            : 'Waking up...';
                }
            });
 
            const pct = Math.round((totalReady / data.services.length) * 100);
            progress.style.width = pct + '%';
 
            if (data.allReady) {
                msg.textContent = '✅ All systems ready! Loading dashboard...';
                progress.style.width = '100%';
                await new Promise(r => setTimeout(r, 800));
                splash.style.opacity = '0';
                setTimeout(() => splash.style.display = 'none', 800);
                return;
            }
 
        } catch(e) {
            msg.textContent = 'Checking services... please wait.';
        }
 
        await new Promise(r => setTimeout(r, 5000));
    }
 
    // Timeout — show dashboard anyway
    msg.textContent = 'Loading dashboard (some services may still be starting — retry chat if needed)';
    await new Promise(r => setTimeout(r, 2000));
    splash.style.opacity = '0';
    setTimeout(() => splash.style.display = 'none', 800);
}
 
pollServicesReady();
document.addEventListener('DOMContentLoaded', function () {
    initializeLiveDashboard();
    initializeAnalyticsDashboard();
    setupTabListeners();
});

// ──────────────────────────────────────────────
// Helper: Wait until tab pane has reasonable size
// ──────────────────────────────────────────────
function whenTabIsReady(callback, delay = 150) {
    const check = () => {
        const tabPane = document.querySelector('#analytics-panel');
        if (tabPane && tabPane.offsetWidth > 50 && tabPane.offsetHeight > 50) {
            callback();
        } else {
            setTimeout(check, 80);
        }
    };
    setTimeout(check, delay);
}

function normalizeAnalyticsResponse(json) {
    if (Array.isArray(json)) return json;
    if (json && Array.isArray(json.data)) return json.data;
    if (json && Array.isArray(json.records)) return json.records;
    if (json && Array.isArray(json.items)) return json.items;
    return [];
}

// ──────────────────────────────────────────────
// IST helpers — FIX: shift UTC → IST for Plotly
// ──────────────────────────────────────────────
const IST_OFFSET_MS = (5 * 60 + 30) * 60 * 1000; // +5:30 in ms

function toIST(dateStr) {
    // Returns a Date shifted by +5:30 so Plotly renders IST wall-clock time
    const utc = new Date(dateStr);
    return new Date(utc.getTime() + IST_OFFSET_MS);
}

function formatIST(dateStr) {
    return new Date(dateStr).toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour12: false
    });
}

function prepareChartContainer(containerId, desiredHeight = 360) {
    const container = typeof containerId === 'string'
        ? document.getElementById(containerId)
        : containerId;
    if (!container) return null;

    container.style.position = 'relative';
    container.style.minHeight = `${desiredHeight}px`;

    let host = container.querySelector(':scope > .plot-host');
    if (!host) {
        host = document.createElement('div');
        host.className = 'plot-host';
        container.appendChild(host);
    }

    host.style.cssText = `
        position: relative;
        z-index: 1;
        width: 100%;
        height: ${desiredHeight}px;
    `;

    return { container, host };
}

function showChartPlaceholder(containerId, text = 'No data available') {
    const container = document.getElementById(containerId);
    if (!container) return;

    hideChartPlaceholder(containerId);

    const ph = document.createElement('div');
    ph.className = 'chart-placeholder p-4 text-center text-muted';
    ph.style.cssText = `
        position: absolute; inset: 0;
        display: flex; align-items: center; justify-content: center;
        z-index: 10; pointer-events: none;
        background: rgba(248,249,250,0.85);
    `;
    ph.textContent = text;
    container.appendChild(ph);
}

function hideChartPlaceholder(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.querySelectorAll('.chart-placeholder').forEach(ph => {
        ph.remove();
        console.log(`[${containerId}] Removed placeholder from DOM`);
    });

    container.querySelectorAll('.p-4.text-center.text-muted').forEach(div => {
        if (div.textContent.includes('No data') || div.textContent.includes('Waiting')) {
            div.remove();
            console.log(`[${containerId}] Removed stray no-data text`);
        }
    });
}

async function renderPlot(containerId, traces, layout, config = { responsive: true }) {
    const desiredHeight = layout?.height || 360;
    const ctx = prepareChartContainer(containerId, desiredHeight);
    if (!ctx) return;
    const { host } = ctx;

    const width = host.offsetWidth;
    const height = host.offsetHeight;
    console.log(`[renderPlot:${containerId}] Called | size: ${width} × ${height}`);

    if (height === 0) host.style.height = `${desiredHeight}px`;

    hideChartPlaceholder(containerId);

    layout = { autosize: true, ...layout };

    try {
        await Plotly.react(host, traces, layout, config);
        console.log(`[renderPlot:${containerId}] Plot rendered successfully`);
    } catch (err) {
        console.error(`[renderPlot:${containerId}] Plotly error:`, err);
        showChartPlaceholder(containerId, 'Chart render failed');
        return;
    }

    requestAnimationFrame(() => Plotly.Plots.resize(host));
    setTimeout(() => Plotly.Plots.resize(host), 120);
    setTimeout(() => Plotly.Plots.resize(host), 450);
}

function resizeAllCharts() {
    console.log('[resizeAllCharts] Triggered');

    const charts = [
        { id: 'trendChart', fn: plotTrendExplorer },
        { id: 'distributionChart', fn: plotDistribution },
        { id: 'rollingChart', fn: plotRollingStats }
    ];

    charts.forEach(({ id, fn }) => {
        const container = document.getElementById(id);
        if (!container) return;

        const host = container.querySelector('.plot-host') || container;
        const w = host.offsetWidth;
        const h = host.offsetHeight;

        if (analyticsData?.length > 0 && (plotsNeedRender || id === 'trendChart' || id === 'rollingChart') && w > 50 && h > 50) {
            console.log(`[${id}] Forcing re-plot (trend/rolling special case)`);
            hideChartPlaceholder(id);
            fn(analyticsData);
        }

        if (host.classList.contains('js-plotly-plot') || host._fullLayout) {
            console.log(`[${id}] Resizing existing plot`);
            try { Plotly.Plots.resize(host); } catch (e) { console.warn('resize failed', e); }
        }
    });
}

function rollingMean(values, windowSize) {
    const out = new Array(values.length).fill(null);
    let sum = 0, count = 0;
    const q = [];

    for (let i = 0; i < values.length; i++) {
        const v = values[i];
        q.push(v);
        if (Number.isFinite(v)) { sum += v; count++; }

        if (q.length > windowSize) {
            const old = q.shift();
            if (Number.isFinite(old)) { sum -= old; count--; }
        }

        out[i] = (q.length === windowSize && count > 0) ? (sum / count) : null;
    }
    return out;
}

function rollingStd(values, windowSize) {
    const out = new Array(values.length).fill(null);
    const q = [];

    for (let i = 0; i < values.length; i++) {
        q.push(values[i]);
        if (q.length > windowSize) q.shift();

        if (q.length === windowSize) {
            const finite = q.filter(Number.isFinite);
            if (finite.length < 2) { out[i] = null; continue; }

            const mean = finite.reduce((a, b) => a + b, 0) / finite.length;
            const varSum = finite.reduce((a, b) => a + (b - mean) ** 2, 0);
            out[i] = Math.sqrt(varSum / (finite.length - 1));
        }
    }
    return out;
}

function rollingSlope(values, windowSize) {
    const out = new Array(values.length).fill(null);
    const q = [];

    for (let i = 0; i < values.length; i++) {
        const v = values[i];
        q.push({ idx: i, val: v });

        if (q.length > windowSize) q.shift();

        if (q.length === windowSize) {
            const finite = q.filter(p => Number.isFinite(p.val));
            if (finite.length < 2) continue;

            let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
            const n = finite.length;

            finite.forEach(p => {
                const x = p.idx - finite[0].idx;
                sumX += x;
                sumY += p.val;
                sumXY += x * p.val;
                sumX2 += x * x;
            });

            const denom = n * sumX2 - sumX * sumX;
            if (Math.abs(denom) < 1e-10) continue;

            out[i] = (n * sumXY - sumX * sumY) / denom;
        }
    }
    return out;
}

async function refreshAllCharts() {
    if (!Array.isArray(analyticsData) || analyticsData.length === 0) {
        clearAnalytics();
        return;
    }

    updateKpiSummary(analyticsData);

    await plotTrendExplorer(analyticsData);
    await plotDistribution(analyticsData);
    await plotRollingStats(analyticsData);

    ['trendChart', 'distributionChart', 'rollingChart'].forEach(hideChartPlaceholder);

    plotsNeedRender = false;
    resizeAllCharts();
    setTimeout(resizeAllCharts, 300);
}

function extractFirstArrayDeep(json) {
    if (Array.isArray(json)) return json;
    if (json && typeof json === 'object') {
        for (const k of ['data', 'records', 'items', 'result', 'payload']) {
            if (Array.isArray(json[k])) return json[k];
        }
        for (const v of Object.values(json)) {
            const found = extractFirstArrayDeep(v);
            if (Array.isArray(found) && found.length >= 0) return found;
        }
    }
    return null;
}

// ============================================================
// LIVE DASHBOARD
// ============================================================

function initializeLiveDashboard() {
    connection = new signalR.HubConnectionBuilder()
        .withUrl("/liveDataHub")
        .withAutomaticReconnect()
        .build();

    connection.on("ReceiveLiveUpdate", function (data) {
        updateLiveDashboard(data);
    });

    connection.start().then(() => console.log("SignalR connected")).catch(err => console.error(err));
}

function updateLiveDashboard(data) {
    if (!data || !data.latestData) return;

    const latest = data.latestData;
    const payload = latest.payload;

    if (data.recentData) recentData = data.recentData;

    updatePlantStatus(data, latest, payload);
    updateProcessOverview(payload);

    if (data.status.isOnline) {
        document.getElementById('mlOfflineWarning').style.display = 'none';
        document.getElementById('mlSection').style.display = 'block';
        if (data.mlResult?.success) updateMlSection(data.mlResult);
    } else {
        document.getElementById('mlOfflineWarning').style.display = 'block';
        document.getElementById('mlSection').style.display = 'none';
    }
}

function updatePlantStatus(data, latest, payload) {
    document.getElementById('plantId').textContent = latest.plantId || 'SWAT_SIM_01';

    const downtimeFlag = parseInt(payload.downtime_flag || 0);
    const downtimeType = (payload.downtime_type || 'run').toLowerCase();
    let stateText = downtimeFlag === 1 ? (downtimeType.includes('maint') ? '🟡 MAINTENANCE' : '🔴 DOWNTIME') : '🟢 RUN';
    document.getElementById('plantState').innerHTML = stateText;

    // FIX: use formatIST for last update display
    document.getElementById('lastUpdate').textContent = formatIST(latest.ts);
    document.getElementById('connection').innerHTML = data.status.isOnline ? '🟢 ONLINE' : '🔴 OFFLINE';
}

function updateProcessOverview(p) {
    document.getElementById('stage1Metrics').innerHTML = `
        <div class="kpi"><div class="kpi-label">Flow (FIT101)</div><div class="kpi-value">${fmt(p.true_FIT101, 3)}</div></div>
        <div class="kpi"><div class="kpi-label">Tank Level (LIT101)</div><div class="kpi-value">${fmt(p.true_LIT101, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">Valve MV101</div><div class="kpi-value">${valveBadge(p.MV101)}</div></div>
        <div class="kpi"><div class="kpi-label">Pump P101</div><div class="kpi-value">${onBadge(p.P101)}</div></div>
    `;
    plotSparkline('stage1Sparkline', 'true_FIT101');

    document.getElementById('stage2Metrics').innerHTML = `
        <div class="kpi"><div class="kpi-label">Flow (FIT201)</div><div class="kpi-value">${fmt(p.true_FIT201, 3)}</div></div>
        <div class="kpi"><div class="kpi-label">Conductivity (AIT201)</div><div class="kpi-value">${fmt(p.true_AIT201, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">pH (AIT202)</div><div class="kpi-value">${fmt(p.true_AIT202, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">ORP (AIT203)</div><div class="kpi-value">${fmt(p.true_AIT203, 1)}</div></div>
        <div class="kpi"><div class="kpi-label">Valve MV201</div><div class="kpi-value">${valveBadge(p.MV201)}</div></div>
        <div class="kpi"><div class="kpi-label">NaCl Pump P201</div><div class="kpi-value">${onBadge(p.P201)}</div></div>
        <div class="kpi"><div class="kpi-label">HCl Pump P203</div><div class="kpi-value">${onBadge(p.P203)}</div></div>
        <div class="kpi"><div class="kpi-label">NaOCl Pump P205</div><div class="kpi-value">${onBadge(p.P205)}</div></div>
    `;
    plotSparkline('stage2Sparkline', 'true_AIT202');

    document.getElementById('stage3Metrics').innerHTML = `
        <div class="kpi"><div class="kpi-label">Flow (FIT301)</div><div class="kpi-value">${fmt(p.true_FIT301, 3)}</div></div>
        <div class="kpi"><div class="kpi-label">Tank Level (LIT301)</div><div class="kpi-value">${fmt(p.true_LIT301, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">ΔP (DPIT301)</div><div class="kpi-value">${fmt(p.true_DPIT301, 3)}</div></div>
        <div class="kpi"><div class="kpi-label">Valve MV301</div><div class="kpi-value">${valveBadge(p.MV301)}</div></div>
        <div class="kpi"><div class="kpi-label">Valve MV302</div><div class="kpi-value">${valveBadge(p.MV302)}</div></div>
        <div class="kpi"><div class="kpi-label">Valve MV303</div><div class="kpi-value">${valveBadge(p.MV303)}</div></div>
        <div class="kpi"><div class="kpi-label">Valve MV304</div><div class="kpi-value">${valveBadge(p.MV304)}</div></div>
        <div class="kpi"><div class="kpi-label">Pump P302</div><div class="kpi-value">${onBadge(p.P302)}</div></div>
    `;
    plotSparkline('stage3Sparkline', 'true_DPIT301');

    document.getElementById('stage4Metrics').innerHTML = `
        <div class="kpi"><div class="kpi-label">Feed Flow (FIT401)</div><div class="kpi-value">${fmt(p.true_FIT401, 3)}</div></div>
        <div class="kpi"><div class="kpi-label">Tank Level (LIT401)</div><div class="kpi-value">${fmt(p.true_LIT401, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">Hardness (AIT401)</div><div class="kpi-value">${fmt(p.true_AIT401, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">ORP (AIT402)</div><div class="kpi-value">${fmt(p.true_AIT402, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">Pump P402</div><div class="kpi-value">${onBadge(p.P402)}</div></div>
        <div class="kpi"><div class="kpi-label">NaHSO₄ Pump P403</div><div class="kpi-value">${onBadge(p.P403)}</div></div>
    `;
    plotSparkline('stage4Sparkline', 'true_FIT401');

    document.getElementById('stage5Metrics').innerHTML = `
        <div class="kpi"><div class="kpi-label">Permeate Flow (FIT501)</div><div class="kpi-value">${fmt(p.true_FIT501, 3)}</div></div>
        <div class="kpi"><div class="kpi-label">pH (AIT501)</div><div class="kpi-value">${fmt(p.true_AIT501, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">Feed pressure (PIT501)</div><div class="kpi-value">${fmt(p.true_PIT501, 2)}</div></div>
        <div class="kpi"><div class="kpi-label">RO Pump P501</div><div class="kpi-value">${onBadge(p.P501)}</div></div>
    `;
    plotSparkline('stage5Sparkline', 'true_AIT501');
}

function plotSparkline(id, key) {
    if (!recentData.length) return;
    const values = recentData.map(d => d.payload[key] || null);
    // FIX: use toIST for sparkline timestamps
    const timestamps = recentData.map(d => toIST(d.ts));

    Plotly.newPlot(id, [{
        x: timestamps, y: values, type: 'scatter', mode: 'lines',
        line: { color: '#4A90E2', width: 2 }, showlegend: false
    }], {
        margin: { t: 5, b: 20, l: 30, r: 5 }, height: 90,
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: '#F8F9FA',
        xaxis: { visible: false, type: 'date' },
        yaxis: { visible: true, gridcolor: '#D1D9E6', zeroline: false }
    }, { displayModeBar: false, responsive: true });
}

function updateMlSection(mlResult) {
    const statusCard = document.getElementById('mlStatusCard');
    const statusValue = document.getElementById('mlStatusValue');
    const statusLabel = document.getElementById('mlStatusLabel');

    if (mlResult.stage1.isAnomaly) {
        statusCard.className = 'ml-status-card ml-status-faulted';
        statusValue.innerHTML = 'ISSUE 🔴';
    } else {
        statusCard.className = 'ml-status-card ml-status-normal';
        statusValue.innerHTML = 'NORMAL 🟢';
    }
    statusLabel.textContent = `Confidence: ${(mlResult.stage1.confidence * 100).toFixed(1)}%`;

    const state = (mlResult.stage2?.state || 'UNKNOWN').toUpperCase();
    const issueCard = document.getElementById('mlIssueCard');

    let issueClass = 'ml-status-monitor';
    let issueText = 'UNKNOWN ⚪';

    if (state === 'NORMAL') {
        issueClass = 'ml-status-normal';
        issueText = 'NORMAL 🟢';
    } else if (state === 'ANOMALY') {
        issueClass = 'ml-status-monitor';
        issueText = 'ANOMALY 🟠';
    } else if (state === 'DEGRADING') {
        issueClass = 'ml-status-degrading';
        issueText = 'DEGRADING 🟡';
    } else if (state === 'FAULTED') {
        issueClass = 'ml-status-faulted';
        issueText = 'FAULTED 🔴';
    }

    issueCard.className = `ml-status-card ${issueClass}`;
    document.getElementById('mlIssueValue').innerHTML = issueText;
    document.getElementById('mlIssueLabel').textContent =
        `Confidence: ${((mlResult.stage2?.confidence || 0) * 100).toFixed(1)}%`;

    if (mlResult.stage3?.component && state !== 'NORMAL') {
        const actionCard = document.getElementById('mlActionCard');

        const actionClass =
            state === 'FAULTED' ? 'ml-status-faulted' :
                state === 'DEGRADING' ? 'ml-status-degrading' :
                    'ml-status-monitor';

        actionCard.className = `ml-status-card ${actionClass}`;
        document.getElementById('mlActionValue').innerHTML = `⚠️ ${mlResult.stage3.component}`;
        document.getElementById('mlActionLabel').textContent =
            `Confidence: ${((mlResult.stage3?.confidence || 0) * 100).toFixed(1)}%`;
    } else {
        document.getElementById('mlActionCard').className = 'ml-status-card ml-status-normal';
        document.getElementById('mlActionValue').innerHTML = '✅ NONE';
        document.getElementById('mlActionLabel').textContent = 'All systems normal';
    }

    const bufferStatus = mlResult.bufferStatus;
    document.getElementById('mlBufferCard').className = bufferStatus.ready ? 'ml-status-card ml-status-normal' : 'ml-status-card ml-status-monitor';
    document.getElementById('mlBufferValue').innerHTML = bufferStatus.ready ? '✅ READY' : `⏳ WARMING (${bufferStatus.size}/60)`;
    document.getElementById('mlBufferLabel').textContent = bufferStatus.ready ? (bufferStatus.usingBuffer ? 'Using real sequences' : 'Using fallback') : 'Collecting samples...';

    updateComponentHealth(mlResult);
    updateRecommendedActions(mlResult);
}

function updateComponentHealth(mlResult) {
    const container = document.getElementById('componentHealth');

    if (!mlResult.componentHealth || Object.keys(mlResult.componentHealth).length === 0) {
        container.innerHTML = '<p class="text-muted">All systems operating normally</p>';
        return;
    }

    const priorityComps = Object.entries(mlResult.componentHealth)
        .filter(([_, h]) => ['FAULTED', 'DEGRADING', 'MONITOR'].includes(h.status));

    if (priorityComps.length === 0) {
        container.innerHTML = '<p class="text-success">✅ All components operating normally</p>';
        return;
    }

    let html = `<div class="attention-row">`;

    priorityComps.forEach(([comp, h]) => {
        html += `
          <div class="attention-item">
            <div class="ml-status-card ml-status-${h.status.toLowerCase()}" style="min-height:auto;padding:12px;">
              <div class="ml-card-title" style="font-size:13px;margin-bottom:4px;">${h.icon} ${comp}</div>
              <div class="ml-card-label" style="font-size:12px;">${h.message}</div>
            </div>
          </div>
        `;
    });

    html += `</div>`;
    container.innerHTML = html;
}

function updateRecommendedActions(mlResult) {
    const container = document.getElementById('recommendedActions');
    if (!mlResult.recommendedActions || mlResult.recommendedActions.length === 0) {
        container.innerHTML = '<p class="text-muted">No specific actions required at this time.</p>';
        return;
    }
    let html = '<ul style="padding-left:20px;margin:0;">';
    mlResult.recommendedActions.slice(0, 6).forEach(action => html += `<li style="margin-bottom:8px;">${action}</li>`);
    html += '</ul>';
    container.innerHTML = html;
}

// ============================================================
// ANALYTICS DASHBOARD
// ============================================================

async function initializeAnalyticsDashboard() {
    await loadPlantIds();
    populateSignalDropdowns();
    setupAnalyticsEventHandlers();
    updateTimeRange();
}

function setupAnalyticsEventHandlers() {
    document.getElementById('windowPreset').addEventListener('change', () => {
        clearTimeout(windowDebounceTimer);
        windowDebounceTimer = setTimeout(updateTimeRange, 250);
    });
    document.getElementById('plantSelect').addEventListener('change', updateTimeRange);
    document.getElementById('stageSelect').addEventListener('change', async function () {
        populateSignalDropdowns();
        if (analyticsData) await refreshAllCharts();
    });
    document.getElementById('signalSelector').addEventListener('change', async function () {
        if (analyticsData) {
            updateKpiSummary(analyticsData);
            await plotTrendExplorer(analyticsData);
            resizeAllCharts();
        }
    });

    document.getElementById('distSignalSelect').addEventListener('change', async function () {
        if (analyticsData) {
            await plotDistribution(analyticsData);
            resizeAllCharts();
        }
    });

    const binsSlider = document.getElementById('binsSlider');
    const binsValue = document.getElementById('binsValue');
    binsSlider.addEventListener('input', function () {
        binsValue.textContent = this.value;
    });
    binsSlider.addEventListener('change', async function () {
        if (analyticsData) {
            await plotDistribution(analyticsData);
            resizeAllCharts();
        }
    });

    document.getElementById('rollSignalSelect').addEventListener('change', async function () {
        if (analyticsData) {
            await plotRollingStats(analyticsData);
            resizeAllCharts();
        }
    });

    const rollSlider = document.getElementById('rollWindowSlider');
    const rollValue = document.getElementById('rollWindowValue');
    rollSlider.addEventListener('input', function () {
        rollValue.textContent = this.value;
    });
    rollSlider.addEventListener('change', async function () {
        if (analyticsData) {
            await plotRollingStats(analyticsData);
            resizeAllCharts();
        }
    });

    document.getElementById('showRollMean').addEventListener('change', async function () {
        if (analyticsData) {
            await plotRollingStats(analyticsData);
            resizeAllCharts();
        }
    });
    document.getElementById('showRollStd').addEventListener('change', async function () {
        if (analyticsData) {
            await plotRollingStats(analyticsData);
            resizeAllCharts();
        }
    });
    document.getElementById('showRollSlope')?.addEventListener('change', async () => {
        if (analyticsData) {
            await plotRollingStats(analyticsData);
            resizeAllCharts();
        }
    });

    // Custom date range apply button
    document.getElementById('applyCustomRange')?.addEventListener('click', updateTimeRange);
}

function updateTimeRange() {
    const preset = document.getElementById('windowPreset').value;
    const now = new Date();
    let start, end;

    const customContainer = document.getElementById('customDateContainer');
    if (preset === 'custom') {
        customContainer.style.display = 'block';
        const fromDate = document.getElementById('fromDate').value;
        const toDate = document.getElementById('toDate').value;
        if (fromDate && toDate) {
            start = new Date(fromDate);
            end = new Date(toDate);
            end.setHours(23, 59, 59, 999);
        } else {
            start = new Date(now.getTime() - 60 * 60 * 1000);
            end = now;
        }
    } else {
        customContainer.style.display = 'none';
        const minutesMap = {
            '15min': 15,
            '1hr': 60,
            '6hr': 360,
            '24hr': 1440,
            '7days': 10080,
            '1month': 43200,
            '6months': 259200
        };

        const minutes = minutesMap[preset] ?? 60;
        end = new Date();
        start = new Date(end.getTime() - minutes * 60 * 1000);
    }

    // FIX: display range label in IST
    document.getElementById('timeRange').textContent =
        `Range: ${formatIST(start.toISOString())} → ${formatIST(end.toISOString())} (IST)`;

    // FIX: corrected template literal (was broken syntax in original)
    console.log(`TimeRange sent: startTime=${start.toISOString()} endTime=${end.toISOString()}`);
    console.log('TimeRange UTC:', start.toISOString(), end.toISOString());

    loadAnalyticsData(start, end);
}

async function loadPlantIds() {
    try {
        const response = await fetch('/Dashboard/GetPlantIds');
        const plantIds = await response.json();
        const select = document.getElementById('plantSelect');

        select.innerHTML = '';
        plantIds.forEach((id, idx) => {
            const option = document.createElement('option');
            option.value = id;
            option.textContent = id;
            if (idx === 0) option.selected = true;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading plant IDs:', error);
    }
}

function populateSignalDropdowns() {
    const stage = document.getElementById('stageSelect').value;
    const keys = STAGES[stage] || [];
    const signals = keys.filter(k => k.startsWith('true_'));

    console.log('Populating dropdowns for stage:', stage, 'Signals:', signals.length);

    const signalSelector = document.getElementById('signalSelector');
    signalSelector.innerHTML = '';
    signals.forEach((sig, idx) => {
        const option = document.createElement('option');
        option.value = sig;
        option.textContent = sig.replace('true_', '');
        option.selected = (idx === 0);
        signalSelector.appendChild(option);
    });

    const distSelect = document.getElementById('distSignalSelect');
    distSelect.innerHTML = '';
    signals.forEach((sig, idx) => {
        const option = document.createElement('option');
        option.value = sig;
        option.textContent = sig.replace('true_', '');
        option.selected = (idx === 0);
        distSelect.appendChild(option);
    });

    const rollSelect = document.getElementById('rollSignalSelect');
    rollSelect.innerHTML = '';
    signals.forEach((sig, idx) => {
        const option = document.createElement('option');
        option.value = sig;
        option.textContent = sig.replace('true_', '');
        option.selected = (idx === 0);
        rollSelect.appendChild(option);
    });
}

async function loadAnalyticsData(start, end) {
    const reqId = ++analyticsReqSeq;
    const statusEl = document.getElementById('analyticsStatus');
    const plantId = document.getElementById('plantSelect')?.value;
    if (!plantId) {
        if (statusEl) statusEl.textContent = 'Select a plant.';
        return;
    }

    const url = `/api/Analytics/range?startTime=${encodeURIComponent(start.toISOString())}&endTime=${encodeURIComponent(end.toISOString())}&plantId=${encodeURIComponent(plantId)}`;

    try {
        if (statusEl) statusEl.textContent = 'Loading...';
        const response = await fetch(url, { cache: 'no-store' });
        if (reqId !== analyticsReqSeq) return;

        const rawText = await response.text();
        if (!response.ok) {
            if (statusEl) statusEl.textContent = `API error ${response.status}: ${rawText.slice(0, 160)}`;
            clearAnalytics();
            return;
        }

        let json;
        try {
            json = JSON.parse(rawText);
        } catch (e) {
            if (statusEl) statusEl.textContent = `Invalid JSON: ${rawText.slice(0, 160)}`;
            clearAnalytics();
            return;
        }

        if (reqId !== analyticsReqSeq) return;

        const arr = extractFirstArrayDeep(json);
        analyticsData = Array.isArray(arr) ? arr : [];
        const count = analyticsData.length;
        if (statusEl) statusEl.textContent = `Loaded ${count} records.`;

        if (count > 0) {
            plotsNeedRender = true;
            setTimeout(() => refreshAllCharts(), 0);
            setTimeout(resizeAllCharts, 100);
            setTimeout(resizeAllCharts, 300);
            setTimeout(resizeAllCharts, 800);
        } else {
            clearAnalytics();
        }

    } catch (err) {
        if (reqId !== analyticsReqSeq) return;
        console.error('Network/fetch error:', err);
        if (statusEl) statusEl.textContent = `Network error: ${err?.message || err}`;
        clearAnalytics();
    }
}

function updateKpiSummary(data) {
    if (!Array.isArray(data) || data.length === 0) return;

    document.getElementById('analyticsRecords').textContent = data.length.toLocaleString();

    const signalSelector = document.getElementById('signalSelector');
    const selected = [signalSelector.value].filter(Boolean);

    if (selected.length > 0) {
        const values = data
            .map(d => parseFloat(d?.payload?.[selected[0]]))
            .filter(v => Number.isFinite(v));

        if (values.length > 0) {
            const avg = values.reduce((a, b) => a + b, 0) / values.length;
            const min = Math.min(...values);
            const max = Math.max(...values);

            document.getElementById('analyticsAvg').textContent = avg.toFixed(3);
            document.getElementById('analyticsMin').textContent = min.toFixed(3);
            document.getElementById('analyticsMax').textContent = max.toFixed(3);
        }
    }
}

async function plotTrendExplorer(data) {
    console.log('[plotTrendExplorer] Called, data length:', data?.length);
    const selector = document.getElementById('signalSelector');
    const selected = selector?.value ? [selector.value] : [];
    console.log('[plotTrendExplorer] Selected signals:', selected);

    if (!selected.length) {
        showChartPlaceholder('trendChart', 'Select signals from the dropdown above');
        return;
    }

    // FIX: use toIST for chart timestamps
    const timestamps = data.map(d => toIST(d.ts));
    const traces = selected.map(sig => ({
        x: timestamps,
        y: data.map(d => {
            const v = parseFloat(d?.payload?.[sig]);
            return Number.isFinite(v) ? v : null;
        }),
        name: sig.replace('true_', ''),
        type: 'scatter',
        mode: 'lines'
    }));

    await renderPlot('trendChart', traces, {
        xaxis: { title: 'Time (IST)', gridcolor: '#D1D9E6', type: 'date' },
        yaxis: { title: 'Value', gridcolor: '#D1D9E6' },
        height: 380,
        paper_bgcolor: 'white',
        plot_bgcolor: '#F8F9FA',
        font: { color: '#2C3E50' },
        showlegend: true,
        legend: { orientation: 'h', y: -0.15 },
        margin: { t: 50, r: 20, b: 60, l: 60 }
    });
}

async function plotDistribution(data) {
    console.log('[plotDistribution] Called');
    const signal = document.getElementById('distSignalSelect').value;
    if (!signal) {
        showChartPlaceholder('distributionChart', 'Select a signal');
        document.getElementById('percentileTable').innerHTML = '';
        return;
    }

    const values = data
        .map(d => parseFloat(d?.payload?.[signal]))
        .filter(v => Number.isFinite(v));

    if (!values.length) {
        showChartPlaceholder('distributionChart', 'No data');
        document.getElementById('percentileTable').innerHTML = '';
        return;
    }

    const bins = parseInt(document.getElementById('binsSlider').value, 10) || 30;
    const vmin = Math.min(...values);
    const vmax = Math.max(...values);
    const size = (vmax - vmin) === 0 ? 1 : (vmax - vmin) / bins;

    const trace = {
        x: values,
        type: 'histogram',
        xbins: { start: vmin, end: vmax, size }
    };

    await renderPlot('distributionChart', [trace], {
        title: `${signal.replace('true_', '')} Distribution`,
        xaxis: { title: 'Value', gridcolor: '#D1D9E6' },
        yaxis: { title: 'Count', gridcolor: '#D1D9E6' },
        height: 375,
        paper_bgcolor: 'white',
        plot_bgcolor: '#F8F9FA',
        font: { color: '#2C3E50' },
        margin: { t: 60, r: 20, b: 60, l: 60 }
    });

    const sorted = [...values].sort((a, b) => a - b);
    const n = sorted.length;
    let html = '<table class="table table-sm"><thead><tr><th>Percentile</th><th>Value</th></tr></thead><tbody>';
    [1, 5, 10, 25, 50, 75, 90, 95, 99].forEach(p => {
        const idx = Math.min(n - 1, Math.floor(n * p / 100));
        html += `<tr><td>P${p}</td><td>${sorted[idx].toFixed(3)}</td></tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('percentileTable').innerHTML = html;
}

async function plotRollingStats(data) {
    console.log('[plotRollingStats] Called');
    const signal = document.getElementById('rollSignalSelect')?.value;
    if (!signal) {
        showChartPlaceholder('rollingChart', 'Select a signal');
        return;
    }

    let windowSize = 10;
    let showMean = document.getElementById('showRollMean')?.checked ?? true;
    let showStd = document.getElementById('showRollStd')?.checked ?? true;
    let showSlope = document.getElementById('showRollSlope')?.checked ?? true;

    const slider = document.getElementById('rollWindowSlider');
    if (slider) windowSize = parseInt(slider.value, 10) || 10;

    // FIX: use toIST for chart timestamps
    const timestamps = data.map(d => toIST(d.ts));
    const values = data.map(d => {
        const v = parseFloat(d?.payload?.[signal]);
        return Number.isFinite(v) ? v : null;
    });

    let traces = [{
        x: timestamps,
        y: values,
        name: 'Original',
        type: 'scatter',
        mode: 'lines'
    }];

    let layout = {
        title: `${signal.replace('true_', '')} - Rolling Statistics (Window: ${windowSize})`,
        xaxis: { title: 'Time (IST)', gridcolor: '#D1D9E6', type: 'date' },
        yaxis: {
            title: 'Value',
            gridcolor: '#D1D9E6',
            domain: [0, 1]
        },
        height: 360,
        paper_bgcolor: 'white',
        plot_bgcolor: '#F8F9FA',
        font: { color: '#2C3E50' },
        showlegend: true,
        legend: { orientation: 'h', y: -0.2 },
        margin: { t: 60, r: 60, b: 80, l: 60 }
    };

    let yaxisCount = 1;

    if (showMean) {
        traces.push({
            x: timestamps,
            y: rollingMean(values, windowSize),
            name: 'Rolling Mean',
            type: 'scatter',
            mode: 'lines'
        });
    }

    if (showStd) {
        try {
            traces.push({
                x: timestamps,
                y: rollingStd(values, windowSize),
                name: 'Rolling Std',
                type: 'scatter',
                mode: 'lines',
                yaxis: 'y2'
            });

            layout.yaxis2 = {
                title: 'Std Dev',
                overlaying: 'y',
                side: 'right',
                anchor: 'free',
                position: 0.88 - (showSlope ? 0.08 : 0),
                gridcolor: '#D1D9E6',
                showgrid: false
            };
            yaxisCount++;
        } catch (e) {
            console.warn('[plotRollingStats] Failed to add Rolling Std → skipping', e);
            showStd = false;
        }
    }

    if (showSlope) {
        try {
            traces.push({
                x: timestamps,
                y: rollingSlope(values, windowSize),
                name: 'Rolling Slope',
                type: 'scatter',
                mode: 'lines',
                line: { color: '#e74c3c', dash: 'dash' },
                yaxis: 'y3'
            });

            layout.yaxis3 = {
                title: 'Slope',
                overlaying: 'y',
                side: 'right',
                anchor: 'free',
                position: 0.95,
                gridcolor: '#D1D9E6',
                showgrid: false,
                zeroline: false
            };
            yaxisCount++;
        } catch (e) {
            console.warn('[plotRollingStats] Failed to add Rolling Slope → skipping', e);
            showSlope = false;
        }
    }

    layout.margin.r = 60 + (yaxisCount - 1) * 40;

    await renderPlot('rollingChart', traces, layout);
}

function clearAnalytics() {
    document.getElementById('analyticsRecords').textContent = '0';
    document.getElementById('analyticsAvg').textContent = '—';
    document.getElementById('analyticsMin').textContent = '—';
    document.getElementById('analyticsMax').textContent = '—';

    showChartPlaceholder('trendChart', 'No data available');
    showChartPlaceholder('distributionChart', 'No data available');
    showChartPlaceholder('rollingChart', 'No data available');
    document.getElementById('percentileTable').innerHTML = '';

    ['trendChart', 'distributionChart', 'rollingChart'].forEach(id => {
        const ctx = prepareChartContainer(id);
        if (ctx) Plotly.purge(ctx.host);
    });
}

// Helper functions
function fmt(v, d = 3) { return v == null ? '—' : parseFloat(v).toFixed(d); }
function onBadge(v) { return parseInt(v) === 2 ? '<span class="badge ok">ON</span>' : '<span class="badge bad">OFF</span>'; }
function valveBadge(v) { return parseInt(v) === 2 ? '<span class="badge ok">OPEN</span>' : '<span class="badge bad">CLOSED</span>'; }

function setupTabListeners() {
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', function (event) {
            if (event.target.id === 'analytics-tab') {
                console.log("Analytics tab shown → scheduling render/resize");
                whenTabIsReady(() => {
                    console.log("Tab ready - size check:", document.querySelector('#analytics-panel').offsetHeight);
                    if (analyticsData && analyticsData.length > 0) {
                        console.log("Data exists → full refresh on tab show");
                        refreshAllCharts();
                    }
                    resizeAllCharts();
                    setTimeout(resizeAllCharts, 150);
                    setTimeout(resizeAllCharts, 450);
                    setTimeout(resizeAllCharts, 800);
                }, 150);
            }
        });
    });
    window.addEventListener('resize', resizeAllCharts);
}
