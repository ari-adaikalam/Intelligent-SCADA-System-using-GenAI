// dashboard.js - SIMPLIFIED VERSION with placeholder fix
// No Section F (Actuator Analytics)

let connection = null;
let analyticsData = null;
let recentData = [];
let analyticsReqSeq = 0;
let windowDebounceTimer = null;
const analyticsCache = new Map();
let plotsNeedRender = true;  // set to true when data loads or tab shown

const STAGES = {
    "Stage 1 - Intake": ["true_FIT101", "true_LIT101", "MV101", "P101"],
    "Stage 2 - Pre-treatment": ["true_FIT201", "true_AIT201", "true_AIT202", "true_AIT203", "MV201", "P201", "P203", "P205"],
    "Stage 3 - Ultrafiltration (UF)": ["true_FIT301", "true_LIT301", "true_DPIT301", "MV301", "MV302", "MV303", "MV304", "P302"],
    "Stage 4 - Dechlorination (UV)": ["true_FIT401", "true_LIT401", "true_AIT401", "true_AIT402", "UV401", "P402", "P403"],
    "Stage 5 - Reverse Osmosis (RO)": ["true_FIT501", "true_PIT501", "true_AIT501", "P501"]
};

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
        const tabPane = document.querySelector('#analytics');
        if (tabPane && tabPane.offsetWidth > 50 && tabPane.offsetHeight > 50) {
            callback();
        } else {
            setTimeout(check, 80);
        }
    };
    setTimeout(check, delay);
}

function toLocalIso(dt) {
    const local = new Date(dt.getTime() - dt.getTimezoneOffset() * 60000)
        .toISOString()
        .slice(0, 19);
    return local;
}

function normalizeAnalyticsResponse(json) {
    if (Array.isArray(json)) return json;
    if (json && Array.isArray(json.data)) return json.data;
    if (json && Array.isArray(json.records)) return json.records;
    if (json && Array.isArray(json.items)) return json.items;
    return [];
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

    // ✅ IMPORTANT: explicit height so offsetHeight is never 0
    host.style.cssText = `
        position: relative;
        z-index: 1;
        width: 100%;
        height: ${desiredHeight}px;
    `;

    return { container, host };
}

// REPLACE these two functions only
function showChartPlaceholder(containerId, text = 'No data available') {
    const container = document.getElementById(containerId);
    if (!container) return;

    hideChartPlaceholder(containerId); // prevent duplicates

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

    // Remove ALL placeholders inside this container (even nested)
    const placeholders = container.querySelectorAll('.chart-placeholder');
    placeholders.forEach(ph => {
        ph.remove();
        console.log(`[${containerId}] Removed placeholder from DOM`);
    });

    // Extra safety: remove any text-muted "No data" divs that might be custom
    const noDataDivs = container.querySelectorAll('.p-4.text-center.text-muted');
    noDataDivs.forEach(div => {
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

    // If still 0 for any reason, force it once
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

        // Use plot-host if you created it, else fallback to container
        const host = container.querySelector('.plot-host') || container;

        const w = host.offsetWidth;
        const h = host.offsetHeight;

        // If we have data and plots are pending and the div is visible -> replot
        if (analyticsData?.length > 0 && (plotsNeedRender || id === 'trendChart' || id === 'rollingChart') && w > 50 && h > 50) {
            console.log(`[${id}] Forcing re-plot (trend/rolling special case)`);
            hideChartPlaceholder(id);
            fn(analyticsData);
        }
      

        // If plot already exists -> resize safely
        if (host.classList.contains('js-plotly-plot') || host._fullLayout) {
            console.log(`[${id}] Resizing existing plot`);
            try { Plotly.Plots.resize(host); } catch (e) { console.warn('resize failed', e); }
        }
    });
}
function rollingMean(values, windowSize) {
    const out = new Array(values.length).fill(null);
    let sum = 0, count = 0;
    const q = []; // store last window values (including nulls)

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
    const q = []; // window of {index, value}

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
                const x = p.idx - finite[0].idx; // relative position 0..n-1
                sumX += x;
                sumY += p.val;
                sumXY += x * p.val;
                sumX2 += x * x;
            });

            const denom = n * sumX2 - sumX * sumX;
            if (Math.abs(denom) < 1e-10) continue; // avoid division by zero

            const slope = (n * sumXY - sumX * sumY) / denom;
            out[i] = slope;
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

    plotsNeedRender = false;   // ✅ ADD THIS
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

    document.getElementById('lastUpdate').textContent = new Date(latest.ts).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata'});
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
    const timestamps = recentData.map(d => new Date(d.ts));
    
    Plotly.newPlot(id, [{
        x: timestamps, y: values, type: 'scatter', mode: 'lines',
        line: { color: '#4A90E2', width: 2 }, showlegend: false
    }], {
        margin: { t: 5, b: 20, l: 30, r: 5 }, height: 90,
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: '#F8F9FA',
        xaxis: { visible: false }, yaxis: { visible: true, gridcolor: '#D1D9E6', zeroline: false }
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
        issueClass = 'ml-status-monitor';     // ✅ blue monitor style
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
                    'ml-status-monitor'; // ✅ ANOMALY goes here

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

    // Single row, cards stretch to fill available width.
    // If too many cards, horizontal scroll appears (still one row).
    let html = `
      <div class="attention-row">
    `;

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
// ANALYTICS DASHBOARD - SIMPLIFIED
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

    
    document.getElementById('timeRange').textContent = `Range: ${start.toLocaleString()} → ${end.toLocaleString()}`;
    console.log("TimeRange local:", start, end);
    console.log("TimeRange sent:", toLocalIso(start), toLocalIso(end));
    console.log("TimeRange UTC:", start.toISOString(), end.toISOString());

    loadAnalyticsData(start, end);
}

async function loadPlantIds() {
    try {
        const response = await fetch('/Dashboard/GetPlantIds');
        const plantIds = await response.json();
        const select = document.getElementById('plantSelect');

        select.innerHTML = ''; // clear
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
    
    // Signal multiselect
    const signalSelector = document.getElementById('signalSelector');
    signalSelector.innerHTML = '';
    signals.forEach((sig, idx) => {
        const option = document.createElement('option');
        option.value = sig;
        option.textContent = sig.replace('true_', '');
        option.selected = (idx == 0); // Auto-select first 3
        signalSelector.appendChild(option);
    });
    
    // Distribution signal (single select)
    const distSelect = document.getElementById('distSignalSelect');
    distSelect.innerHTML = '';
    signals.forEach((sig, idx) => {
        const option = document.createElement('option');
        option.value = sig;
        option.textContent = sig.replace('true_', '');
        option.selected = (idx === 0); // Auto-select first
        distSelect.appendChild(option);
    });
    
    // Rolling signal (single select)
    const rollSelect = document.getElementById('rollSignalSelect');
    rollSelect.innerHTML = '';
    signals.forEach((sig, idx) => {
        const option = document.createElement('option');
        option.value = sig;
        option.textContent = sig.replace('true_', '');
        option.selected = (idx === 0); // Auto-select first
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

    const url = `/api/Analytics/range?startTime=${encodeURIComponent(toLocalIso(start))}&endTime=${encodeURIComponent(toLocalIso(end))}&plantId=${encodeURIComponent(plantId)}`;

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

            // ✅ ALWAYS refresh KPI + charts after data arrives
            // Plotly will handle hidden-size via your renderPlot() guard.
            setTimeout(() => refreshAllCharts(), 0);

            // keep your resize nudges (optional)
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


async function refreshAllCharts() {
    if (!Array.isArray(analyticsData) || analyticsData.length === 0) {
        clearAnalytics();
        return;
    }

    updateKpiSummary(analyticsData);

    await plotTrendExplorer(analyticsData);
    await plotDistribution(analyticsData);
    await plotRollingStats(analyticsData);
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
    console.log('[plotTrendExplorer] selector exists?', !!selector);
    const selected = selector?.value ? [selector.value] : [];
    console.log('[plotTrendExplorer] Selected signals:', selected, 'count:', selected.length);

    if (!selected.length) {
        console.log('[plotTrendExplorer] No signals selected → placeholder');
        showChartPlaceholder('trendChart', 'Select signals from the dropdown above');
        return;
    }
    const timestamps = data.map(d => new Date(d.ts));
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
        xaxis: { title: 'Time', gridcolor: '#D1D9E6' },
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
    console.log('[plotDistribution] Selected signal:', signal);
    if (!signal) {
        console.log('[plotDistribution] No signal selected → placeholder');
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

    const bins = parseInt(document.getElementById('binsSlider').value, 10) || 30;  // ← ADD THIS LINE (fallback to 30)

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

    // Percentiles (unchanged)
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
        console.warn('[plotRollingStats] No signal selected');
        showChartPlaceholder('rollingChart', 'Select a signal');
        return;
    }

    let windowSize = 10;
    let showMean = document.getElementById('showRollMean')?.checked ?? true;
    let showStd = document.getElementById('showRollStd')?.checked ?? true;
    let showSlope = document.getElementById('showRollSlope')?.checked ?? true;

    const slider = document.getElementById('rollWindowSlider');
    if (slider) windowSize = parseInt(slider.value, 10) || 10;

    console.log('[plotRollingStats] signal:', signal, 'window:', windowSize,
        'mean:', showMean, 'std:', showStd, 'slope:', showSlope);

    const timestamps = data.map(d => new Date(d.ts));
    const values = data.map(d => {
        const v = parseFloat(d?.payload?.[signal]);
        return Number.isFinite(v) ? v : null;
    });

    // ──────────────────────────────────────────────
    // 1. Base traces & layout (always render this)
    // ──────────────────────────────────────────────
    let traces = [{
        x: timestamps,
        y: values,
        name: 'Original',
        type: 'scatter',
        mode: 'lines'
    }];

    let layout = {
        title: `${signal.replace('true_', '')} - Rolling Statistics (Window: ${windowSize})`,
        xaxis: { title: 'Time', gridcolor: '#D1D9E6' },
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

    // ──────────────────────────────────────────────
    // 2. Try to add extras one by one
    // ──────────────────────────────────────────────
    let yaxisCount = 1; // main y is 1

    // Rolling Mean (uses same y-axis as original)
    if (showMean) {
        traces.push({
            x: timestamps,
            y: rollingMean(values, windowSize),
            name: 'Rolling Mean',
            type: 'scatter',
            mode: 'lines'
        });
    }

    // Rolling Std (needs yaxis2)
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
            showStd = false; // don't try again
        }
    }

    // Rolling Slope (needs yaxis3)
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

    // Adjust right margin based on how many y-axes we actually have
    layout.margin.r = 60 + (yaxisCount - 1) * 40;

    // ──────────────────────────────────────────────
    // 3. Render the chart (base + whatever extras survived)
    // ──────────────────────────────────────────────
    await renderPlot('rollingChart', traces, layout);

    // If nothing extra was added successfully, at least original should show
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
                    console.log("Tab ready - size check:", document.querySelector('#analytics').offsetHeight);
                    if (analyticsData && analyticsData.length > 0) {
                        console.log("Data exists → full refresh on tab show");
                        refreshAllCharts();          // ← re-plot everything
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