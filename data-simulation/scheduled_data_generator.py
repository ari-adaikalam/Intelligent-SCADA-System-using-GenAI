"""
Same physics engine as plant_simulator.py, but instead of leaving which
component degrades or has an anomaly up to chance, this schedules every
event up front so each component and anomaly type gets guaranteed,
balanced coverage. This is the dataset the models actually train on.

Left purely random, some rare component or anomaly combinations barely
show up across even a 200 day run, not enough for a classifier to learn
them. This script builds an explicit event list (N degradation cycles
per component, M anomaly episodes per component and type), shuffles it,
and plays it back with short gaps in between.

Only three things differ from plant_simulator.py: which component
degrades next is scheduled here, not random, the gaps between events are
short (10 to 60 minutes) instead of realistic hours, and there is no
maintenance downtime phase, a fault goes straight to startup. Physics,
state machine shape, and noise model are otherwise identical, on purpose,
so a model trained here transfers to the simulator's more realistic data.
"""

import argparse
import csv
import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from paths import RAW_BASELINE_CSV, TRAINING_DATA_FILE

STEP_SEC = 10
START_TIMESTAMP = datetime(2024, 1, 1, 0, 0, 0)

INPUT_CSV = RAW_BASELINE_CSV
OUTPUT_CSV = TRAINING_DATA_FILE

# ============================================================
# COVERAGE TARGETS, THIS IS THE MAIN DIFFERENCE FROM THE SIMULATOR
# ============================================================

CYCLES_PER_COMPONENT = 5          # each component gets 5 degradation cycles
ANOMALY_EPISODES_PER_TYPE = 120   # each component/anomaly type pair gets 120 episodes

# ============================================================
# HOW FAST EACH COMPONENT WEARS OUT (same as the simulator)
# ============================================================
COMPONENT_DEGRADATION = {
    'P101': {'micro_wear_per_hour': (0.001, 0.003), 'accel_wear_per_hour': (0.5, 1.0), 'fault_threshold': (42, 44)},
    'P201': {'micro_wear_per_hour': (0.001, 0.003), 'accel_wear_per_hour': (0.5, 1.0), 'fault_threshold': (43, 45)},
    'P203': {'micro_wear_per_hour': (0.001, 0.003), 'accel_wear_per_hour': (0.5, 1.0), 'fault_threshold': (45, 47)},
    'P205': {'micro_wear_per_hour': (0.001, 0.003), 'accel_wear_per_hour': (0.5, 1.0), 'fault_threshold': (47, 49)},
    'P302': {'micro_wear_per_hour': (0.001, 0.003), 'accel_wear_per_hour': (0.5, 1.0), 'fault_threshold': (48, 50)},
    'P402': {'micro_wear_per_hour': (0.001, 0.003), 'accel_wear_per_hour': (0.5, 1.0), 'fault_threshold': (44, 46)},
    'P403': {'micro_wear_per_hour': (0.001, 0.003), 'accel_wear_per_hour': (0.5, 1.0), 'fault_threshold': (41, 43)},
    'P501': {'micro_wear_per_hour': (0.001, 0.003), 'accel_wear_per_hour': (0.5, 1.0), 'fault_threshold': (46, 48)},

    'MV101': {'micro_wear_per_hour': (0.003, 0.005), 'accel_wear_per_hour': (0.3, 0.6), 'fault_threshold': (52, 54)},
    'MV304': {'micro_wear_per_hour': (0.003, 0.005), 'accel_wear_per_hour': (0.3, 0.6), 'fault_threshold': (55, 57)},
}

# ============================================================
# TIMING, DIFFERENCES 2 AND 3 FROM THE SIMULATOR
# ============================================================

NORMAL_GAP_HOURS_RANGE = (0.17, 1.0)  # short gaps (10 to 60 minutes), not long idle stretches

FAULT_DURATION_HOURS_RANGE = (8, 15)
# No downtime phase here, a fault goes straight to startup.
STARTUP_DURATION_MINUTES = 30
STARTUP_BLEND = 0.03

ANOMALY_SEVERITY_RANGE = (0.04, 0.10)
ANOMALY_DURATION_MIN = int((5 * 60) / STEP_SEC)
ANOMALY_DURATION_MAX = int((45 * 60) / STEP_SEC)

# ============================================================
# PHYSICS CONSTANTS (same shape as the simulator, noise tuned a touch
# higher here so the classification task stays non trivial)
# ============================================================

AMBIENT_TEMP = 28.0
TAU_HEAT = 900.0
TAU_COOL = 1800.0

TEMP_RANGE = (28.0, 60.0)
CURR_MAX = 8.0
VIB_MAX = 3.0

TEMP_NOISE_STD = 0.02
CURR_NOISE_STD = 0.01
VIB_NOISE_STD = 0.01

RUN_SENSOR_NOISE_REL_STD = 0.005
RUN_SENSOR_NOISE_ABS_STD = 0.001
RUN_SENSOR_NOISE_APPLY_TAG_PREFIX = ("FIT", "PIT", "DPIT", "LIT", "AIT")

ANOM_MIN_Z = 2.0
FAULT_MIN_Z = 10.0
DEGRADE_MIN_Z_START = 0.4
DEGRADE_MIN_Z_END = 4.0

CLAMP_TO_P05_P995 = False
P995 = 99.5

episode_wear_rate = {}
episode_start_step = {}
episode_h0 = {}
episode_thr = {}
episode_expected_steps = {}

# ============================================================
# WHICH SENSORS BELONG TO WHICH COMPONENT (same as the simulator)
# ============================================================

COMP_TO_SENSORS = {
    "P101": ["FIT101"],
    "MV101": ["LIT101"],
    "P201": ["AIT201", "FIT201"],
    "P203": ["AIT202", "FIT201"],
    "P205": ["AIT203", "FIT201"],
    "P302": ["FIT301", "DPIT301"],
    "MV304": ["LIT301"],
    "P402": ["FIT401", "AIT401", "LIT401"],
    "P403": ["AIT402"],
    "P501": ["FIT501", "PIT501", "AIT501"],
}

SHARED_SENSORS = {"FIT201": ["P201", "P203", "P205"]}
EVENT_BLACKLIST = {"MV201", "MV301", "MV302", "MV303"}

np.random.seed(42)

try:
    from tqdm import tqdm
    USE_TQDM = True
except Exception:
    USE_TQDM = False


# ============================================================
# TAG HELPERS
# ============================================================

def episode_progress01(comp: str, step_idx: int) -> float:
    if comp not in episode_start_step:
        return 0.0
    steps = episode_expected_steps.get(comp, None)
    if steps is None or steps <= 1:
        return 0.0
    return float(np.clip((step_idx - episode_start_step[comp]) / steps, 0.0, 1.0))


def is_sensor(col):
    s = str(col).strip().upper()
    return bool(re.fullmatch(r"(FIT|LIT|AIT|PIT|DPIT)\d+", s))


def is_pump(col):
    s = str(col).strip().upper()
    return bool(re.match(r"^P[-_]?(\d{3})\b", s))


def is_valve(col):
    s = str(col).strip().upper()
    return bool(re.match(r"^MV[-_]?(\d{3})\b", s))


def stage_digit_from_tag(tag: str):
    m = re.search(r"(\d)", str(tag))
    return m.group(1) if m else None


def normalize_header(s: str) -> str:
    s = str(s)
    s = s.replace("﻿", "").replace("​", "").replace("‌", "").replace("‍", "")
    s = s.replace("\xa0", " ")
    s = s.strip()
    s = re.sub(r"\s+", "", s)
    return s.upper()


def component_sensor_tags(comp: str):
    comp = str(comp).strip().upper()
    sensors = COMP_TO_SENSORS.get(comp, [])
    return [t for t in sensors if t not in SHARED_SENSORS and t in sensor_tags]


def _osc(step_idx: int, period_steps: int) -> float:
    period_steps = max(2, int(period_steps))
    w = 2.0 * np.pi / period_steps
    return float(np.sin(w * step_idx))


def _family_prefix(tag: str) -> str:
    m = re.match(r"(FIT|PIT|DPIT|LIT|AIT)", tag)
    return m.group(1) if m else ""


def can_start_anomaly_now(comp: str) -> bool:
    """Anomalies only fire when nothing else is already happening."""
    if system_status != "RUN":
        return False
    if current_fault is not None:
        return False
    if degrading_component is not None:
        return False
    if component_status.get(comp, "HEALTHY") != "HEALTHY":
        return False
    if anomaly is not None:
        return False
    return True


# ============================================================
# LOAD THE BASELINE DATA
# ============================================================

df_clean = pd.read_csv(INPUT_CSV, low_memory=False)
df_clean = df_clean.loc[:, ~df_clean.columns.astype(str).str.contains("^Unnamed")]
df_clean.columns = [normalize_header(c) for c in df_clean.columns]

ALLOWED_SENSOR_TAGS = sorted({t for v in COMP_TO_SENSORS.values() for t in v})
sensor_tags = [c for c in df_clean.columns if is_sensor(c) and c in ALLOWED_SENSOR_TAGS]

AUDIT_ACTUATORS = set(COMP_TO_SENSORS.keys()) | set(EVENT_BLACKLIST)
pump_tags = [c for c in df_clean.columns if is_pump(c) and c in AUDIT_ACTUATORS]
valve_tags = [c for c in df_clean.columns if is_valve(c) and c in AUDIT_ACTUATORS]

components = [c for c in (pump_tags + valve_tags)
              if c in COMP_TO_SENSORS and c not in EVENT_BLACKLIST]

# ============================================================
# BASELINE STATISTICS
# ============================================================

baseline_stats = {}
robust_stats = {}

for tag in sensor_tags:
    s = pd.to_numeric(df_clean[tag], errors="coerce").dropna().to_numpy(dtype=float)
    if len(s):
        p01 = np.percentile(s, 1)
        p05 = np.percentile(s, 5)
        p95 = np.percentile(s, 95)
        p995 = np.percentile(s, P995)
        med = float(np.median(s))
        mad = float(np.median(np.abs(s - med)))

        baseline_stats[tag] = {
            "p01": float(p01), "p05": float(p05), "p90": float(np.percentile(s, 90)),
            "p95": float(p95), "p99": float(np.percentile(s, 99)),
            "median": med, "mad": max(mad, 1e-9),
        }

        spread = max(1e-9, p95 - p05)
        mad_eff = max(mad, 0.10 * spread)
        robust_stats[tag] = {"median": med, "mad": mad_eff, "p05": p05, "p995": p995}


def norm_from_stats(tag: str, x: float) -> float:
    st = baseline_stats.get(tag)
    if st is None:
        return 0.0
    lo, hi = st["p05"], st["p95"]
    if not np.isfinite(lo) or not np.isfinite(hi) or (hi - lo) < 1e-12:
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


def clamp_tag(tag: str, val: float) -> float:
    if not CLAMP_TO_P05_P995:
        return float(val)
    rs = robust_stats.get(tag)
    if not rs:
        return float(val)
    return float(np.clip(val, rs["p05"], rs["p995"]))


# ============================================================
# WHICH SENSORS BEST TRACK EACH PUMP'S LOAD
# ============================================================

def topk_by_variance(df: pd.DataFrame, cols, k):
    vars_ = []
    for c in cols:
        arr = pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
        v = np.nanvar(arr)
        if np.isfinite(v):
            vars_.append((v, c))
    vars_.sort(reverse=True)
    return [c for _, c in vars_[:k]]


def stage_candidates(stage: str):
    flow = [c for c in sensor_tags if re.fullmatch(rf"FIT{stage}\d\d", str(c))]
    press = [c for c in sensor_tags if re.fullmatch(rf"(PIT|DPIT){stage}\d\d", str(c))]
    return flow, press


TOP_K_FLOW = 2
TOP_K_PRESS = 2

pump_load_sources = {}
for p in pump_tags:
    stage = stage_digit_from_tag(p)
    flow_cands, press_cands = stage_candidates(stage) if stage else ([], [])
    flows = topk_by_variance(df_clean, flow_cands, TOP_K_FLOW)
    press = topk_by_variance(df_clean, press_cands, TOP_K_PRESS)
    pump_load_sources[p] = {"stage": stage, "flows": flows, "press": press}


def compute_pump_load_from(prefix: str, pump_tag: str, value_map: dict, on: int) -> float:
    src = pump_load_sources.get(pump_tag, {})
    cols = src.get("flows", []) + src.get("press", [])
    if not cols or on <= 0:
        return 0.0
    parts = []
    for col in cols:
        key = f"{prefix}{col}"
        if key in value_map:
            parts.append(norm_from_stats(col, value_map[key]))
    if not parts:
        return 0.0
    return float(np.clip(np.mean(parts), 0.0, 1.0))


# ============================================================
# BASELINE REPLAY
# ============================================================

class Baseline:
    def __init__(self, df):
        self.df = df.reset_index(drop=True)
        self.idx = np.random.randint(0, max(1, len(df) - 1000))

    def step(self):
        row = self.df.iloc[self.idx]
        self.idx = (self.idx + 1) % len(self.df)
        expected = {f"expected_{t}": float(row[t]) for t in sensor_tags}
        actuators = {t: int(row[t]) for t in pump_tags + valve_tags}
        return expected, actuators


baseline = Baseline(df_clean)

# ============================================================
# COMPONENT STATE
# ============================================================

health = {c: 100.0 for c in components}
component_status = {c: "HEALTHY" for c in components}
system_status = "RUN"
degrading_component = None

fault_thresholds = {}
for comp in components:
    if comp in COMPONENT_DEGRADATION:
        lo, hi = COMPONENT_DEGRADATION[comp]['fault_threshold']
        fault_thresholds[comp] = float(np.random.uniform(lo, hi))
    else:
        fault_thresholds[comp] = 60.0

current_fault = None
anomaly = None


def get_anomaly_types_for_component(comp: str):
    if is_pump(comp):
        return ["cavitation", "flow_oscillation"]
    elif is_valve(comp):
        return ["valve_chatter", "level_jitter"]
    return []


# ============================================================
# THE EVENT SCHEDULE, THIS IS THE MAIN DIFFERENCE FROM THE SIMULATOR
# ============================================================

def build_event_schedule():
    """Schedule CYCLES_PER_COMPONENT degradation cycles per component and
    ANOMALY_EPISODES_PER_TYPE anomaly episodes per component/type pair,
    then shuffle so they're spread evenly through the run."""
    events = []

    for comp in components:
        for cycle in range(CYCLES_PER_COMPONENT):
            params = COMPONENT_DEGRADATION[comp]
            threshold = np.random.uniform(*params['fault_threshold'])
            events.append({
                "type": "DEGRADATION_CYCLE",
                "component": comp,
                "fault_threshold": threshold,
            })

    for comp in components:
        anom_types = get_anomaly_types_for_component(comp)
        for anom_type in anom_types:
            for _ in range(ANOMALY_EPISODES_PER_TYPE):
                events.append({
                    "type": "ANOMALY",
                    "component": comp,
                    "subtype": anom_type,
                    "severity": np.random.uniform(*ANOMALY_SEVERITY_RANGE),
                    "duration_steps": np.random.randint(ANOMALY_DURATION_MIN, ANOMALY_DURATION_MAX),
                })

    np.random.shuffle(events)
    return events


EVENT_SCHEDULE = build_event_schedule()

print("Event schedule built:")
print(f"   Total events: {len(EVENT_SCHEDULE)}")
print(f"   Degradation cycles: {sum(1 for e in EVENT_SCHEDULE if e['type'] == 'DEGRADATION_CYCLE')}")
print(f"   Anomaly episodes: {sum(1 for e in EVENT_SCHEDULE if e['type'] == 'ANOMALY')}")


# ============================================================
# HEALTH UPDATE (same logic as the simulator)
# ============================================================

def update_health(dt_hours: float):
    global health
    for comp in components:
        if comp not in COMPONENT_DEGRADATION:
            continue
        params = COMPONENT_DEGRADATION[comp]

        if component_status[comp] == "HEALTHY":
            lo, hi = params['micro_wear_per_hour']
            wear_rate = np.random.uniform(lo, hi)
            health[comp] = max(0.0, health[comp] - wear_rate * dt_hours)

        elif component_status[comp] == "DEGRADING":
            wear_rate = episode_wear_rate.get(comp)
            if wear_rate is None:
                lo, hi = params["accel_wear_per_hour"]
                wear_rate = float(np.random.uniform(lo, hi))
                episode_wear_rate[comp] = wear_rate
            health[comp] = max(0.0, health[comp] - wear_rate * dt_hours)


def check_for_fault():
    """Move DEGRADING to FAULTED once health reaches this episode's threshold."""
    global current_fault, system_status, anomaly

    if degrading_component is None:
        return False

    if health[degrading_component] <= fault_thresholds[degrading_component]:
        component_status[degrading_component] = "FAULTED"
        system_status = "FAULT"
        anomaly = None
        episode_wear_rate.pop(degrading_component, None)
        episode_start_step.pop(degrading_component, None)
        episode_h0.pop(degrading_component, None)
        episode_thr.pop(degrading_component, None)
        episode_expected_steps.pop(degrading_component, None)

        severity = int(100 * (1 - health[degrading_component] / 100.0))
        current_fault = {"component": degrading_component, "severity": severity}
        return True

    return False


# ============================================================
# MOTOR PHYSICS
# ============================================================

motor_temp_true = {p: AMBIENT_TEMP for p in pump_tags}


def motor_temp(on, load, prev, health_pct, status):
    alpha = 1 - np.exp(-STEP_SEC / (TAU_HEAT if on else TAU_COOL))

    if status == "FAULTED":
        target = TEMP_RANGE[1] * np.random.uniform(0.75, 0.92)
    elif status == "DEGRADING":
        deg_factor = (100 - health_pct) / 100.0
        wear_heat = deg_factor * 10.0
        min_load = max(load, 0.35)
        target = AMBIENT_TEMP + (35.0 * min_load if on else 0.0) + wear_heat + (6.0 * deg_factor)
    else:
        target = AMBIENT_TEMP + (35.0 * load if on else 0.0)

    new_temp = prev + alpha * (target - prev) + np.random.normal(0, TEMP_NOISE_STD)
    return float(np.clip(new_temp, *TEMP_RANGE))


def motor_current(on, load, health_pct, status, noise_std=CURR_NOISE_STD):
    if on <= 0:
        return 0.0

    base_amps = (1.0 + 6.0 * load)

    if status == "FAULTED":
        amps = CURR_MAX * np.random.uniform(0.65, 0.85)
    elif status == "DEGRADING":
        deg_factor = (100 - health_pct) / 100.0
        amps = base_amps * (1.0 + 0.5 * deg_factor) + (0.3 * deg_factor)
    else:
        amps = base_amps

    return float(np.clip(amps + np.random.normal(0, noise_std * 2.0), 0.0, CURR_MAX))


def motor_vibration(on, load, health_pct, status, noise_std=VIB_NOISE_STD):
    if on <= 0:
        return 0.0

    base_vib = (0.6 + 1.2 * load)

    if status == "FAULTED":
        vib = VIB_MAX * np.random.uniform(0.65, 0.85)
    elif status == "DEGRADING":
        deg_factor = (100 - health_pct) / 100.0
        vib = base_vib * (1.0 + 1.0 * deg_factor) + (0.2 * deg_factor)
    else:
        vib = base_vib

    return float(np.clip(vib + np.random.normal(0, noise_std), 0.0, VIB_MAX))


# ============================================================
# DEGRADATION PHYSICS (same shape as the simulator, softer coefficients)
# ============================================================

def apply_degradation_physics(tag: str, baseline_val: float, comp: str,
                               health_pct: float, step_idx: int) -> float:
    health_factor = (100.0 - health_pct) / 100.0
    prog01 = episode_progress01(comp, step_idx)
    deg_factor = float(np.clip(0.5 * health_factor + 0.5 * prog01, 0.0, 1.0))

    t_prefix = _family_prefix(tag)
    st = baseline_stats.get(tag, {})
    med = float(st.get("median", baseline_val))
    p05 = float(st.get("p05", med))
    p95 = float(st.get("p95", med))
    spread = max(1e-9, p95 - p05)

    val = baseline_val

    if is_pump(comp):
        if t_prefix == "FIT":
            base_ref = 0.05 * baseline_val + 0.95 * med
            monotone_drop = (prog01 ** 1.2) * (0.60 * spread)
            health_drop = health_factor * (0.15 * spread)
            fit_noise = np.random.normal(0.0, 0.008 * spread)
            val = base_ref - (monotone_drop + health_drop) + fit_noise

        elif t_prefix in ("PIT", "DPIT"):
            rise = deg_factor * (0.05 * abs(med) + 0.08 * spread)
            val = baseline_val + rise + np.random.normal(0.0, 0.015 * spread)

        elif t_prefix == "AIT":
            base_ref = 0.03 * baseline_val + 0.97 * med
            rise = (prog01 ** 1.2) * (0.12 * spread) + health_factor * (0.06 * spread)
            ait_noise = np.random.normal(0.0, 0.012 * spread)
            val = base_ref + rise + ait_noise

        elif t_prefix == "LIT":
            drop = deg_factor * (0.05 * spread)
            val = baseline_val - drop + np.random.normal(0.0, 0.010 * spread)

    elif is_valve(comp):
        if t_prefix == "LIT":
            drift = -deg_factor * (0.04 * spread)
            val = baseline_val + drift + np.random.normal(0.0, 0.020 * spread)
            if deg_factor > 0.3:
                val += _osc(step_idx, 120) * deg_factor * 0.03 * spread

    return max(0.0, float(val))


# ============================================================
# FAULT PHYSICS
# ============================================================

def _owner_weight(owner_comp: str) -> float:
    st = component_status.get(owner_comp, "HEALTHY")
    if st == "FAULTED":
        return 1.0
    if st == "DEGRADING":
        return 0.85
    if anomaly is not None and anomaly.get("component") == owner_comp:
        return 0.60
    return 0.25


def apply_fault_physics(tag: str, baseline_val: float, comp: str, severity_01: float) -> float:
    t_prefix = _family_prefix(tag)
    st = baseline_stats.get(tag, {})
    val = baseline_val
    med = float(st.get("median", val))
    p05 = float(st.get("p05", med))
    p95 = float(st.get("p95", med))
    spread = max(1e-9, p95 - p05)

    if t_prefix == "FIT":
        p05 = st.get("p05", val * 0.7)
        target = p05 + np.random.uniform(0, 0.15 * spread)
        val = val - (0.5 + 0.3 * severity_01) * (val - target)

    elif t_prefix in ("PIT", "DPIT"):
        p90 = st.get("p90", val * 1.3)
        p95 = st.get("p95", val * 1.5)
        target = p90 * (1 - severity_01) + p95 * severity_01
        val = max(val, target)

    elif t_prefix == "LIT":
        if is_pump(comp):
            val += np.random.uniform(-0.05, 0.05) * severity_01 * abs(val)
        elif is_valve(comp):
            val += np.random.choice([-1, 1]) * severity_01 * 0.15 * abs(val)

    elif t_prefix == "AIT":
        p95 = st.get("p95", val)
        p99 = st.get("p99", val)
        target = p95 * (1 - severity_01) + p99 * severity_01
        val = max(val, target)

    return max(0.0, float(val))


# ============================================================
# ANOMALY PHYSICS
# ============================================================

def apply_anomaly_physics(tag: str, baseline_val: float, anom_type: str,
                           severity: float, step_idx: int) -> float:
    t_prefix = _family_prefix(tag)
    st = baseline_stats.get(tag, {})
    val = baseline_val
    mag = max(1.0, abs(val))
    rel_scale = severity * 0.02 * mag

    if anom_type == "cavitation":
        if t_prefix == "FIT":
            val -= severity * 1.2 * (val - st.get("p05", val * 0.5))
        elif t_prefix in ("PIT", "DPIT"):
            val += severity * 0.15 * (st.get("p90", val * 1.2) - val) + np.random.normal(0.0, rel_scale)
        elif t_prefix == "AIT":
            val += severity * 0.03 * mag + np.random.normal(0.0, severity * 0.01 * mag)

    elif anom_type == "flow_oscillation":
        period_steps = int(np.random.randint(12, 36))
        wave = _osc(step_idx, period_steps)
        if t_prefix == "FIT":
            val += wave * (severity * 0.06 * mag)
        elif t_prefix in ("PIT", "DPIT"):
            val += wave * (severity * 0.04 * mag)
        elif t_prefix == "AIT":
            val += wave * (severity * 0.02 * mag) + np.random.normal(0.0, severity * 0.005 * mag)

    elif anom_type == "valve_chatter":
        if t_prefix == "LIT":
            val += np.random.normal(0.0, severity * 0.03 * mag)

    elif anom_type == "level_jitter":
        if t_prefix == "LIT":
            period_steps = int(np.random.randint(30, 90))
            wave = _osc(step_idx, period_steps)
            val += wave * (severity * 0.03 * mag) + np.random.normal(0.0, severity * 0.01 * mag)

    return max(0.0, float(val))


# ============================================================
# PHYSICS DISPATCH (same shared sensor blending as the simulator)
# ============================================================

def apply_physics(expected: dict, step_idx: int) -> dict:
    true_vals = {}

    for tag in sensor_tags:
        k = f"expected_{tag}"
        if k not in expected:
            continue

        baseline_val = float(expected[k])

        if tag in SHARED_SENSORS:
            owner_comps = SHARED_SENSORS[tag]
            affected_values = []

            for owner_comp in owner_comps:
                if owner_comp not in component_status:
                    affected_values.append(baseline_val)
                    continue

                status = component_status[owner_comp]
                comp_health = health[owner_comp]
                val = baseline_val

                if status == "FAULTED":
                    severity_01 = (100 - comp_health) / 100.0
                    val = apply_fault_physics(tag, baseline_val, owner_comp, severity_01)
                elif status == "DEGRADING":
                    val = apply_degradation_physics(tag, baseline_val, owner_comp, comp_health, step_idx)
                elif status == "HEALTHY" and anomaly is not None:
                    if owner_comp == anomaly["component"]:
                        val = apply_anomaly_physics(tag, baseline_val, anomaly["type"],
                                                     anomaly["severity"], step_idx)
                else:
                    val += np.random.normal(0, 0.0010 * abs(baseline_val))

                affected_values.append(val)

            weights = [_owner_weight(c) for c in owner_comps]
            final_val = float(np.average(affected_values, weights=weights))
            true_vals[f"true_{tag}"] = max(0.0, float(final_val))

        else:
            owner_comp = None
            for comp, sensors in COMP_TO_SENSORS.items():
                if tag in sensors and comp in component_status:
                    owner_comp = comp
                    break

            if owner_comp is None:
                true_vals[f"true_{tag}"] = baseline_val
                continue

            status = component_status[owner_comp]
            comp_health = health[owner_comp]
            val = baseline_val

            if status == "FAULTED":
                severity_01 = (100 - comp_health) / 100.0
                val = apply_fault_physics(tag, val, owner_comp, severity_01)
            elif status == "DEGRADING":
                val = apply_degradation_physics(tag, val, owner_comp, comp_health, step_idx)
            elif status == "HEALTHY" and anomaly is not None:
                if owner_comp == anomaly["component"]:
                    val = apply_anomaly_physics(tag, val, anomaly["type"], anomaly["severity"], step_idx)
            else:
                val += np.random.normal(0, 0.0010 * abs(baseline_val))

            true_vals[f"true_{tag}"] = max(0.0, float(val))

    return true_vals


# ============================================================
# OBSERVABLE BIAS (same logic as the simulator)
# ============================================================

def enforce_observable_bias(tag: str, val: float, kind: str, comp: str, severity01: float) -> float:
    rs = robust_stats.get(tag)
    if not rs:
        return float(val)

    med = rs["median"]
    mad = rs["mad"]

    if kind == "ANOMALY":
        min_z = ANOM_MIN_Z
    elif kind == "DEGRADING":
        min_z = DEGRADE_MIN_Z_START + severity01 * (DEGRADE_MIN_Z_END - DEGRADE_MIN_Z_START)
    else:
        min_z = FAULT_MIN_Z

    min_shift = min_z * mad
    fam = _family_prefix(tag)

    direction = 0.0
    if is_pump(comp):
        if fam == "FIT":
            direction = -1.0
        elif fam in ("PIT", "DPIT"):
            direction = +1.0
        elif fam == "AIT":
            direction = +1.0
        elif fam == "LIT":
            direction = -1.0
    elif is_valve(comp):
        if fam == "LIT":
            direction = -1.0

    if direction == 0.0:
        return float(val)

    st = baseline_stats.get(tag, {})
    spread = max(1e-9, float(st.get("p95", med) - st.get("p05", med)))
    extra = float(severity01) * 0.20 * spread

    target_shift = min_shift + extra
    cur_shift = (val - med) * direction

    if cur_shift >= target_shift:
        return float(val)

    return float(med + direction * target_shift)


def enforce_bias_on_true_vals(true_vals: dict, kind: str, comp: str, severity01: float) -> dict:
    comp = str(comp).strip().upper()
    tags = component_sensor_tags(comp)

    for shared_tag, owners in SHARED_SENSORS.items():
        if comp in owners and shared_tag in sensor_tags:
            tags.append(shared_tag)

    if not tags:
        return true_vals

    out = dict(true_vals)
    for t in tags:
        k = f"true_{t}"
        if k not in out:
            continue
        out[k] = enforce_observable_bias(tag=t, val=float(out[k]), kind=kind, comp=comp, severity01=severity01)
    return out


# ============================================================
# SENSOR NOISE
# ============================================================

def add_run_sensor_noise(true_vals: dict) -> dict:
    out = dict(true_vals)
    for k, v in true_vals.items():
        tag = k.replace("true_", "")
        if not tag.startswith(RUN_SENSOR_NOISE_APPLY_TAG_PREFIX):
            continue
        v = float(v)
        std = max(abs(v) * RUN_SENSOR_NOISE_REL_STD, RUN_SENSOR_NOISE_ABS_STD)
        out[k] = max(0.0, v + float(np.random.normal(0.0, std)))
    return out


# ============================================================
# THE GROUND TRUTH LABELS
# ============================================================

def build_meta_columns():
    degrading_active = degrading_component if (degrading_component and not current_fault) else "none"
    return {
        "system_status": system_status,
        "degrading_component": degrading_active,
        "faulted_component": current_fault["component"] if current_fault else "none",
        "anomaly_component": anomaly["component"] if anomaly else "none",
        "is_degrading": 1 if (degrading_component and not current_fault) else 0,
        "is_faulted": 1 if current_fault else 0,
        "is_anomaly": 1 if anomaly else 0,
    }


# ============================================================
# CSV COLUMNS
# ============================================================

actuator_fields = list(pump_tags + valve_tags)
true_fields = [f"true_{t}" for t in sensor_tags]

pump_phys_fields = []
for p in pump_tags:
    pump_phys_fields += [f"true_{p}_motor_temp", f"true_{p}_current", f"true_{p}_vibration"]

meta_fields = [
    "timestamp", "system_status", "degrading_component", "faulted_component",
    "anomaly_component", "is_degrading", "is_faulted", "is_anomaly",
]

health_fields = [f"expected_H_{c}" for c in components]

fieldnames = actuator_fields + true_fields + pump_phys_fields + meta_fields + health_fields


# ============================================================
# MAIN LOOP, PLAYS BACK EVENT_SCHEDULE UNTIL IT RUNS OUT
# ============================================================

def main(output_csv=OUTPUT_CSV):
    global system_status, degrading_component, current_fault
    global anomaly, component_status, health, fault_thresholds
    global motor_temp_true

    global_step = 0
    event_idx = 0
    current_event = None
    event_phase = None  # "degrading", "faulted", "startup", "anomaly", "normal_gap"
    phase_steps_left = 0

    # An anomaly scheduled for a component that isn't currently healthy
    # gets pushed here and retried once it frees up, so nothing in the
    # schedule is silently skipped.
    deferred_anomalies = []
    last_run_values = {}

    system_status = "RUN"
    gap_hours = np.random.uniform(*NORMAL_GAP_HOURS_RANGE)
    phase_steps_left = int(gap_hours * 3600 / STEP_SEC)
    event_phase = "normal_gap"

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        iterator = range(10_000_000)  # large upper bound, breaks once the schedule is done
        if USE_TQDM:
            iterator = tqdm(iterator, total=len(EVENT_SCHEDULE) * 2000, desc="Generating training data")

        for _ in iterator:
            dt_hours = STEP_SEC / 3600.0

            # ---- phase transitions ----

            if phase_steps_left <= 0:
                if event_phase in ("normal_gap", "startup"):
                    if event_phase == "startup":
                        system_status = "RUN"

                    if deferred_anomalies:
                        current_event = deferred_anomalies.pop(0)
                    elif event_idx >= len(EVENT_SCHEDULE):
                        print("\nAll scheduled events completed.")
                        break
                    else:
                        current_event = EVENT_SCHEDULE[event_idx]
                        event_idx += 1

                    if current_event["type"] == "DEGRADATION_CYCLE":
                        if anomaly is not None:
                            deferred_anomalies.append(current_event)
                            gap_hours = np.random.uniform(*NORMAL_GAP_HOURS_RANGE)
                            phase_steps_left = int(gap_hours * 3600 / STEP_SEC)
                            event_phase = "normal_gap"
                            system_status = "RUN"
                            continue

                        comp = current_event["component"]
                        degrading_component = comp
                        component_status[comp] = "DEGRADING"

                        if anomaly is not None and anomaly["component"] == comp:
                            anomaly = None

                        h0 = float(health[comp])
                        thr = float(current_event["fault_threshold"])
                        thr = min(thr, h0 - 12.0)
                        thr = max(thr, 20.0)
                        fault_thresholds[comp] = thr

                        event_phase = "degrading"
                        episode_start_step[comp] = global_step
                        episode_h0[comp] = h0
                        episode_thr[comp] = thr

                        params = COMPONENT_DEGRADATION.get(comp)
                        if params:
                            lo, hi = params["accel_wear_per_hour"]
                            wear = float(np.random.uniform(lo, hi))
                            episode_wear_rate[comp] = wear
                            dh = max(1.0, h0 - thr)
                            hours = dh / max(1e-6, wear)
                            episode_expected_steps[comp] = int(max(600, hours * 3600 / STEP_SEC))

                        phase_steps_left = 999999  # runs until the fault threshold is hit

                    elif current_event["type"] == "ANOMALY":
                        comp = current_event["component"]
                        if can_start_anomaly_now(comp):
                            anomaly = {
                                "component": comp,
                                "type": current_event["subtype"],
                                "severity": current_event["severity"],
                            }
                            event_phase = "anomaly"
                            phase_steps_left = current_event["duration_steps"]
                        else:
                            deferred_anomalies.append(current_event)
                            gap_hours = np.random.uniform(*NORMAL_GAP_HOURS_RANGE)
                            phase_steps_left = int(gap_hours * 3600 / STEP_SEC)
                            event_phase = "normal_gap"

                elif event_phase == "degrading":
                    pass  # exits below, via check_for_fault, not here

                elif event_phase == "faulted":
                    # No downtime phase, straight to startup.
                    if current_fault:
                        comp = current_fault["component"]
                        health[comp] = 95.0
                        component_status[comp] = "HEALTHY"
                        episode_wear_rate.pop(comp, None)
                        episode_start_step.pop(comp, None)
                        episode_h0.pop(comp, None)
                        episode_thr.pop(comp, None)
                        episode_expected_steps.pop(comp, None)

                    current_fault = None
                    degrading_component = None
                    system_status = "STARTUP"
                    event_phase = "startup"
                    phase_steps_left = int(STARTUP_DURATION_MINUTES * 60 / STEP_SEC)

                elif event_phase == "anomaly":
                    anomaly = None
                    gap_hours = np.random.uniform(*NORMAL_GAP_HOURS_RANGE)
                    phase_steps_left = int(gap_hours * 3600 / STEP_SEC)
                    event_phase = "normal_gap"
                    system_status = "RUN"

            # ---- state updates ----

            if system_status == "RUN":
                update_health(dt_hours)

                if event_phase == "degrading":
                    if check_for_fault():
                        fault_hours = np.random.uniform(*FAULT_DURATION_HOURS_RANGE)
                        phase_steps_left = int(fault_hours * 3600 / STEP_SEC)
                        event_phase = "faulted"
                        if anomaly is not None:
                            anomaly = None

            expected, actuators = baseline.step()
            if system_status == "RUN" and degrading_component is not None:
                if is_pump(degrading_component):
                    actuators[degrading_component] = 2

            if system_status == "STARTUP":
                for a in actuators:
                    actuators[a] = 1

            # ---- physics ----

            true_vals = apply_physics(expected, global_step)

            if system_status == "STARTUP":
                for k in list(expected.keys()):
                    tag = k.replace("expected_", "")
                    if tag.startswith(("FIT", "PIT", "DPIT")):
                        expected[k] = 0.0
                    elif tag.startswith(("LIT", "AIT")):
                        expected[k] = float(last_run_values.get(k, expected[k]))

                for k in list(true_vals.keys()):
                    tag = k.replace("true_", "")
                    if tag.startswith(("FIT", "PIT", "DPIT")):
                        true_vals[k] = 0.0
                    elif tag.startswith(("LIT", "AIT")):
                        true_vals[k] = float(last_run_values.get(k, true_vals[k]))

            if system_status == "RUN":
                true_vals = add_run_sensor_noise(true_vals)

                if anomaly is not None:
                    sev01 = np.clip(anomaly["severity"] / ANOMALY_SEVERITY_RANGE[1], 0, 1)
                    true_vals = enforce_bias_on_true_vals(true_vals, "ANOMALY", anomaly["component"], sev01)

                if degrading_component is not None and component_status[degrading_component] == "DEGRADING":
                    sev01 = np.clip((100 - health[degrading_component]) / 100.0, 0, 1)
                    true_vals = enforce_bias_on_true_vals(true_vals, "DEGRADING", degrading_component, sev01)

            if current_fault is not None:
                sev01 = np.clip(current_fault["severity"] / 100.0, 0, 1)
                true_vals = enforce_bias_on_true_vals(true_vals, "FAULT", current_fault["component"], sev01)

            if system_status == "RUN":
                for k, v in expected.items():
                    tag = k.replace("expected_", "")
                    if tag.startswith(("LIT", "AIT")):
                        last_run_values[k] = float(v)
                for k, v in true_vals.items():
                    tag = k.replace("true_", "")
                    if tag.startswith(("LIT", "AIT")):
                        last_run_values[k] = float(v)

            if system_status == "STARTUP":
                for k in list(expected.keys()):
                    tag = k.replace("expected_", "")
                    if tag.startswith(("LIT", "AIT")) and k in last_run_values:
                        expected[k] = (1 - STARTUP_BLEND) * last_run_values[k] + STARTUP_BLEND * expected[k]

                for k in list(true_vals.keys()):
                    tag = k.replace("true_", "")
                    if tag.startswith(("LIT", "AIT")) and k in last_run_values:
                        true_vals[k] = (1 - STARTUP_BLEND) * last_run_values[k] + STARTUP_BLEND * true_vals[k]

            # ---- motor physics ----

            pump_outputs = {}
            for p in pump_tags:
                on = int(actuators[p] == 2 and system_status == "RUN")
                load_true = compute_pump_load_from("true_", p, true_vals, on)

                if p in component_status:
                    status = component_status[p]
                    comp_health = health[p]
                else:
                    status = "HEALTHY"
                    comp_health = 100.0

                motor_temp_true[p] = motor_temp(on, load_true, motor_temp_true[p], comp_health, status)
                pump_outputs[f"true_{p}_motor_temp"] = round(motor_temp_true[p], 3)
                pump_outputs[f"true_{p}_current"] = round(motor_current(on, load_true, comp_health, status), 3)
                pump_outputs[f"true_{p}_vibration"] = round(motor_vibration(on, load_true, comp_health, status), 3)

            # ---- clamp (off by default) ----

            if CLAMP_TO_P05_P995 and system_status == "RUN" and anomaly is None and current_fault is None and (
                    degrading_component is None):
                for k in list(true_vals.keys()):
                    if k.startswith("true_"):
                        tag = k.replace("true_", "")
                        true_vals[k] = clamp_tag(tag, true_vals[k])

            # ---- build the row ----

            row = {}
            for a in actuator_fields:
                row[a] = actuators.get(a, 1)
            for k in true_fields:
                row[k] = true_vals.get(k, 0.0)
            for k in pump_phys_fields:
                row[k] = pump_outputs.get(k, 0.0)

            row["timestamp"] = (START_TIMESTAMP + timedelta(seconds=global_step * STEP_SEC)).isoformat()

            meta = build_meta_columns()
            for k in meta_fields[1:]:
                row[k] = meta[k]

            for c in components:
                row[f"expected_H_{c}"] = round(float(health[c]), 2)

            writer.writerow(row)

            # ---- timers ----

            if phase_steps_left < 999999:  # don't decrement the "runs until fault" phase
                phase_steps_left -= 1

            global_step += 1

            if USE_TQDM and (global_step % 1000 == 0):
                iterator.set_postfix({
                    "event": f"{event_idx}/{len(EVENT_SCHEDULE)}",
                    "phase": event_phase[:4] if event_phase else "none",
                    "status": system_status[:3],
                    "deferred": len(deferred_anomalies),
                })

    print(f"\nSaved: {output_csv}")
    print(f"Total steps: {global_step}")
    print(f"Events processed: {event_idx}/{len(EVENT_SCHEDULE)}")
    print(f"Deferred anomalies remaining: {len(deferred_anomalies)}")
    print(f"Components: {len(components)}")
    print(f"Sensors: {len(sensor_tags)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=str, default=str(OUTPUT_CSV),
                         help=f"output CSV path (default {OUTPUT_CSV})")
    args = parser.parse_args()

    main(output_csv=args.output)
