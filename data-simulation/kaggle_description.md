A physics-based digital twin built on top of a real water treatment testbed, used to train the hierarchical fault-detection pipeline in [Intelligent SCADA System using GenAI](https://github.com/ari-adaikalam/Intelligent-SCADA-System-using-GenAI).

### Source

Built on [SWaT Dataset: Secure Water Treatment System](https://www.kaggle.com/datasets/vishala28/swat-dataset-secure-water-treatment-system) by vishala28 (CC0-1.0), real sensor and actuator readings from a scaled-down industrial water treatment testbed. That dataset is almost entirely normal operation, with too little labeled fault and anomaly data to train a fault classifier on directly.

### What was built on top of it

A simulator that replays the real baseline readings and layers physically grounded degradation, faults, and transient anomalies on top, one component at a time. Each of 8 pumps and 2 valves wears down over a randomized lifespan, crosses a fault threshold, fails with a realistic sensor and motor signature (temperature, current, vibration), then recovers through a startup phase. A separate process fires short transient anomalies (cavitation, valve chatter, flow oscillation, level jitter) on whichever component is healthy at the time. The simulator code is open source in the `data-simulation/` folder of the linked repository.

### Files

| File | What it is |
|---|---|
| `clean_1.csv` | Cleaned baseline extract of the source SWaT dataset, normal operation only. The replay signal the simulator perturbs. |
| `plant_simulation.csv` | Realistic, randomly timed simulation. Long healthy stretches, faults whenever they happen, same as a real plant. Held out from training entirely, this is the generalization check. |
| `training_data.csv` | Same physics, but every component and fault type is scheduled to appear a guaranteed number of times. This is the file the models actually train on. |

### Column reference, generated files

Both generated CSVs share the same 72 columns.

**Actuators** (14 columns, raw state codes from the source dataset: 1 = off/closed, 2 = on/open)
`P101, P201, P203, P205, P302, P402, P403, P501` (pumps), `MV101, MV201, MV301, MV302, MV303, MV304` (motorized valves). Only the first 10 are ever driven into a fault state by the simulator, the rest are replayed as-is from the baseline.

**Sensor readings**, prefixed `true_` (16 columns), tag meanings from the source dataset:
- `FIT101, FIT201, FIT301, FIT401, FIT501`: Flow Indicator Transmitters
- `LIT101, LIT301, LIT401`: Level Indicator Transmitters
- `AIT201, AIT202, AIT203, AIT401, AIT402, AIT501`: Analyzer Indicator Transmitters (pH, conductivity, ORP)
- `DPIT301`: Differential Pressure Indicator Transmitter
- `PIT501`: Pressure Indicator Transmitter

**Motor physics**, 3 simulated signals per pump, 24 columns: `true_{PUMP}_motor_temp` (deg C), `true_{PUMP}_current` (A), `true_{PUMP}_vibration` (simulated relative units), for each of the 8 pumps above.

**Labels** (8 columns): `timestamp`, `system_status` (`RUN`, `FAULT`, `DOWNTIME`, `STARTUP`), `degrading_component`, `faulted_component`, `anomaly_component` (component name or `none`), `is_degrading`, `is_faulted`, `is_anomaly` (0/1 flags).

**Component health** (10 columns): `expected_H_{COMPONENT}`, a 0 to 100 ground truth wear score for each of the 10 simulated components, 100 is brand new, dropping toward each component's randomized fault threshold.

### Column reference, clean_1.csv

The cleaned baseline: the same actuator and sensor tags as above (without the `true_` prefix or the added label/health columns), taken directly from the source SWaT dataset's normal operation file, with header whitespace and encoding artifacts stripped.

### License

CC0-1.0, matching the source dataset.
