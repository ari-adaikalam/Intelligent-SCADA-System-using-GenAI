"""
Turns the two simulation CSVs into the scaled arrays and labels the
training scripts use.

training_data.csv (from scheduled_data_generator.py) is split 60/20/20
by time into train, validation, and test. Only the 60% train split is
ever fit on. plant_simulation.csv (from plant_simulator.py) is scaled
with that same scaler but never split or trained on, it is the held-out
generalization check reported throughout training.

The split is by time, not shuffled. Shuffling first would leak later
rows (like the tail of a fault) into the training set through their
neighbors, which is a form of data leakage for time series.
"""

import json
import pickle
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from paths import OUTPUT_DIR, PLANT_SIMULATION_FILE, TRAINING_DATA_FILE

TRAIN_RATIO = 0.6
VAL_RATIO = 0.2
TEST_RATIO = 0.2

# 16 raw sensor readings.
SENSOR_FEATURES = [
    'true_FIT101', 'true_FIT201', 'true_FIT301', 'true_FIT401', 'true_FIT501',
    'true_LIT101', 'true_LIT301', 'true_LIT401',
    'true_AIT201', 'true_AIT202', 'true_AIT203', 'true_AIT401', 'true_AIT402', 'true_AIT501',
    'true_DPIT301', 'true_PIT501',
]

# 24 motor physics readings, 3 signals for each of 8 pumps.
PUMP_NAMES = ['P101', 'P201', 'P203', 'P205', 'P302', 'P402', 'P403', 'P501']
MOTOR_FEATURES = []
for pump in PUMP_NAMES:
    MOTOR_FEATURES.extend([f'true_{pump}_motor_temp', f'true_{pump}_current', f'true_{pump}_vibration'])

ALL_FEATURES = SENSOR_FEATURES + MOTOR_FEATURES  # 40 total

COMPONENTS = ['P101', 'P201', 'P203', 'P205', 'P302', 'P402', 'P403', 'P501', 'MV101', 'MV304']
COMPONENT_TO_IDX = {comp: i for i, comp in enumerate(COMPONENTS)}


def get_stage2_label(row):
    """3 class state label. 0 anomaly, 1 degrading, 2 faulted, -1 normal (excluded)."""
    if row['is_anomaly'] == 1:
        return 0
    elif row['is_degrading'] == 1:
        return 1
    elif row['is_faulted'] == 1:
        return 2
    return -1


def get_stage3_label(row):
    """10 class component label. Index into COMPONENTS, -1 normal (excluded)."""
    if row['is_faulted'] == 1:
        comp = row['faulted_component']
    elif row['is_degrading'] == 1:
        comp = row['degrading_component']
    elif row['is_anomaly'] == 1:
        comp = row['anomaly_component']
    else:
        return -1

    if comp == 'none' or comp not in COMPONENT_TO_IDX:
        return -1
    return COMPONENT_TO_IDX[comp]


def main():
    print("Preparing the dataset")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print(f"\nLoading training data: {TRAINING_DATA_FILE}")
    df_train_source = pd.read_csv(TRAINING_DATA_FILE)
    print(f"Loaded {len(df_train_source):,} rows, {len(df_train_source.columns)} columns")
    print(f"Duration: {len(df_train_source) * 10 / 3600:.1f} hours")

    missing = [f for f in ALL_FEATURES if f not in df_train_source.columns]
    if missing:
        raise ValueError(f"Missing features in training data: {missing}")

    # ---- labels ----
    df_train_source['label_stage1'] = (
        (df_train_source['is_degrading'] == 1) |
        (df_train_source['is_faulted'] == 1) |
        (df_train_source['is_anomaly'] == 1)
    ).astype(int)

    s1_counts = df_train_source['label_stage1'].value_counts()
    print(f"\nStage 1 labels: normal {s1_counts.get(0, 0):,}, anomaly {s1_counts.get(1, 0):,}")

    df_train_source['label_stage2'] = df_train_source.apply(get_stage2_label, axis=1)
    df_train_source['label_stage3'] = df_train_source.apply(get_stage3_label, axis=1)

    # ---- time based split, no shuffling ----
    n = len(df_train_source)
    train_size = int(TRAIN_RATIO * n)
    val_size = int(VAL_RATIO * n)

    train_idx = np.arange(0, train_size)
    val_idx = np.arange(train_size, train_size + val_size)
    test_idx = np.arange(train_size + val_size, n)

    overlap = (len(set(train_idx) & set(val_idx))
               + len(set(train_idx) & set(test_idx))
               + len(set(val_idx) & set(test_idx)))
    if overlap > 0:
        raise ValueError("Split overlap detected, this should never happen")

    print(f"\nSplit: train {len(train_idx):,}, val {len(val_idx):,}, test {len(test_idx):,}")

    X = df_train_source[ALL_FEATURES].values
    if np.isnan(X).sum() > 0:
        raise ValueError("NaN values found in features")

    y_stage1 = df_train_source['label_stage1'].values
    y_stage2 = df_train_source['label_stage2'].values
    y_stage3 = df_train_source['label_stage3'].values

    health_cols = [f'expected_H_{comp}' for comp in COMPONENTS]
    health_data = df_train_source[health_cols].values

    X_train, X_val, X_test = X[train_idx], X[val_idx], X[test_idx]
    y1_train, y1_val, y1_test = y_stage1[train_idx], y_stage1[val_idx], y_stage1[test_idx]
    y2_train, y2_val, y2_test = y_stage2[train_idx], y_stage2[val_idx], y_stage2[test_idx]
    y3_train, y3_val, y3_test = y_stage3[train_idx], y_stage3[val_idx], y_stage3[test_idx]
    health_train, health_val, health_test = health_data[train_idx], health_data[val_idx], health_data[test_idx]

    # ---- scale, fit on the train split only ----
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    print(f"\nScaled. Train mean {X_train_scaled.mean():.4f}, train std {X_train_scaled.std():.4f}")

    # ---- load the simulator data, the held-out generalization check ----
    print(f"\nLoading simulation data: {PLANT_SIMULATION_FILE}")
    df_sim = pd.read_csv(PLANT_SIMULATION_FILE)
    print(f"Loaded {len(df_sim):,} rows")

    missing_sim = [f for f in ALL_FEATURES if f not in df_sim.columns]
    if missing_sim:
        raise ValueError(f"Missing features in simulation data: {missing_sim}")

    df_sim['label_stage1'] = (
        (df_sim['is_degrading'] == 1) | (df_sim['is_faulted'] == 1) | (df_sim['is_anomaly'] == 1)
    ).astype(int)
    df_sim['label_stage2'] = df_sim.apply(get_stage2_label, axis=1)
    df_sim['label_stage3'] = df_sim.apply(get_stage3_label, axis=1)

    X_sim = df_sim[ALL_FEATURES].values
    y1_sim = df_sim['label_stage1'].values
    y2_sim = df_sim['label_stage2'].values
    y3_sim = df_sim['label_stage3'].values
    health_sim = df_sim[health_cols].values

    # Same scaler as the training split, never refit on the simulation data.
    X_sim_scaled = scaler.transform(X_sim)
    print(f"Simulation anomaly rate: {y1_sim.mean() * 100:.1f}%")

    # ---- save everything ----
    np.save(OUTPUT_DIR / "X_train_scaled.npy", X_train_scaled)
    np.save(OUTPUT_DIR / "X_val_scaled.npy", X_val_scaled)
    np.save(OUTPUT_DIR / "X_test_scaled.npy", X_test_scaled)

    np.save(OUTPUT_DIR / "y1_train.npy", y1_train)
    np.save(OUTPUT_DIR / "y1_val.npy", y1_val)
    np.save(OUTPUT_DIR / "y1_test.npy", y1_test)

    np.save(OUTPUT_DIR / "y2_train.npy", y2_train)
    np.save(OUTPUT_DIR / "y2_val.npy", y2_val)
    np.save(OUTPUT_DIR / "y2_test.npy", y2_test)

    np.save(OUTPUT_DIR / "y3_train.npy", y3_train)
    np.save(OUTPUT_DIR / "y3_val.npy", y3_val)
    np.save(OUTPUT_DIR / "y3_test.npy", y3_test)

    np.save(OUTPUT_DIR / "health_train.npy", health_train)
    np.save(OUTPUT_DIR / "health_val.npy", health_val)
    np.save(OUTPUT_DIR / "health_test.npy", health_test)

    np.save(OUTPUT_DIR / "X_sim_scaled.npy", X_sim_scaled)
    np.save(OUTPUT_DIR / "y1_sim.npy", y1_sim)
    np.save(OUTPUT_DIR / "y2_sim.npy", y2_sim)
    np.save(OUTPUT_DIR / "y3_sim.npy", y3_sim)
    np.save(OUTPUT_DIR / "health_sim.npy", health_sim)

    with open(OUTPUT_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    metadata = {
        'created_at': datetime.now().isoformat(),
        'training_data_file': str(TRAINING_DATA_FILE),
        'simulation_file': str(PLANT_SIMULATION_FILE),
        'n_features': len(ALL_FEATURES),
        'feature_names': ALL_FEATURES,
        'sensor_features': SENSOR_FEATURES,
        'motor_features': MOTOR_FEATURES,
        'components': COMPONENTS,
        'component_to_idx': COMPONENT_TO_IDX,
        'train_size': len(train_idx),
        'val_size': len(val_idx),
        'test_size': len(test_idx),
        'sim_size': len(X_sim),
        'train_ratio': TRAIN_RATIO,
        'val_ratio': VAL_RATIO,
        'test_ratio': TEST_RATIO,
        'stage1_classes': ['NORMAL', 'ANOMALY'],
        'stage2_classes': ['ANOMALY', 'DEGRADING', 'FAULTED'],
        'stage3_classes': COMPONENTS,
    }
    with open(OUTPUT_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nDone. Saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
