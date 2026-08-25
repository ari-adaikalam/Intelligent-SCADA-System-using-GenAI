"""Builds the full dataset-metadata.json for the Kaggle dataset, including
per-file descriptions and per-column schema, to close out the quality-score
checklist (tags, source/provenance, update frequency, file/column descriptions).

Writes to output/dataset-metadata.json. Run kaggle commands from output/,
and never put anything else in that folder, Kaggle uploads every file it
finds there as a dataset resource."""

import json
from pathlib import Path

OUT = Path(__file__).parent / "output"
OUT.mkdir(exist_ok=True)

TAG_MEANINGS = {
    "FIT": "Flow Indicator Transmitter",
    "LIT": "Level Indicator Transmitter",
    "AIT": "Analyzer Indicator Transmitter (pH, conductivity, or ORP)",
    "DPIT": "Differential Pressure Indicator Transmitter",
    "PIT": "Pressure Indicator Transmitter",
}


def sensor_description(tag):
    bare = tag.replace("true_", "")
    prefix = "".join(c for c in bare if not c.isdigit())
    return f"{TAG_MEANINGS.get(prefix, 'Sensor reading')} ({bare}), perturbed by the simulator's fault/degradation/anomaly physics."


ACTUATORS = ['P101', 'P201', 'P203', 'P205', 'P302', 'P402', 'P403', 'P501',
             'MV101', 'MV201', 'MV301', 'MV302', 'MV303', 'MV304']
SIMULATED_COMPONENTS = {'P101', 'P201', 'P203', 'P205', 'P302', 'P402', 'P403', 'P501', 'MV101', 'MV304'}

SENSORS = ['true_FIT101', 'true_LIT101', 'true_AIT201', 'true_AIT202', 'true_AIT203', 'true_FIT201',
           'true_DPIT301', 'true_FIT301', 'true_LIT301', 'true_AIT401', 'true_AIT402', 'true_FIT401',
           'true_LIT401', 'true_AIT501', 'true_FIT501', 'true_PIT501']

# clean_1.csv carries every raw column from the source SWaT baseline, including ones
# the simulator never touches (stage 5 has more sensors than the 10 simulated
# components use, plus the UV401 disinfection unit). Listed here so the schema
# covers all 40 real columns in that file, not just the ones the simulator perturbs.
BASELINE_ONLY_SENSORS = ['AIT502', 'AIT503', 'AIT504', 'FIT502', 'FIT503', 'FIT504', 'PIT502', 'PIT503']
BASELINE_ONLY_ACTUATORS = ['UV401']

MOTOR = ['true_P101_motor_temp', 'true_P101_current', 'true_P101_vibration',
         'true_P201_motor_temp', 'true_P201_current', 'true_P201_vibration',
         'true_P203_motor_temp', 'true_P203_current', 'true_P203_vibration',
         'true_P205_motor_temp', 'true_P205_current', 'true_P205_vibration',
         'true_P302_motor_temp', 'true_P302_current', 'true_P302_vibration',
         'true_P402_motor_temp', 'true_P402_current', 'true_P402_vibration',
         'true_P403_motor_temp', 'true_P403_current', 'true_P403_vibration',
         'true_P501_motor_temp', 'true_P501_current', 'true_P501_vibration']

META = ['timestamp', 'system_status', 'degrading_component', 'faulted_component',
        'anomaly_component', 'is_degrading', 'is_faulted', 'is_anomaly']

HEALTH = ['expected_H_P101', 'expected_H_P201', 'expected_H_P203', 'expected_H_P205', 'expected_H_P302',
          'expected_H_P402', 'expected_H_P403', 'expected_H_P501', 'expected_H_MV101', 'expected_H_MV304']

META_DESCRIPTIONS = {
    'timestamp': ("Simulated timestamp for this row, 10 seconds apart from the previous row.", "datetime"),
    'system_status': ("Plant lifecycle state: RUN, FAULT, DOWNTIME, or STARTUP.", "string"),
    'degrading_component': ("Component currently in a DEGRADING episode, or 'none'.", "string"),
    'faulted_component': ("Component currently FAULTED, or 'none'.", "string"),
    'anomaly_component': ("Component currently having a transient anomaly, or 'none'.", "string"),
    'is_degrading': ("1 if degrading_component is active, else 0.", "integer"),
    'is_faulted': ("1 if faulted_component is active, else 0.", "integer"),
    'is_anomaly': ("1 if anomaly_component is active, else 0.", "integer"),
}


def generated_file_fields():
    fields = []
    for tag in ACTUATORS:
        note = "" if tag in SIMULATED_COMPONENTS else " (replayed from the baseline, never faulted by the simulator)"
        fields.append({"name": tag, "type": "integer", "description": f"Actuator state code (1=off/closed, 2=on/open){note}."})
    for tag in SENSORS:
        fields.append({"name": tag, "type": "number", "description": sensor_description(tag)})
    for col in MOTOR:
        pump = col.split("_")[1]
        label = {"motor_temp": "motor temperature (deg C)", "current": "motor current (A)",
                  "vibration": "motor vibration (simulated relative units)"}
        key = col[len(f"true_{pump}_"):]
        fields.append({"name": col, "type": "number", "description": f"Simulated {pump} {label[key]}."})
    for col in META:
        desc, typ = META_DESCRIPTIONS[col]
        fields.append({"name": col, "type": typ, "description": desc})
    for col in HEALTH:
        comp = col.replace("expected_H_", "")
        fields.append({"name": col, "type": "number", "description": f"Ground truth wear score for {comp}, 100 (new) down to its randomized fault threshold."})
    return fields


def baseline_file_fields():
    fields = [{"name": "Timestamp", "type": "datetime", "description": "Original recording timestamp from the source SWaT dataset."}]
    for tag in ACTUATORS:
        fields.append({"name": tag, "type": "integer", "description": "Actuator state code (1=off/closed, 2=on/open), from the source SWaT dataset."})
    for tag in BASELINE_ONLY_ACTUATORS:
        fields.append({"name": tag, "type": "integer", "description": "UV disinfection unit state code, from the source SWaT dataset. Not simulated or perturbed, this component is outside the 10 the digital twin models."})
    for tag in SENSORS:
        clean_tag = tag.replace("true_", "")
        fields.append({"name": clean_tag, "type": "number", "description": sensor_description(clean_tag).split(",")[0] + ", from the source SWaT dataset (normal operation only)."})
    for tag in BASELINE_ONLY_SENSORS:
        fields.append({"name": tag, "type": "number", "description": sensor_description(tag).split(",")[0] + ", from the source SWaT dataset. Not simulated or perturbed, this sensor is outside the 10 components the digital twin models."})
    return fields


metadata = {
    "title": "SWaT Digital Twin: Faults and Anomalies",
    "id": "ariadaikalam/fyp-ml-dataset",
    "subtitle": "Physics-based synthetic fault and anomaly data from a SWaT digital twin",
    "licenses": [{"name": "CC0-1.0"}],
    "keywords": ["manufacturing", "engineering", "classification", "datetime", "synthetic"],
    "isPrivate": False,
    "expectedUpdateFrequency": "never",
    "userSpecifiedSources": (
        "The baseline (clean_1.csv) is a cleaned extract of the normal-operation file from "
        "vishala28/swat-dataset-secure-water-treatment-system on Kaggle (CC0-1.0), itself sourced "
        "from the Secure Water Treatment (SWaT) industrial testbed. The two generated files "
        "(plant_simulation.csv, training_data.csv) are produced by this project's own physics-based "
        "digital twin simulator (open source at github.com/ari-adaikalam/Intelligent-SCADA-System-using-GenAI, "
        "data-simulation/ folder), not observed from any real plant."
    ),
    "resources": [
        {
            "path": "clean_1.csv",
            "description": "Cleaned baseline extract of the source SWaT dataset, normal operation only. The replay signal the simulator perturbs.",
            "schema": {"fields": baseline_file_fields()},
        },
        {
            "path": "plant_simulation.csv",
            "description": "Realistic, randomly timed simulation. Long healthy stretches, faults whenever they happen, same as a real plant. Held out from training entirely, this is the generalization check.",
            "schema": {"fields": generated_file_fields()},
        },
        {
            "path": "training_data.csv",
            "description": "Same physics as plant_simulation.csv, but every component and fault type is scheduled to appear a guaranteed number of times. This is the file the ML models actually train on.",
            "schema": {"fields": generated_file_fields()},
        },
    ],
}

with open(Path(__file__).parent / "kaggle_description.md") as f:
    metadata["description"] = f.read()

with open(OUT / "dataset-metadata.json", "w") as f:
    json.dump(metadata, f, indent=2)

print("Wrote output/dataset-metadata.json")
print("Fields per generated file:", len(generated_file_fields()))
print("Fields for clean_1.csv:", len(baseline_file_fields()))
