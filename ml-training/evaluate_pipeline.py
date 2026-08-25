"""
Loads the best model from each stage and runs the full pipeline end to
end: anomaly detection, then state classification on whatever Stage 1
flagged, then component identification on whatever Stage 2 classified.
Reports accuracy at each stage plus how much error compounds from one
stage to the next.
"""

import json
import warnings
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pickle
import tensorflow as tf
from sklearn.metrics import accuracy_score, confusion_matrix
from tensorflow import keras

warnings.filterwarnings('ignore')

from gpu_setup import setup_gpu
from paths import MODEL_DIR, OUTPUT_DIR, RESULTS_DIR as RESULTS_BASE

setup_gpu()

np.random.seed(42)
tf.random.set_seed(42)

RESULTS_DIR = RESULTS_BASE / "full_pipeline"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

STATE_NAMES = ['ANOMALY', 'DEGRADING', 'FAULTED']


def load_stage_model(stage_dir, best_type):
    if best_type in ('autoencoder', 'dae'):
        model = keras.models.load_model(stage_dir / f"{best_type}.keras", compile=False)
        with open(stage_dir / f"{best_type}_threshold.pkl", "rb") as f:
            threshold = pickle.load(f)
        return model, threshold
    if best_type == 'iforest':
        with open(stage_dir / "isolation_forest.pkl", "rb") as f:
            return pickle.load(f), None
    if best_type in ('lstm', 'cnn'):
        return keras.models.load_model(stage_dir / f"{best_type}.keras"), None
    if best_type == 'mlp':
        return keras.models.load_model(stage_dir / "mlp.keras"), None
    if best_type == 'lightgbm':
        with open(stage_dir / "lightgbm.pkl", "rb") as f:
            return pickle.load(f), None
    with open(stage_dir / "xgboost.pkl", "rb") as f:
        return pickle.load(f), None


def main():
    print("Full pipeline evaluation")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with open(OUTPUT_DIR / "metadata.json", "r") as f:
        metadata = json.load(f)

    with open(MODEL_DIR / "stage1" / "final_config.json", "r") as f:
        config1 = json.load(f)
    with open(MODEL_DIR / "stage2" / "final_config.json", "r") as f:
        config2 = json.load(f)
    with open(MODEL_DIR / "stage3" / "final_config.json", "r") as f:
        config3 = json.load(f)

    best_s1, best_s2, best_s3 = config1['best_model_type'], config2['best_model_type'], config3['best_model_type']
    print(f"Stage 1: {config1['best_model']}  Stage 2: {config2['best_model']}  Stage 3: {config3['best_model']}")

    model_s1, threshold_s1 = load_stage_model(MODEL_DIR / "stage1", best_s1)
    model_s2, _ = load_stage_model(MODEL_DIR / "stage2", best_s2)
    model_s3, _ = load_stage_model(MODEL_DIR / "stage3", best_s3)
    seq_length_s2 = config2.get("sequence_length", 60) if best_s2 in ("lstm", "cnn") else None

    X_test = np.load(OUTPUT_DIR / "X_test_scaled.npy")
    y1_test = np.load(OUTPUT_DIR / "y1_test.npy")
    y2_test = np.load(OUTPUT_DIR / "y2_test.npy")
    y3_test = np.load(OUTPUT_DIR / "y3_test.npy")

    X_sim = np.load(OUTPUT_DIR / "X_sim_scaled.npy")
    y1_sim = np.load(OUTPUT_DIR / "y1_sim.npy")
    y2_sim = np.load(OUTPUT_DIR / "y2_sim.npy")
    y3_sim = np.load(OUTPUT_DIR / "y3_sim.npy")

    def predict_stage1(X):
        if best_s1 in ('autoencoder', 'dae'):
            recon = model_s1.predict(X, verbose=0, batch_size=1024)
            errors = np.mean((X - recon) ** 2, axis=1)
            return (errors > threshold_s1).astype(int)
        if best_s1 == 'iforest':
            return (model_s1.predict(X) == -1).astype(int)
        return model_s1.predict(X)

    def predict_stage2(X, s1_pred):
        """Only classifies the rows Stage 1 flagged as anomalous."""
        anomaly_mask = (s1_pred == 1)
        s2_pred = np.full(len(X), -1, dtype=np.int32)
        if anomaly_mask.sum() == 0:
            return s2_pred

        if seq_length_s2 and best_s2 in ('lstm', 'cnn'):
            ds = tf.keras.utils.timeseries_dataset_from_array(
                data=X.astype(np.float32, copy=False), targets=None,
                sequence_length=seq_length_s2, sequence_stride=1,
                sampling_rate=1, batch_size=256, shuffle=False,
            )
            pred_seq = model_s2.predict(ds, verbose=0).argmax(axis=1)
            n = len(pred_seq)
            end = min(len(X), seq_length_s2 + n)
            s2_pred[seq_length_s2:end] = pred_seq[:end - seq_length_s2]
            s2_pred[~anomaly_mask] = -1
        else:
            s2_pred[anomaly_mask] = model_s2.predict(X[anomaly_mask])

        return s2_pred

    def predict_stage3(X, s2_pred):
        """Only classifies the rows Stage 2 already classified."""
        classified_mask = (s2_pred >= 0)
        s3_pred = np.full(len(X), -1, dtype=np.int32)
        if classified_mask.sum() == 0:
            return s3_pred

        X_classified = X[classified_mask]
        if best_s3 == 'mlp':
            pred = model_s3.predict(X_classified, verbose=0, batch_size=1024).argmax(axis=1)
        else:
            pred = model_s3.predict(X_classified)
        s3_pred[classified_mask] = pred
        return s3_pred

    def run_pipeline(X, y1, y2, y3, label):
        print(f"\nRunning the pipeline on {label}")
        s1_pred = predict_stage1(X)
        s1_acc = accuracy_score(y1, s1_pred)
        print(f"Stage 1 accuracy: {s1_acc:.4f}")

        s2_pred = predict_stage2(X, s1_pred)
        s2_mask = (y2 >= 0) & (s2_pred >= 0)
        s2_acc = accuracy_score(y2[s2_mask], s2_pred[s2_mask]) if s2_mask.sum() > 0 else None
        if s2_acc is not None:
            print(f"Stage 2 accuracy: {s2_acc:.4f} (on {s2_mask.sum():,} rows)")

        s3_pred = predict_stage3(X, s2_pred)
        s3_mask = (y3 >= 0) & (s3_pred >= 0)
        s3_acc = accuracy_score(y3[s3_mask], s3_pred[s3_mask]) if s3_mask.sum() > 0 else None
        if s3_acc is not None:
            print(f"Stage 3 accuracy: {s3_acc:.4f} (on {s3_mask.sum():,} rows)")

        s1_error = (s1_pred != y1).mean()
        s2_error = (s2_pred[s2_mask] != y2[s2_mask]).mean() if s2_mask.sum() > 0 else None
        s3_error = (s3_pred[s3_mask] != y3[s3_mask]).mean() if s3_mask.sum() > 0 else None

        return {
            'stage1_accuracy': s1_acc, 'stage2_accuracy': s2_acc, 'stage3_accuracy': s3_acc,
            'stage1_error': s1_error, 'stage2_error': s2_error, 'stage3_error': s3_error,
        }

    results_train = run_pipeline(X_test, y1_test, y2_test, y3_test, "the training test split")
    results_sim = run_pipeline(X_sim, y1_sim, y2_sim, y3_sim, "the simulation set")

    # ---- comparison table and chart ----
    comparison_rows = []
    for stage, train_key, sim_key in [
        ('Stage 1 (anomaly)', 'stage1_accuracy', 'stage1_accuracy'),
        ('Stage 2 (state)', 'stage2_accuracy', 'stage2_accuracy'),
        ('Stage 3 (component)', 'stage3_accuracy', 'stage3_accuracy'),
    ]:
        train_val, sim_val = results_train[train_key], results_sim[sim_key]
        if train_val is not None and sim_val is not None:
            comparison_rows.append({
                'Stage': stage, 'Training': train_val, 'Simulation': sim_val,
                'Gap': abs(train_val - sim_val),
            })

    df_comparison = pd.DataFrame(comparison_rows)
    print("\n" + df_comparison.to_string(index=False))
    df_comparison.to_csv(RESULTS_DIR / "performance_comparison.csv", index=False)

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(df_comparison))
    width = 0.35
    ax.bar(x - width / 2, df_comparison['Training'], width, label='Training', color='skyblue')
    ax.bar(x + width / 2, df_comparison['Simulation'], width, label='Simulation', color='lightcoral')
    ax.set_xlabel('Pipeline stage')
    ax.set_ylabel('Accuracy')
    ax.set_title('Pipeline accuracy: training vs simulation')
    ax.set_xticks(x)
    ax.set_xticklabels(df_comparison['Stage'], rotation=15, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "performance_comparison.png", dpi=150)
    plt.close()

    report = {
        'evaluated_at': datetime.now().isoformat(),
        'models': {'stage1': config1['best_model'], 'stage2': config2['best_model'], 'stage3': config3['best_model']},
        'training': results_train,
        'simulation': results_sim,
    }
    with open(RESULTS_DIR / "final_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nDone. Results in {RESULTS_DIR}")


if __name__ == "__main__":
    main()
