"""
Stage 3: which of the 10 pumps and valves is actually responsible.

Trains three candidates: LightGBM, an MLP (tracking top-3 accuracy during
training), and XGBoost. Model selection favors accuracy plus a bonus for
correctly telling apart P201, P203, and P205, which all read the same
shared FIT201 sensor and are the hardest components to separate.

Training labels get 5% random label noise (inject_label_noise) so the
models don't just overfit to the simulator's very clean ground truth, a
stand-in for the labeling uncertainty a real fault log would have.
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
import lightgbm as lgb
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    f1_score, precision_score, recall_score, top_k_accuracy_score,
)
from tensorflow import keras
from tensorflow.keras import callbacks, layers

warnings.filterwarnings('ignore')

from gpu_setup import get_lgb_params, get_xgb_params, setup_gpu
from paths import MODEL_DIR as MODEL_BASE, OUTPUT_DIR, RESULTS_DIR as RESULTS_BASE

setup_gpu()

np.random.seed(42)
tf.random.set_seed(42)

MODEL_DIR = MODEL_BASE / "stage3"
RESULTS_DIR = RESULTS_BASE / "stage3"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

COMPONENTS = ['P101', 'P201', 'P203', 'P205', 'P302', 'P402', 'P403', 'P501', 'MV101', 'MV304']
NUM_CLASSES = len(COMPONENTS)
SHARED_SENSOR_COMPS = ['P201', 'P203', 'P205']  # share FIT201, hardest to tell apart


def inject_label_noise(y, noise_rate=0.05):
    """Randomly relabels noise_rate of samples so the model can't just
    memorize a perfectly clean synthetic label distribution."""
    y = y.copy()
    n = len(y)
    k = int(n * noise_rate)
    idx = np.random.choice(n, k, replace=False)
    y[idx] = np.random.randint(0, y.max() + 1, size=k)
    return y


def build_mlp_model(input_dim, num_classes=10):
    model = keras.Sequential([
        layers.Input(shape=(input_dim,)),
        layers.Dense(128, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.3),
        layers.Dense(64, activation='relu'),
        layers.Dropout(0.3),
        layers.Dense(32, activation='relu'),
        layers.Dense(num_classes, activation='softmax'),
    ])
    model.compile(
        optimizer='adam', loss='sparse_categorical_crossentropy',
        metrics=['accuracy', keras.metrics.SparseTopKCategoricalAccuracy(k=3, name='top3_acc')],
    )
    return model


def evaluate_model(X, y_true, model, model_name, dataset_name, results_dir):
    print(f"\nEvaluating {model_name} on {dataset_name}")

    if hasattr(model, 'predict_proba'):
        y_pred = model.predict(X)
        y_proba = model.predict_proba(X)
    else:
        y_proba = model.predict(X, verbose=0)
        y_pred = y_proba.argmax(axis=1)

    acc = accuracy_score(y_true, y_pred)
    f1_macro = f1_score(y_true, y_pred, average='macro', zero_division=0)
    f1_weighted = f1_score(y_true, y_pred, average='weighted', zero_division=0)
    top3_acc = top_k_accuracy_score(y_true, y_proba, k=3)
    print(f"Accuracy {acc:.4f}  Top-3 {top3_acc:.4f}  F1 macro {f1_macro:.4f}  F1 weighted {f1_weighted:.4f}")

    shared_indices = [COMPONENTS.index(c) for c in SHARED_SENSOR_COMPS]
    shared_mask = np.isin(y_true, shared_indices)
    shared_acc = 0.0
    if shared_mask.sum() > 0:
        shared_acc = accuracy_score(y_true[shared_mask], y_pred[shared_mask])
        print(f"Shared sensor accuracy (P201/P203/P205): {shared_acc:.4f}")

    for i, comp in enumerate(COMPONENTS):
        mask = (y_true == i)
        if mask.sum() == 0:
            continue
        prec = precision_score(y_true == i, y_pred == i, zero_division=0)
        rec = recall_score(y_true == i, y_pred == i, zero_division=0)
        f1 = f1_score(y_true == i, y_pred == i, zero_division=0)
        print(f"   {comp:6s}: precision {prec:.4f}, recall {rec:.4f}, f1 {f1:.4f} (n={mask.sum():,})")

    cm = confusion_matrix(y_true, y_pred, labels=range(NUM_CLASSES))
    print(classification_report(y_true, y_pred, target_names=COMPONENTS, zero_division=0))

    fig, ax = plt.subplots(figsize=(12, 10))
    sns.heatmap(cm, annot=True, fmt=',', cmap='Blues', ax=ax, xticklabels=COMPONENTS, yticklabels=COMPONENTS)
    ax.set_ylabel('Actual')
    ax.set_xlabel('Predicted')
    ax.set_title(f'{model_name} on {dataset_name}')
    plt.tight_layout()
    model_type = model_name.lower().replace(' ', '_')
    plt.savefig(results_dir / f"{model_type}_{dataset_name.lower()}_cm.png", dpi=150)
    plt.close()

    return {
        'model_name': model_name, 'dataset': dataset_name, 'accuracy': acc,
        'top3_accuracy': top3_acc, 'f1_macro': f1_macro, 'f1_weighted': f1_weighted,
        'shared_sensor_acc': shared_acc, 'confusion_matrix': cm.tolist(),
    }


def main():
    print("Stage 3 training: component identification")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    X_train = np.load(OUTPUT_DIR / "X_train_scaled.npy")
    X_val = np.load(OUTPUT_DIR / "X_val_scaled.npy")
    X_test = np.load(OUTPUT_DIR / "X_test_scaled.npy")

    y_train_full = inject_label_noise(np.load(OUTPUT_DIR / "y3_train.npy"), noise_rate=0.05)
    y_val_full = np.load(OUTPUT_DIR / "y3_val.npy")
    y_test_full = np.load(OUTPUT_DIR / "y3_test.npy")

    X_train_s3 = X_train[y_train_full >= 0]
    y_train = y_train_full[y_train_full >= 0]
    X_val_s3 = X_val[y_val_full >= 0]
    y_val = y_val_full[y_val_full >= 0]
    X_test_s3 = X_test[y_test_full >= 0]
    y_test = y_test_full[y_test_full >= 0]

    print(f"Train {X_train_s3.shape}, val {X_val_s3.shape}, test {X_test_s3.shape}")

    X_sim = np.load(OUTPUT_DIR / "X_sim_scaled.npy")
    y_sim_full = np.load(OUTPUT_DIR / "y3_sim.npy")
    X_sim_s3 = X_sim[y_sim_full >= 0]
    y_sim = y_sim_full[y_sim_full >= 0]

    # ---- lightgbm ----
    print("\nTraining LightGBM")
    lgb_model = lgb.LGBMClassifier(**get_lgb_params({
        'objective': 'multiclass', 'num_class': NUM_CLASSES,
        'n_estimators': 200, 'max_depth': 10, 'learning_rate': 0.1,
        'num_leaves': 31, 'random_state': 42, 'n_jobs': -1, 'verbose': -1,
    }))
    lgb_model.fit(X_train_s3, y_train, eval_set=[(X_val_s3, y_val)],
                  callbacks=[lgb.early_stopping(10, verbose=False)])
    with open(MODEL_DIR / "lightgbm.pkl", "wb") as f:
        pickle.dump(lgb_model, f)

    # ---- mlp ----
    print("\nTraining MLP")
    mlp_model = build_mlp_model(input_dim=X_train_s3.shape[1], num_classes=NUM_CLASSES)
    mlp_model.fit(
        X_train_s3, y_train, epochs=50, batch_size=256, validation_data=(X_val_s3, y_val),
        callbacks=[
            callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True),
            callbacks.ReduceLROnPlateau(monitor='val_loss', factor=0.5, patience=3),
        ],
        verbose=0,
    )
    mlp_model.save(MODEL_DIR / "mlp.keras")

    # ---- xgboost ----
    print("\nTraining XGBoost")
    xgb_model = xgb.XGBClassifier(**get_xgb_params({
        'objective': 'multi:softmax', 'num_class': NUM_CLASSES,
        'n_estimators': 200, 'max_depth': 3, 'min_child_weight': 8, 'gamma': 0.3,
        'learning_rate': 0.1, 'subsample': 0.8, 'colsample_bytree': 0.8,
        'random_state': 42, 'n_jobs': -1,
    }))
    xgb_model.fit(X_train_s3, y_train, eval_set=[(X_val_s3, y_val)], verbose=False)
    with open(MODEL_DIR / "xgboost.pkl", "wb") as f:
        pickle.dump(xgb_model, f)

    # ---- evaluate ----
    print("\nEvaluating on the training set")
    results_train = [
        evaluate_model(X_test_s3, y_test, lgb_model, "LightGBM", "Training", RESULTS_DIR),
        evaluate_model(X_test_s3, y_test, mlp_model, "MLP", "Training", RESULTS_DIR),
        evaluate_model(X_test_s3, y_test, xgb_model, "XGBoost", "Training", RESULTS_DIR),
    ]

    print("\nEvaluating on the simulation set")
    results_sim = [
        evaluate_model(X_sim_s3, y_sim, lgb_model, "LightGBM", "Simulation", RESULTS_DIR),
        evaluate_model(X_sim_s3, y_sim, mlp_model, "MLP", "Simulation", RESULTS_DIR),
        evaluate_model(X_sim_s3, y_sim, xgb_model, "XGBoost", "Simulation", RESULTS_DIR),
    ]

    # ---- pick the best model ----
    combined_scores = []
    for i in range(3):
        avg_acc = (results_train[i]['accuracy'] + results_sim[i]['accuracy']) / 2
        gap = abs(results_train[i]['accuracy'] - results_sim[i]['accuracy'])
        shared_bonus = (results_train[i]['shared_sensor_acc'] + results_sim[i]['shared_sensor_acc']) / 2
        score = avg_acc + (shared_bonus * 0.2) - (gap * 0.5)
        combined_scores.append(score)
        print(f"{results_train[i]['model_name']}: avg accuracy {avg_acc:.4f}, shared bonus {shared_bonus * 0.2:.4f}, "
              f"gap penalty {gap * 0.5:.4f}, score {score:.4f}")

    best_idx = int(np.argmax(combined_scores))
    best_model_name = results_train[best_idx]['model_name']
    print(f"\nBest model: {best_model_name}")

    pd.DataFrame(results_train).to_csv(RESULTS_DIR / "training_results.csv", index=False)
    pd.DataFrame(results_sim).to_csv(RESULTS_DIR / "simulation_results.csv", index=False)

    final_config = {
        'stage': 3,
        'task': 'Component identification, 10 classes',
        'components': COMPONENTS,
        'shared_sensor_components': SHARED_SENSOR_COMPS,
        'best_model': best_model_name,
        'best_model_type': ['lightgbm', 'mlp', 'xgboost'][best_idx],
        'training_performance': results_train[best_idx],
        'simulation_performance': results_sim[best_idx],
        'trained_at': datetime.now().isoformat(),
    }
    with open(MODEL_DIR / "final_config.json", "w") as f:
        json.dump(final_config, f, indent=2, default=str)

    print(f"\nStage 3 done. Models in {MODEL_DIR}, results in {RESULTS_DIR}")


if __name__ == "__main__":
    main()
