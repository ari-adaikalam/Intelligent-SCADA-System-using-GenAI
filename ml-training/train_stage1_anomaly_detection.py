"""
Stage 1: is this row normal or anomalous.

Trains three candidates and keeps whichever generalizes best from the
training set to the held-out simulation set.
  1. Autoencoder, unsupervised. Trained on normal rows only, flags
     anything whose reconstruction error passes a threshold learned
     from normal data.
  2. Isolation forest, unsupervised. Trained on all rows, isolates
     points that are easy to separate from the rest.
  3. XGBoost, supervised. Trained directly on the label.

Model selection favors recall (missing a real anomaly is worse than a
false alarm) and a small training vs simulation gap, since a model that
only works on the data it was trained on hasn't learned anything useful.
"""

import json
import pickle
import warnings
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import tensorflow as tf
import xgboost as xgb
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, precision_score,
    recall_score, roc_auc_score,
)
from sklearn.utils.class_weight import compute_sample_weight
from tensorflow import keras
from tensorflow.keras import callbacks, layers

warnings.filterwarnings('ignore')

from gpu_setup import get_xgb_params, setup_gpu
from paths import MODEL_DIR as MODEL_BASE, OUTPUT_DIR, RESULTS_DIR as RESULTS_BASE

setup_gpu()

np.random.seed(42)
tf.random.set_seed(42)

MODEL_DIR = MODEL_BASE / "stage1"
RESULTS_DIR = RESULTS_BASE / "stage1"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def build_autoencoder(input_dim=40):
    """Symmetric bottleneck: input, 64, 32, 16, 32, 64, input."""
    input_layer = layers.Input(shape=(input_dim,))
    encoded = layers.Dense(64, activation='relu')(input_layer)
    encoded = layers.Dense(32, activation='relu')(encoded)
    encoded = layers.Dense(16, activation='relu')(encoded)

    decoded = layers.Dense(32, activation='relu')(encoded)
    decoded = layers.Dense(64, activation='relu')(decoded)
    output_layer = layers.Dense(input_dim, activation='linear')(decoded)

    model = keras.Model(input_layer, output_layer)
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return model


def evaluate_model(X, y_true, model_name, model_type, dataset_name, models, thresholds, results_dir):
    print(f"\nEvaluating {model_name} on {dataset_name}")

    if model_type == 'autoencoder':
        recon = models['autoencoder'].predict(X, verbose=0)
        errors = np.mean((X - recon) ** 2, axis=1)
        y_pred = (errors > thresholds['autoencoder']).astype(int)
        y_score = (errors - errors.min()) / (errors.max() - errors.min())

    elif model_type == 'iforest':
        y_pred_raw = models['iforest'].predict(X)
        y_pred = (y_pred_raw == -1).astype(int)
        y_score = -models['iforest'].score_samples(X)
        y_score = (y_score - y_score.min()) / (y_score.max() - y_score.min())

    else:  # xgboost
        y_pred = models['xgboost'].predict(X)
        y_score = models['xgboost'].predict_proba(X)[:, 1]

    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    try:
        roc_auc = roc_auc_score(y_true, y_score)
    except Exception:
        roc_auc = 0.0

    print(f"Accuracy {acc:.4f}  Precision {prec:.4f}  Recall {rec:.4f}  F1 {f1:.4f}  ROC-AUC {roc_auc:.4f}")

    cm = confusion_matrix(y_true, y_pred)
    fn, fp = cm[1, 0], cm[0, 1]
    print(f"Missed anomalies: {fn:,}   False alarms: {fp:,}")

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt=',', cmap='Blues', ax=ax,
                xticklabels=['NORMAL', 'ANOMALY'], yticklabels=['NORMAL', 'ANOMALY'])
    ax.set_ylabel('Actual')
    ax.set_xlabel('Predicted')
    ax.set_title(f'{model_name} on {dataset_name}')
    plt.tight_layout()
    plt.savefig(results_dir / f"{model_type}_{dataset_name.lower()}_cm.png", dpi=150)
    plt.close()

    return {
        'model_name': model_name, 'dataset': dataset_name, 'accuracy': acc,
        'precision': prec, 'recall': rec, 'f1': f1, 'roc_auc': roc_auc,
        'false_negatives': int(fn), 'false_positives': int(fp), 'cm': cm,
    }


def main():
    print("Stage 1 training: anomaly detection")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    X_train = np.load(OUTPUT_DIR / "X_train_scaled.npy")
    X_val = np.load(OUTPUT_DIR / "X_val_scaled.npy")
    X_test = np.load(OUTPUT_DIR / "X_test_scaled.npy")
    y_train = np.load(OUTPUT_DIR / "y1_train.npy")
    y_val = np.load(OUTPUT_DIR / "y1_val.npy")
    y_test = np.load(OUTPUT_DIR / "y1_test.npy")

    print(f"Train {X_train.shape}, anomaly rate {y_train.mean() * 100:.1f}%")

    X_sim = np.load(OUTPUT_DIR / "X_sim_scaled.npy")
    y_sim = np.load(OUTPUT_DIR / "y1_sim.npy")
    print(f"Simulation {X_sim.shape}, anomaly rate {y_sim.mean() * 100:.1f}%")

    # ---- autoencoder ----
    print("\nTraining the autoencoder (unsupervised)")
    X_train_normal = X_train[y_train == 0]
    autoencoder = build_autoencoder(input_dim=X_train.shape[1])
    history_ae = autoencoder.fit(
        X_train_normal, X_train_normal,
        epochs=50, batch_size=256, validation_split=0.2,
        callbacks=[
            callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True),
            callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3),
        ],
        verbose=0,
    )
    print(f"Best epoch: {len(history_ae.history['loss']) - 5}")

    train_recon = autoencoder.predict(X_train_normal, verbose=0)
    train_errors = np.mean((X_train_normal - train_recon) ** 2, axis=1)
    threshold_ae = np.percentile(train_errors, 95)

    autoencoder.save(MODEL_DIR / "autoencoder.keras")
    with open(MODEL_DIR / "autoencoder_threshold.pkl", "wb") as f:
        pickle.dump(threshold_ae, f)

    # ---- isolation forest ----
    print("\nTraining isolation forest (unsupervised)")
    iforest = IsolationForest(n_estimators=100, contamination='auto', random_state=42, n_jobs=-1)
    iforest.fit(X_train)
    with open(MODEL_DIR / "isolation_forest.pkl", "wb") as f:
        pickle.dump(iforest, f)

    # ---- xgboost ----
    print("\nTraining XGBoost (supervised)")
    sample_weights = compute_sample_weight('balanced', y_train)
    scale_pos_weight = len(y_train[y_train == 0]) / len(y_train[y_train == 1])

    xgb_model = xgb.XGBClassifier(**get_xgb_params({
        'n_estimators': 200, 'max_depth': 10, 'learning_rate': 0.1,
        'subsample': 0.8, 'colsample_bytree': 0.8,
        'scale_pos_weight': scale_pos_weight, 'random_state': 42,
        'n_jobs': -1, 'eval_metric': 'logloss',
    }))
    xgb_model.fit(X_train, y_train, sample_weight=sample_weights, eval_set=[(X_val, y_val)], verbose=False)

    with open(MODEL_DIR / "xgboost.pkl", "wb") as f:
        pickle.dump(xgb_model, f)

    models = {'autoencoder': autoencoder, 'iforest': iforest, 'xgboost': xgb_model}
    thresholds = {'autoencoder': threshold_ae}

    # ---- evaluate ----
    print("\nEvaluating on the training set")
    results_train = [
        evaluate_model(X_test, y_test, "Autoencoder", "autoencoder", "Training", models, thresholds, RESULTS_DIR),
        evaluate_model(X_test, y_test, "Isolation Forest", "iforest", "Training", models, thresholds, RESULTS_DIR),
        evaluate_model(X_test, y_test, "XGBoost", "xgboost", "Training", models, thresholds, RESULTS_DIR),
    ]

    print("\nEvaluating on the simulation set")
    results_sim = [
        evaluate_model(X_sim, y_sim, "Autoencoder", "autoencoder", "Simulation", models, thresholds, RESULTS_DIR),
        evaluate_model(X_sim, y_sim, "Isolation Forest", "iforest", "Simulation", models, thresholds, RESULTS_DIR),
        evaluate_model(X_sim, y_sim, "XGBoost", "xgboost", "Simulation", models, thresholds, RESULTS_DIR),
    ]

    # ---- pick the best model ----
    combined_scores = []
    for i in range(3):
        avg_recall = (results_train[i]['recall'] + results_sim[i]['recall']) / 2
        gap = abs(results_train[i]['recall'] - results_sim[i]['recall'])
        score = avg_recall - (gap * 0.5)
        combined_scores.append(score)
        print(f"{results_train[i]['model_name']}: avg recall {avg_recall:.4f}, gap penalty {gap * 0.5:.4f}, score {score:.4f}")

    best_idx = int(np.argmax(combined_scores))
    best_model_name = results_train[best_idx]['model_name']
    print(f"\nBest model: {best_model_name}")

    pd.DataFrame(results_train).to_csv(RESULTS_DIR / "training_results.csv", index=False)
    pd.DataFrame(results_sim).to_csv(RESULTS_DIR / "simulation_results.csv", index=False)

    final_config = {
        'stage': 1,
        'task': 'Binary anomaly detection',
        'best_model': best_model_name,
        'best_model_type': ['autoencoder', 'iforest', 'xgboost'][best_idx],
        'training_performance': results_train[best_idx],
        'simulation_performance': results_sim[best_idx],
        'trained_at': datetime.now().isoformat(),
        'num_features': X_train.shape[1],
    }
    with open(MODEL_DIR / "final_config.json", "w") as f:
        json.dump(final_config, f, indent=2, default=str)

    print(f"\nStage 1 done. Models in {MODEL_DIR}, results in {RESULTS_DIR}")


if __name__ == "__main__":
    main()
