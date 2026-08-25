"""
Stage 2: which state is this, anomaly, degrading, or faulted.

Only runs on rows Stage 1 already flagged as anomalous, normal rows are
filtered out. Trains three candidates:
  1. XGBoost, tabular, multi class.
  2. LSTM, 60 step sequences (10 minutes of history at 10 second steps).
  3. 1D CNN, same sequences, pattern matching instead of recurrence.

Model selection favors F1 macro (there is real class imbalance here) and
specifically the anomaly vs degrading confusion rate, since those two are
hardest to tell apart early in a degradation episode.
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
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    f1_score, precision_score, recall_score,
)
from tensorflow import keras
from tensorflow.keras import callbacks, layers

warnings.filterwarnings('ignore')

from gpu_setup import get_xgb_params, setup_gpu
from paths import MODEL_DIR as MODEL_BASE, OUTPUT_DIR, RESULTS_DIR as RESULTS_BASE

setup_gpu()

np.random.seed(42)
tf.random.set_seed(42)

MODEL_DIR = MODEL_BASE / "stage2"
RESULTS_DIR = RESULTS_BASE / "stage2"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

STATE_NAMES = ['ANOMALY', 'DEGRADING', 'FAULTED']
NUM_CLASSES = 3
SEQ_LENGTH = 60   # 60 steps = 10 minutes of history
BATCH_SIZE = 128


def build_lstm_model(input_shape, num_classes=3):
    model = keras.Sequential([
        layers.LSTM(128, return_sequences=True, input_shape=input_shape),
        layers.Dropout(0.2),
        layers.LSTM(64),
        layers.Dropout(0.2),
        layers.Dense(32, activation='relu'),
        layers.Dense(num_classes, activation='softmax'),
    ])
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    return model


def build_cnn_model(input_shape, num_classes=3):
    model = keras.Sequential([
        layers.Input(shape=input_shape),
        layers.Conv1D(64, 3, activation='relu', padding="same"),
        layers.MaxPooling1D(2),
        layers.Conv1D(128, 3, activation='relu', padding="same"),
        layers.MaxPooling1D(2),
        layers.GlobalAveragePooling1D(),
        layers.Dense(64, activation='relu'),
        layers.Dropout(0.3),
        layers.Dense(num_classes, activation='softmax'),
    ])
    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])
    return model


def make_seq_ds(X, y, seq_length=60, batch_size=128, shuffle=False):
    """Streams (batch, seq_length, features) windows via tf.data instead
    of building every window in memory up front."""
    X = X.astype(np.float32, copy=False)
    y = y.astype(np.int32, copy=False)
    return tf.keras.utils.timeseries_dataset_from_array(
        data=X, targets=y[seq_length:], sequence_length=seq_length,
        sequence_stride=1, sampling_rate=1, batch_size=batch_size, shuffle=shuffle,
    )


def evaluate_model(model, model_name, dataset_name, results_dir,
                    X=None, y_true=None, use_sequences=False, ds=None, y_true_eval=None):
    print(f"\nEvaluating {model_name} on {dataset_name}")

    if use_sequences:
        y_pred = model.predict(ds, verbose=0).argmax(axis=1)
    else:
        y_pred = model.predict(X)
        y_true_eval = y_true

    acc = accuracy_score(y_true_eval, y_pred)
    f1_macro = f1_score(y_true_eval, y_pred, average='macro', zero_division=0)
    f1_weighted = f1_score(y_true_eval, y_pred, average='weighted', zero_division=0)
    print(f"Accuracy {acc:.4f}  F1 macro {f1_macro:.4f}  F1 weighted {f1_weighted:.4f}")

    for i, name in enumerate(STATE_NAMES):
        if (y_true_eval == i).sum() == 0:
            continue
        prec = precision_score(y_true_eval == i, y_pred == i, zero_division=0)
        rec = recall_score(y_true_eval == i, y_pred == i, zero_division=0)
        f1 = f1_score(y_true_eval == i, y_pred == i, zero_division=0)
        print(f"   {name:10s}: precision {prec:.4f}, recall {rec:.4f}, f1 {f1:.4f}")

    cm = confusion_matrix(y_true_eval, y_pred)
    confusion_rate = 0
    if cm.shape[0] >= 2:
        anom_degr_confusion = cm[0, 1] + cm[1, 0]
        total_anom_degr = cm[0, :].sum() + cm[1, :].sum()
        confusion_rate = anom_degr_confusion / total_anom_degr if total_anom_degr > 0 else 0
        print(f"Anomaly vs degrading confusion: {anom_degr_confusion:,} ({100 * confusion_rate:.1f}%)")

    print(classification_report(y_true_eval, y_pred, target_names=STATE_NAMES, zero_division=0))

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt=',', cmap='Blues', ax=ax, xticklabels=STATE_NAMES, yticklabels=STATE_NAMES)
    ax.set_ylabel('Actual')
    ax.set_xlabel('Predicted')
    ax.set_title(f'{model_name} on {dataset_name}')
    plt.tight_layout()
    model_type = model_name.lower().replace(' ', '_').replace('-', '')
    plt.savefig(results_dir / f"{model_type}_{dataset_name.lower()}_cm.png", dpi=150)
    plt.close()

    return {
        'model_name': model_name, 'dataset': dataset_name, 'accuracy': acc,
        'f1_macro': f1_macro, 'f1_weighted': f1_weighted,
        'confusion_matrix': cm.tolist(), 'confusion_rate': confusion_rate,
    }


def main():
    print("Stage 2 training: state classification")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    X_train = np.load(OUTPUT_DIR / "X_train_scaled.npy")
    X_val = np.load(OUTPUT_DIR / "X_val_scaled.npy")
    X_test = np.load(OUTPUT_DIR / "X_test_scaled.npy")
    y_train_full = np.load(OUTPUT_DIR / "y2_train.npy")
    y_val_full = np.load(OUTPUT_DIR / "y2_val.npy")
    y_test_full = np.load(OUTPUT_DIR / "y2_test.npy")

    # Drop normal rows (label -1), Stage 2 only classifies already anomalous rows.
    X_train_s2 = X_train[y_train_full >= 0]
    y_train = y_train_full[y_train_full >= 0]
    X_val_s2 = X_val[y_val_full >= 0]
    y_val = y_val_full[y_val_full >= 0]
    X_test_s2 = X_test[y_test_full >= 0]
    y_test = y_test_full[y_test_full >= 0]

    print(f"Train {X_train_s2.shape}, val {X_val_s2.shape}, test {X_test_s2.shape}")

    X_sim = np.load(OUTPUT_DIR / "X_sim_scaled.npy")
    y_sim_full = np.load(OUTPUT_DIR / "y2_sim.npy")
    X_sim_s2 = X_sim[y_sim_full >= 0]
    y_sim = y_sim_full[y_sim_full >= 0]

    # ---- xgboost ----
    print("\nTraining XGBoost (multi class)")
    xgb_model = xgb.XGBClassifier(**get_xgb_params({
        'objective': 'multi:softmax', 'num_class': NUM_CLASSES,
        'n_estimators': 200, 'max_depth': 4, 'min_child_weight': 5, 'gamma': 0.2,
        'learning_rate': 0.1, 'subsample': 0.8, 'colsample_bytree': 0.8,
        'random_state': 42, 'n_jobs': -1,
    }))
    class_weight = {0: 1.2, 1: 1.0, 2: 1.1}  # anomaly, degrading, faulted
    sample_weight = np.array([class_weight[int(y)] for y in y_train])
    xgb_model.fit(X_train_s2, y_train, eval_set=[(X_val_s2, y_val)], sample_weight=sample_weight, verbose=False)
    with open(MODEL_DIR / "xgboost.pkl", "wb") as f:
        pickle.dump(xgb_model, f)

    # ---- sequence datasets for LSTM and CNN ----
    train_ds = make_seq_ds(X_train_s2, y_train, SEQ_LENGTH, BATCH_SIZE, shuffle=True)
    val_ds = make_seq_ds(X_val_s2, y_val, SEQ_LENGTH, BATCH_SIZE, shuffle=False)
    test_ds = make_seq_ds(X_test_s2, y_test, SEQ_LENGTH, BATCH_SIZE, shuffle=False)
    sim_ds = make_seq_ds(X_sim_s2, y_sim, SEQ_LENGTH, BATCH_SIZE, shuffle=False)

    # ---- lstm ----
    print("\nTraining LSTM")
    lstm_model = build_lstm_model(input_shape=(SEQ_LENGTH, X_train_s2.shape[1]), num_classes=NUM_CLASSES)
    lstm_model.fit(
        train_ds, epochs=30, validation_data=val_ds,
        callbacks=[
            callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True),
            callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3),
        ],
        verbose=0,
    )
    lstm_model.save(MODEL_DIR / "lstm.keras")

    # ---- 1d cnn ----
    print("\nTraining 1D CNN")
    cnn_model = build_cnn_model(input_shape=(SEQ_LENGTH, X_train_s2.shape[1]), num_classes=NUM_CLASSES)
    cnn_model.fit(
        train_ds, epochs=30, validation_data=val_ds,
        callbacks=[
            callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True),
            callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3),
        ],
        verbose=0,
    )
    cnn_model.save(MODEL_DIR / "cnn.keras")

    # ---- evaluate ----
    print("\nEvaluating on the training set")
    results_train = [
        evaluate_model(xgb_model, "XGBoost", "Training", RESULTS_DIR, X=X_test_s2, y_true=y_test),
        evaluate_model(lstm_model, "LSTM", "Training", RESULTS_DIR, use_sequences=True, ds=test_ds,
                        y_true_eval=y_test[SEQ_LENGTH:]),
        evaluate_model(cnn_model, "1D-CNN", "Training", RESULTS_DIR, use_sequences=True, ds=test_ds,
                        y_true_eval=y_test[SEQ_LENGTH:]),
    ]

    print("\nEvaluating on the simulation set")
    results_sim = [
        evaluate_model(xgb_model, "XGBoost", "Simulation", RESULTS_DIR, X=X_sim_s2, y_true=y_sim),
        evaluate_model(lstm_model, "LSTM", "Simulation", RESULTS_DIR, use_sequences=True, ds=sim_ds,
                        y_true_eval=y_sim[SEQ_LENGTH:]),
        evaluate_model(cnn_model, "1D-CNN", "Simulation", RESULTS_DIR, use_sequences=True, ds=sim_ds,
                        y_true_eval=y_sim[SEQ_LENGTH:]),
    ]

    # ---- pick the best model ----
    combined_scores = []
    for i in range(3):
        avg_f1 = (results_train[i]['f1_macro'] + results_sim[i]['f1_macro']) / 2
        gap = abs(results_train[i]['f1_macro'] - results_sim[i]['f1_macro'])
        confusion_penalty = results_train[i]['confusion_rate'] * 0.3
        score = avg_f1 - (gap * 0.5) - confusion_penalty
        combined_scores.append(score)
        print(f"{results_train[i]['model_name']}: avg f1 {avg_f1:.4f}, gap penalty {gap * 0.5:.4f}, "
              f"confusion penalty {confusion_penalty:.4f}, score {score:.4f}")

    best_idx = int(np.argmax(combined_scores))
    best_model_name = results_train[best_idx]['model_name']
    print(f"\nBest model: {best_model_name}")

    pd.DataFrame(results_train).to_csv(RESULTS_DIR / "training_results.csv", index=False)
    pd.DataFrame(results_sim).to_csv(RESULTS_DIR / "simulation_results.csv", index=False)

    final_config = {
        'stage': 2,
        'task': 'State classification, 3 classes',
        'classes': STATE_NAMES,
        'best_model': best_model_name,
        'best_model_type': ['xgboost', 'lstm', 'cnn'][best_idx],
        'sequence_length': SEQ_LENGTH if best_idx > 0 else None,
        'training_performance': results_train[best_idx],
        'simulation_performance': results_sim[best_idx],
        'trained_at': datetime.now().isoformat(),
    }
    with open(MODEL_DIR / "final_config.json", "w") as f:
        json.dump(final_config, f, indent=2, default=str)

    print(f"\nStage 2 done. Models in {MODEL_DIR}, results in {RESULTS_DIR}")


if __name__ == "__main__":
    main()
