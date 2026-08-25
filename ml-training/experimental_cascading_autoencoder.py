"""
An alternative, fully unsupervised design explored alongside the
supervised pipeline. Not what is deployed, the supervised 3 stage
pipeline (train_stage1/2/3) performed better and is what ships. Kept here
because it was a real part of the exploration and shows a different way
to attack the same problem.

Three autoencoders are chained, each trained on a different slice of the
state space:
  Stage 1: trained on NORMAL only, flags anything unusual at all.
  Stage 2: trained on ANOMALY and FAULTED, tries to isolate DEGRADING.
  Stage 3: trained on FAULTED only, tries to isolate ANOMALY.
Each stage's reconstruction error against its own 95th percentile
threshold is the trigger.
"""

import json
import pickle
import warnings
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import tensorflow as tf
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
from tensorflow import keras
from tensorflow.keras import callbacks, layers

warnings.filterwarnings('ignore')

try:
    from gpu_setup import setup_gpu
    setup_gpu()
except Exception:
    print("gpu_setup not available, using CPU")

from paths import HERE, PLANT_SIMULATION_FILE, TRAINING_DATA_FILE

np.random.seed(42)
tf.random.set_seed(42)

OUTPUT_DIR = HERE / "experimental_output"
MODEL_DIR = OUTPUT_DIR / "models"
RESULTS_DIR = OUTPUT_DIR / "results"
DATA_DIR = OUTPUT_DIR / "processed_data"
for d in (OUTPUT_DIR, MODEL_DIR, RESULTS_DIR, DATA_DIR):
    d.mkdir(parents=True, exist_ok=True)

TRAIN_RATIO, VAL_RATIO, TEST_RATIO = 0.6, 0.2, 0.2
BATCH_SIZE = 256
EPOCHS = 50
PATIENCE = 5

SENSOR_FEATURES = [
    'true_FIT101', 'true_FIT201', 'true_FIT301', 'true_FIT401', 'true_FIT501',
    'true_LIT101', 'true_LIT301', 'true_LIT401',
    'true_AIT201', 'true_AIT202', 'true_AIT203', 'true_AIT401', 'true_AIT402', 'true_AIT501',
    'true_DPIT301', 'true_PIT501',
]
PUMP_NAMES = ['P101', 'P201', 'P203', 'P205', 'P302', 'P402', 'P403', 'P501']
MOTOR_FEATURES = []
for pump in PUMP_NAMES:
    MOTOR_FEATURES.extend([f'true_{pump}_motor_temp', f'true_{pump}_current', f'true_{pump}_vibration'])
ALL_FEATURES = SENSOR_FEATURES + MOTOR_FEATURES

STATE_NAMES = ['NORMAL', 'ANOMALY', 'DEGRADING', 'FAULTED']
NORMAL, ANOMALY, DEGRADING, FAULTED = 0, 1, 2, 3


def get_state_label(row):
    if row['is_faulted'] == 1:
        return FAULTED
    if row['is_degrading'] == 1:
        return DEGRADING
    if row['is_anomaly'] == 1:
        return ANOMALY
    return NORMAL


def build_autoencoder(input_dim, name):
    """40 to 64 to 32 to 16 to 32 to 64 to 40."""
    input_layer = layers.Input(shape=(input_dim,), name="input")
    encoded = layers.Dense(64, activation='relu', name="encoder_64")(input_layer)
    encoded = layers.Dense(32, activation='relu', name="encoder_32")(encoded)
    encoded = layers.Dense(16, activation='relu', name="encoder_16")(encoded)
    decoded = layers.Dense(32, activation='relu', name="decoder_32")(encoded)
    decoded = layers.Dense(64, activation='relu', name="decoder_64")(decoded)
    output_layer = layers.Dense(input_dim, activation='linear', name="output")(decoded)
    model = keras.Model(input_layer, output_layer, name=name)
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return model


def train_autoencoder(X_subset, name, batch_size=BATCH_SIZE):
    model = build_autoencoder(input_dim=X_subset.shape[1], name=name)
    history = model.fit(
        X_subset, X_subset, epochs=EPOCHS, batch_size=min(batch_size, max(2, len(X_subset) // 2)),
        validation_split=0.2,
        callbacks=[
            callbacks.EarlyStopping(monitor='val_loss', patience=PATIENCE, restore_best_weights=True),
            callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3),
        ],
        verbose=0,
    )
    recon = model.predict(X_subset, verbose=0)
    errors = np.mean((X_subset - recon) ** 2, axis=1)
    threshold = np.percentile(errors, 95)
    print(f"{name}: {len(history.history['loss'])} epochs, threshold {threshold:.6f}")
    return model, threshold


def evaluate_binary(errors, threshold, y_true, stage_name, positive_label, results_dir):
    y_pred = (errors > threshold).astype(int)
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    print(f"{stage_name}: accuracy {acc:.4f}, precision {prec:.4f}, recall {rec:.4f}, f1 {f1:.4f}")

    cm = confusion_matrix(y_true, y_pred)
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt=',', cmap='Blues', ax=ax)
    ax.set_ylabel('Actual')
    ax.set_xlabel('Predicted')
    ax.set_title(stage_name)
    plt.tight_layout()
    safe_name = stage_name.lower().replace(' ', '_')
    plt.savefig(results_dir / f"{safe_name}_cm.png", dpi=150)
    plt.close()

    return {'stage': stage_name, 'accuracy': acc, 'precision': prec, 'recall': rec, 'f1': f1}


def main():
    print("Experimental cascading autoencoder pipeline")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    df = pd.read_csv(TRAINING_DATA_FILE)
    missing = [f for f in ALL_FEATURES if f not in df.columns]
    if missing:
        raise ValueError(f"Missing features: {missing}")

    df['state'] = df.apply(get_state_label, axis=1)

    n = len(df)
    train_size = int(TRAIN_RATIO * n)
    val_size = int(VAL_RATIO * n)
    train_idx = np.arange(0, train_size)
    test_idx = np.arange(train_size + val_size, n)

    X = df[ALL_FEATURES].values
    states = df['state'].values
    if np.isnan(X).sum() > 0:
        raise ValueError("NaN values in features")

    X_train, X_test = X[train_idx], X[test_idx]
    states_train, states_test = states[train_idx], states[test_idx]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    df_sim = pd.read_csv(PLANT_SIMULATION_FILE)
    df_sim['state'] = df_sim.apply(get_state_label, axis=1)
    X_sim = df_sim[ALL_FEATURES].values
    states_sim = df_sim['state'].values
    X_sim_scaled = scaler.transform(X_sim)

    with open(DATA_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    # ---- stage 1: trained on normal, flags any issue ----
    print("\nStage 1: training on NORMAL rows")
    mask_normal = (states_train == NORMAL)
    ae1, threshold1 = train_autoencoder(X_train_scaled[mask_normal], "stage1")
    ae1.save(MODEL_DIR / "stage1_autoencoder.keras")
    with open(MODEL_DIR / "stage1_threshold.pkl", "wb") as f:
        pickle.dump(threshold1, f)

    # ---- stage 2: trained on anomaly + faulted, isolates degrading ----
    print("\nStage 2: training on ANOMALY and FAULTED rows")
    mask_anom_fault = np.isin(states_train, [ANOMALY, FAULTED])
    ae2, threshold2 = train_autoencoder(X_train_scaled[mask_anom_fault], "stage2")
    ae2.save(MODEL_DIR / "stage2_autoencoder.keras")
    with open(MODEL_DIR / "stage2_threshold.pkl", "wb") as f:
        pickle.dump(threshold2, f)

    # ---- stage 3: trained on faulted, isolates anomaly ----
    print("\nStage 3: training on FAULTED rows")
    mask_faulted = (states_train == FAULTED)
    if mask_faulted.sum() < 100:
        print("Warning: very few FAULTED rows, this model may not train well")
    ae3, threshold3 = train_autoencoder(X_train_scaled[mask_faulted], "stage3")
    ae3.save(MODEL_DIR / "stage3_autoencoder.keras")
    with open(MODEL_DIR / "stage3_threshold.pkl", "wb") as f:
        pickle.dump(threshold3, f)

    # ---- evaluate ----
    def evaluate_all(X_scaled, states_true, label):
        print(f"\nEvaluating on {label}")
        results = []

        recon1 = ae1.predict(X_scaled, verbose=0)
        errors1 = np.mean((X_scaled - recon1) ** 2, axis=1)
        results.append(evaluate_binary(errors1, threshold1, (states_true > NORMAL).astype(int),
                                        f"Stage 1 {label}", "any issue", RESULTS_DIR))

        mask = (states_true > NORMAL)
        if mask.sum() > 0:
            X_f = X_scaled[mask]
            recon2 = ae2.predict(X_f, verbose=0)
            errors2 = np.mean((X_f - recon2) ** 2, axis=1)
            y_true2 = (states_true[mask] == DEGRADING).astype(int)
            results.append(evaluate_binary(errors2, threshold2, y_true2, f"Stage 2 {label}", "degrading", RESULTS_DIR))

        mask3 = np.isin(states_true, [ANOMALY, FAULTED])
        if mask3.sum() > 0:
            X_f3 = X_scaled[mask3]
            recon3 = ae3.predict(X_f3, verbose=0)
            errors3 = np.mean((X_f3 - recon3) ** 2, axis=1)
            y_true3 = (states_true[mask3] == ANOMALY).astype(int)
            results.append(evaluate_binary(errors3, threshold3, y_true3, f"Stage 3 {label}", "anomaly", RESULTS_DIR))

        return results

    results_train = evaluate_all(X_test_scaled, states_test, "training test split")
    results_sim = evaluate_all(X_sim_scaled, states_sim, "simulation set")

    pd.DataFrame(results_train).to_csv(RESULTS_DIR / "training_results.csv", index=False)
    pd.DataFrame(results_sim).to_csv(RESULTS_DIR / "simulation_results.csv", index=False)

    config = {
        'created_at': datetime.now().isoformat(),
        'architecture': '40 to 64 to 32 to 16 to 32 to 64 to 40',
        'n_features': len(ALL_FEATURES),
        'stages': {
            'stage1': {'train_on': 'NORMAL', 'threshold': float(threshold1)},
            'stage2': {'train_on': 'ANOMALY + FAULTED', 'threshold': float(threshold2)},
            'stage3': {'train_on': 'FAULTED', 'threshold': float(threshold3)},
        },
    }
    with open(MODEL_DIR / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nDone. Results in {RESULTS_DIR}")


if __name__ == "__main__":
    main()
