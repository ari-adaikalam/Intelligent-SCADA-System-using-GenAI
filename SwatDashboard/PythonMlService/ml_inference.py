"""
ML INFERENCE ENGINE FOR SWAT DASHBOARD
======================================
Real-time predictive maintenance inference using trained models.

Implements 3-stage pipeline:
- Stage 1: Anomaly Detection (ANY model from training)
- Stage 2: State Classification (ANY model from training)
- Stage 3: Component Identification (ANY model from training)

Models are automatically loaded based on final_config.json from each stage.
Models are cached for fast inference.
"""

import numpy as np
import pandas as pd
import pickle
import json
import warnings
from sensor_buffer import SensorBuffer
from alerts import trigger_alerts
warnings.filterwarnings('ignore')

try:
    import tensorflow as tf
    from tensorflow import keras
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    print("⚠️  TensorFlow not available. Install: pip install tensorflow")

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = False
except ImportError:
    STREAMLIT_AVAILABLE = False


# ============================================================================
# CONFIGURATION
# ============================================================================

# Model paths (adjust these to your local paths)
MODEL_DIR = r"D:\FYP - FINAL\SwatDashboard\PythonMlService\models"
DATA_DIR = r"D:\FYP - FINAL\SwatDashboard\PythonMlService\ml_data"

# Component names (must match training)
COMPONENTS = ['P101', 'P201', 'P203', 'P205', 'P302', 'P402', 'P403', 'P501', 'MV101', 'MV304']
STATE_NAMES = ['ANOMALY', 'DEGRADING', 'FAULTED']

# ============================================================================
# MODEL LOADING (CACHED & GENERAL)
# ============================================================================

if STREAMLIT_AVAILABLE:
    @st.cache_resource
    def load_models():
        """Load all trained models (cached for performance)"""
        return _load_models_internal()
else:
    _cached_models = None
    def load_models():
        global _cached_models
        if _cached_models is None:
            _cached_models = _load_models_internal()
        return _cached_models


def _load_models_internal():
    """Internal model loading function - GENERAL VERSION"""
    models = {}

    try:
        # Load scaler
        scaler_path = f"{DATA_DIR}/scaler.pkl"
        with open(scaler_path, 'rb') as f:
            models['scaler'] = pickle.load(f)

        # ====================================================================
        # STAGE 1: Load best model based on config
        # ====================================================================
        stage1_dir = f"{MODEL_DIR}/stage1"
        with open(f"{stage1_dir}/final_config.json", "r") as f:
            config1 = json.load(f)

        models['stage1_type'] = config1['best_model_type']

        if models['stage1_type'] in ['autoencoder', 'dae']:
            # Autoencoder or Denoising Autoencoder
            if not TF_AVAILABLE:
                raise ImportError("TensorFlow required for autoencoder models")

            model_file = 'autoencoder.keras' if models['stage1_type'] == 'autoencoder' else 'denoising_autoencoder.keras'
            threshold_file = 'autoencoder_threshold.pkl' if models['stage1_type'] == 'autoencoder' else 'dae_threshold.pkl'

            models['stage1'] = keras.models.load_model(f"{stage1_dir}/{model_file}", compile=False)
            with open(f"{stage1_dir}/{threshold_file}", 'rb') as f:
                models['stage1_threshold'] = pickle.load(f)

        elif models['stage1_type'] == 'lof':
            # Local Outlier Factor
            with open(f"{stage1_dir}/lof.pkl", 'rb') as f:
                models['stage1'] = pickle.load(f)
            with open(f"{stage1_dir}/lof_threshold.pkl", 'rb') as f:
                models['stage1_threshold'] = pickle.load(f)

        elif models['stage1_type'] == 'iforest':
            # Isolation Forest
            with open(f"{stage1_dir}/isolation_forest.pkl", 'rb') as f:
                models['stage1'] = pickle.load(f)
            models['stage1_threshold'] = None  # Uses built-in threshold

        else:  # xgboost
            with open(f"{stage1_dir}/xgboost.pkl", 'rb') as f:
                models['stage1'] = pickle.load(f)

            # ===== FORCE CPU (XGBoost 3.1.0 SAFE) =====
            m = models['stage1']

            # sklearn wrapper params
            try:
                m.set_params(
                    device="cpu",  # 🔥 key line
                    tree_method="hist",  # CPU-friendly
                    n_jobs=1  # avoid OpenMP fights
                )
            except Exception:
                pass

            # booster-level safety
            try:
                m.get_booster().set_param({"device": "cpu"})
            except Exception:
                pass

            models['stage1_threshold'] = None
            #print("   ✅ Stage 1 XGBoost loaded (CPU forced)")

        # ====================================================================
        # STAGE 2: Load best model based on config
        # ====================================================================
        stage2_dir = f"{MODEL_DIR}/stage2"
        with open(f"{stage2_dir}/final_config.json", "r") as f:
            config2 = json.load(f)

        models['stage2_type'] = config2['best_model_type']
        models['stage2_seq_length'] = config2.get('sequence_length', None)

        if models['stage2_type'] in ['lstm', 'cnn']:
            # Sequential models (LSTM or CNN)
            if not TF_AVAILABLE:
                raise ImportError("TensorFlow required for LSTM/CNN models")

            models['stage2'] = keras.models.load_model(f"{stage2_dir}/{models['stage2_type']}.keras")

        else:  # xgboost
            with open(f"{stage2_dir}/xgboost.pkl", 'rb') as f:
                models['stage2'] = pickle.load(f)

        # ====================================================================
        # STAGE 3: Load best model based on config
        # ====================================================================
        stage3_dir = f"{MODEL_DIR}/stage3"
        with open(f"{stage3_dir}/final_config.json", "r") as f:
            config3 = json.load(f)

        models['stage3_type'] = config3['best_model_type']

        if models['stage3_type'] == 'mlp':
            # Multi-Layer Perceptron
            if not TF_AVAILABLE:
                raise ImportError("TensorFlow required for MLP models")

            models['stage3'] = keras.models.load_model(f"{stage3_dir}/mlp.keras")

        elif models['stage3_type'] == 'lightgbm':
            # LightGBM
            with open(f"{stage3_dir}/lightgbm.pkl", 'rb') as f:
                models['stage3'] = pickle.load(f)

        else:  # xgboost
            with open(f"{stage3_dir}/xgboost.pkl", 'rb') as f:
                models['stage3'] = pickle.load(f)

        models['loaded'] = True
        print(f"✅ Models loaded successfully!")
        print(f"   Stage 1: {config1['best_model']} ({models['stage1_type']})")
        print(f"   Stage 2: {config2['best_model']} ({models['stage2_type']})")
        print(f"   Stage 3: {config3['best_model']} ({models['stage3_type']})")

        return models

    except Exception as e:
        print(f"⚠️  Error loading models: {e}")
        models['loaded'] = False
        models['error'] = str(e)
        return models


# ============================================================================
# FEATURE EXTRACTION
# ============================================================================

def extract_features(payload):
    """
    Extract 40 features from payload (matches training format).

    Returns:
        np.array: (1, 40) feature array
    """
    features = []

    # ========================================================================
    # 16 SENSOR READINGS
    # ========================================================================
    sensors = [
        'true_FIT101', 'true_FIT201', 'true_FIT301', 'true_FIT401', 'true_FIT501',
    'true_LIT101', 'true_LIT301', 'true_LIT401',
    'true_AIT201', 'true_AIT202', 'true_AIT203', 'true_AIT401', 'true_AIT402', 'true_AIT501',
    'true_DPIT301', 'true_PIT501'
]

    for sensor in sensors:
        val = payload.get(sensor, 0)
        try:
            features.append(float(val))
        except:
            features.append(0.0)

    # ========================================================================
    # 24 MOTOR PHYSICS FEATURES
    # ========================================================================
    # These should match the motor physics features used in training
    # Format: motor_temp, current, vibration for each component
    components = ['P101', 'P201', 'P203', 'P205', 'P302', 'P402', 'P403', 'P501']

    for comp in components:
        # Get motor physics features from payload
        temp_key = f'true_{comp}_motor_temp'
        current_key = f'true_{comp}_current'
        vib_key = f'true_{comp}_vibration'

        # Extract values (use defaults if not present)
        temp = payload.get(temp_key, 0.0)
        current = payload.get(current_key, 0.0)
        vib = payload.get(vib_key, 0.0)

        try:
            features.extend([float(temp), float(current), float(vib)])
        except:
            features.extend([0.0, 0.0, 0.0])

    # Convert to numpy array
    return np.array(features).reshape(1, -1)


# ============================================================================
# STAGE 1: ANOMALY DETECTION (GENERAL)
# ============================================================================

def predict_anomaly(features_scaled, models):
    """
    Stage 1: Binary anomaly detection using ANY model type.

    Returns:
        tuple: (is_anomaly, confidence, score)
    """
    if not models.get('loaded'):
        return False, 0.0, 0.0

    try:
        model_type = models['stage1_type']

        # ====================================================================
        # AUTOENCODER / DENOISING AUTOENCODER
        # ====================================================================
        if model_type in ['autoencoder', 'dae']:
            # Reconstruct input
            reconstructed = models['stage1'].predict(features_scaled, verbose=0)

            # Compute reconstruction error (MSE)
            error = np.mean((features_scaled - reconstructed) ** 2)

            # Compare to threshold
            threshold = models['stage1_threshold']
            is_anomaly = (error > threshold)

            # Compute confidence
            if is_anomaly:
                confidence = min(1.0, (error / threshold - 1.0) * 2 + 0.5)
            else:
                confidence = min(1.0, (1.0 - error / threshold) + 0.5)

            return bool(is_anomaly), float(confidence), float(error)

        # ====================================================================
        # LOCAL OUTLIER FACTOR
        # ====================================================================
        elif model_type == 'lof':
            # Get anomaly score (higher = more anomalous)
            score = -models['stage1'].decision_function(features_scaled)[0]
            threshold = models['stage1_threshold']

            is_anomaly = (score > threshold)

            # Confidence based on distance from threshold
            if is_anomaly:
                confidence = min(1.0, (score / threshold - 1.0) + 0.5)
            else:
                confidence = min(1.0, (1.0 - score / threshold) + 0.5)

            return bool(is_anomaly), float(confidence), float(score)

        # ====================================================================
        # ISOLATION FOREST
        # ====================================================================
        elif model_type == 'iforest':
            # Predict (-1 = anomaly, 1 = normal)
            pred = models['stage1'].predict(features_scaled)[0]
            is_anomaly = (pred == -1)

            # Get anomaly score for confidence
            score = -models['stage1'].score_samples(features_scaled)[0]
            confidence = min(1.0, abs(score) / 2.0)

            return bool(is_anomaly), float(confidence), float(score)

        # ====================================================================
        # XGBOOST
        # ====================================================================
        else:  # xgboost
            import xgboost as xgb
            import numpy as np

            # force CPU
            try:
                models["stage1"].set_params(device="cpu", tree_method="hist", n_jobs=1)
            except Exception:
                pass
            try:
                models["stage1"].get_booster().set_param({"device": "cpu"})
            except Exception:
                pass

            x = np.ascontiguousarray(features_scaled.astype(np.float32))
            dm = xgb.DMatrix(x)

            p1 = float(models["stage1"].get_booster().predict(dm)[0])  # binary:logistic => P(class=1)
            is_anomaly = p1 > 0.5
            confidence = p1 if is_anomaly else (1.0 - p1)

            return bool(is_anomaly), float(confidence), float(p1)

    except Exception as e:
        print(f"Stage 1 error: {e}")
        return False, 0.0, 0.0


# ============================================================================
# STAGE 2: STATE CLASSIFICATION (GENERAL)
# ============================================================================

def predict_state(features_scaled, models, is_anomaly, sensor_buffer=None):
    """
    Stage 2: Multi-class state classification using ANY model type.
    Only runs if Stage 1 detected anomaly.

    Args:
        features_scaled: Current sample features (scaled)
        models: Loaded models dict
        is_anomaly: Whether Stage 1 detected anomaly
        sensor_buffer: Optional SensorBuffer for LSTM/CNN

    Returns:
        tuple: (state_name, confidence, state_probs)
    """
    if not is_anomaly:
        return "NORMAL", 1.0, [0.0, 0.0, 0.0]

    if not models.get('loaded'):
        return "UNKNOWN", 0.0, [0.0, 0.0, 0.0]

    try:
        model_type = models['stage2_type']

        # ====================================================================
        # LSTM / CNN (Sequential models)
        # ====================================================================
        if model_type in ['lstm', 'cnn']:
            seq_length = models['stage2_seq_length']

            # NEW: Try to use buffer if available
            if sensor_buffer is not None and sensor_buffer.is_ready():
                # Use real sequence from buffer
                seq = sensor_buffer.get_sequence()
                seq = seq.reshape(1, seq_length, -1)
                use_buffer = True
            else:
                # Fallback: Repeat current sample (old hack)
                seq = np.repeat(features_scaled, seq_length, axis=0)
                seq = seq.reshape(1, seq_length, -1)
                use_buffer = False

            # Predict
            probs = models['stage2'].predict(seq, verbose=0)[0]

            # Get predicted class
            state_idx = int(np.argmax(probs))
            state_name = STATE_NAMES[state_idx]
            confidence = float(probs[state_idx])

            # Reduce confidence if using fallback hack
            if not use_buffer:
                confidence *= 0.85  # Penalty for not having real sequence

            return state_name, confidence, probs.tolist()

        # ====================================================================
        # XGBOOST (Tabular model - doesn't need buffer)
        # ====================================================================
        else:  # xgboost
            # Predict probabilities
            probs = models['stage2'].predict_proba(features_scaled)[0]

            # Get predicted class
            state_idx = int(np.argmax(probs))
            state_name = STATE_NAMES[state_idx]
            confidence = float(probs[state_idx])

            return state_name, confidence, probs.tolist()

    except Exception as e:
        print(f"Stage 2 error: {e}")
        return "UNKNOWN", 0.0, [0.0, 0.0, 0.0]

# ============================================================================
# STAGE 3: COMPONENT IDENTIFICATION (GENERAL)
# ============================================================================

def predict_component(features_scaled, models, state_name):
    """
    Stage 3: Component identification using ANY model type.
    Only runs if state is DEGRADING or FAULTED.

    Returns:
        tuple: (component, confidence, top3_components)
    """
    if state_name == "NORMAL":
        return None, 0.0, []

    if not models.get('loaded'):
        return None, 0.0, []

    try:
        model_type = models['stage3_type']

        # ====================================================================
        # MLP (Neural Network)
        # ====================================================================
        if model_type == 'mlp':
            # Predict probabilities
            probs = models['stage3'].predict(features_scaled, verbose=0)[0]

            # Get top prediction
            comp_idx = int(np.argmax(probs))
            component = COMPONENTS[comp_idx]
            confidence = float(probs[comp_idx])

            # Get top 3
            top3_idx = np.argsort(probs)[-3:][::-1]
            top3 = [(COMPONENTS[i], float(probs[i])) for i in top3_idx]

            return component, confidence, top3

        # ====================================================================
        # LIGHTGBM or XGBOOST
        # ====================================================================
        else:  # lightgbm or xgboost
            # Predict probabilities
            probs = models['stage3'].predict_proba(features_scaled)[0]

            # Get top prediction
            comp_idx = int(np.argmax(probs))
            component = COMPONENTS[comp_idx]
            confidence = float(probs[comp_idx])

            # Get top 3
            top3_idx = np.argsort(probs)[-3:][::-1]
            top3 = [(COMPONENTS[i], float(probs[i])) for i in top3_idx]

            return component, confidence, top3

    except Exception as e:
        print(f"Stage 3 error: {e}")
        return None, 0.0, []


# ============================================================================
# FULL PIPELINE
# ============================================================================

def run_pipeline(payload, sensor_buffer=None):
    """
    Run complete 3-stage ML pipeline on payload.

    Args:
        payload (dict): Raw sensor/actuator data from dashboard
        sensor_buffer (SensorBuffer): Optional buffer for LSTM/CNN models

    Returns:
        dict: Prediction results with all stages
    """
    # Load models (cached)
    models = load_models()

    # Check if models loaded successfully
    if not models.get('loaded'):
        return {
            'success': False,
            'error': models.get('error', 'Models not loaded'),
            'stage1': {'is_anomaly': False, 'confidence': 0.0},
            'stage2': {'state': 'UNKNOWN', 'confidence': 0.0},
            'stage3': {'component': None, 'confidence': 0.0}
        }

    try:
        # Extract features
        features = extract_features(payload)

        # Scale features
        features_scaled = models['scaler'].transform(features)

        # NEW: Add to buffer if provided
        if sensor_buffer is not None:
            sensor_buffer.add_sample(features_scaled[0])  # Add 1D array

        # Stage 1: Anomaly Detection
        is_anomaly, s1_conf, score = predict_anomaly(features_scaled, models)

        # Stage 2: State Classification (NOW WITH BUFFER)
        state, s2_conf, state_probs = predict_state(
            features_scaled,
            models,
            is_anomaly,
            sensor_buffer=sensor_buffer  # PASS BUFFER
        )

        # Stage 3: Component Identification
        component, s3_conf, top3 = predict_component(features_scaled, models, state)

        # Compile results
        result = {
            'success': True,
            'timestamp': pd.Timestamp.now(),
            'stage1': {
                'is_anomaly': is_anomaly,
                'confidence': s1_conf,
                'score': score,
                'model_type': models['stage1_type']
            },
            'stage2': {
                'state': state,
                'confidence': s2_conf,
                'probabilities': {
                    'ANOMALY': state_probs[0] if len(state_probs) > 0 else 0.0,
                    'DEGRADING': state_probs[1] if len(state_probs) > 1 else 0.0,
                    'FAULTED': state_probs[2] if len(state_probs) > 2 else 0.0
                },
                'model_type': models['stage2_type']
            },
            'stage3': {
                'component': component,
                'confidence': s3_conf,
                'top3': top3,
                'model_type': models['stage3_type']
            }
        }

        # NEW: Add buffer status to result
        if sensor_buffer is not None:
            result['buffer_status'] = {
                'size': sensor_buffer.size(),
                'ready': sensor_buffer.is_ready(),
                'using_buffer': sensor_buffer.is_ready() and models['stage2_type'] in ['lstm', 'cnn']
            }
        # Build component health + recommended actions
        component_health = get_component_health(result)
        result['component_health'] = component_health  # optional (for dashboard)

        result['actions'] = get_recommended_actions(result, component_health)

        # Now trigger alerts (email uses result['actions'])
        alert_status = trigger_alerts(result)
        result['alerts_sent'] = alert_status
        return result

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'stage1': {'is_anomaly': False, 'confidence': 0.0},
            'stage2': {'state': 'ERROR', 'confidence': 0.0},
            'stage3': {'component': None, 'confidence': 0.0}
        }

# ============================================================================
# COMPONENT HEALTH SUMMARY
# ============================================================================

def get_component_health(prediction):
    """
    Generate health status for all components.

    Returns:
        dict: {component_name: status_dict}
    """
    health = {}

    state = prediction['stage2']['state']
    identified_comp = prediction['stage3']['component']
    top3 = prediction['stage3'].get('top3', [])

    for comp in COMPONENTS:
        if state == "NORMAL":
            health[comp] = {
                'status': 'NORMAL',
                'icon': '🟢',
                'confidence': 1.0,
                'message': 'Operating normally'
            }
        elif comp == identified_comp:
            # Primary suspect
            conf = prediction['stage3']['confidence']
            if state == "FAULTED":
                health[comp] = {
                    'status': 'FAULTED',
                    'icon': '🔴',
                    'confidence': conf,
                    'message': f'FAULTED - Immediate action required'
                }
            elif state == "DEGRADING":
                health[comp] = {
                    'status': 'DEGRADING',
                    'icon': '🟡',
                    'confidence': conf,
                    'message': f'Degrading - Schedule maintenance'
                }
            elif state == "ANOMALY":
                health[comp] = {
                    'status': 'MONITOR',
                    'icon': '🟠',
                    'confidence': conf,
                    'message': 'Anomaly detected - Monitor closely'
                }
        elif any(comp == t[0] for t in top3):
            # In top 3 - possible suspect
            conf = next(t[1] for t in top3 if t[0] == comp)
            health[comp] = {
                'status': 'MONITOR',
                'icon': '🟠',
                'confidence': conf,
                'message': f'Check (Top-3: {conf*100:.0f}%)'
            }
        else:
            # Not identified
            health[comp] = {
                'status': 'NORMAL',
                'icon': '🟢',
                'confidence': 0.0,
                'message': 'Operating normally'
            }

    return health


# ============================================================================
# RECOMMENDED ACTIONS
# ============================================================================

def get_recommended_actions(prediction, component_health):
    """
    Generate maintenance recommendations based on predictions.

    Returns:
        list: List of action strings
    """
    actions = []

    state = prediction['stage2']['state']
    component = prediction['stage3']['component']

    if state == "NORMAL":
        actions.append("✅ System operating normally - No action required")
        return actions
    else:
        if state != "FAULTED" and state != "DEGRADING":
            actions.append(f"⚠️  Suspected component: {component}")

    if component:
        # Component-specific actions
        comp_actions = {
            'P101': [
                '🔧 Inspect intake pump P101 for wear',
                '📋 Check pump vibration and bearing temperature',
                '💧 Verify intake flow rate and pressure'
            ],
            'P201': [
                '🔧 Inspect NaCl dosing pump P201',
                '📋 Check chemical feed lines for blockages',
                '⚗️ Verify NaCl concentration and flow rate'
            ],
            'P203': [
                '🔧 Inspect HCl dosing pump P203',
                '📋 Check acid feed system for leaks',
                '⚗️ Calibrate pH sensor AIT202'
            ],
            'P205': [
                '🔧 Inspect NaOCl dosing pump P205',
                '📋 Check chlorine feed system',
                '⚗️ Verify ORP readings (AIT203)'
            ],
            'P302': [
                '🔧 Inspect UF feed pump P302',
                '📋 Check UF membrane differential pressure',
                '💧 Consider membrane backwash or cleaning'
            ],
            'P402': [
                '🔧 Inspect dechlorination feed pump P402',
                '📋 Check UV system operation',
                '⚗️ Verify ORP levels post-UV'
            ],
            'P403': [
                '🔧 Inspect NaHSO₄ dosing pump P403',
                '📋 Check dechlorination efficiency',
                '⚗️ Verify residual chlorine levels'
            ],
            'P501': [
                '🔧 Inspect RO feed pump P501',
                '📋 Check RO membrane pressure and flow',
                '💧 Monitor permeate quality (TDS)'
            ],
            'MV101': [
                '🔧 Inspect motorized valve MV101',
                '📋 Check valve position and response',
                '⚙️ Lubricate valve actuator'
            ],
            'MV304': [
                '🔧 Inspect motorized valve MV304',
                '📋 Check UF backwash valve operation',
                '⚙️ Verify valve seating'
            ]
        }
        if state == "FAULTED":
            actions.append(f"🚨 URGENT: {component} has FAULTED")
            actions.append("📞 Alert maintenance team")
            actions.append(f"⏸️  Consider stopping {component} immediately")
        # General actions based on state
        if state == "DEGRADING":
            actions.append(f"🚨 URGENT: {component} is DEGRADING")
            actions.append("📅 Schedule maintenance within next 24-48 hours")
            actions.append("📊 Increase monitoring frequency")

        if component in comp_actions:
            actions.extend(comp_actions[component][:3])  # Top 3 actions


    return actions


# ============================================================================
# TESTING
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TEST 1: Without Buffer (Old Way)")
    print("=" * 60)

    test_payload = {
        'true_FIT101': 2.5, 'true_LIT101': 800.0,
        'true_FIT201': 2.3, 'true_AIT201': 150.0, 'true_AIT202': 7.2, 'true_AIT203': 350.0,
        'true_FIT301': 2.1, 'true_LIT301': 750.0, 'true_DPIT301': 0.15,
        'true_FIT401': 2.0, 'true_LIT401': 700.0, 'true_AIT401': 85.0, 'true_AIT402': 280.0,
        'true_FIT501': 1.8, 'true_PIT501': 5.2, 'true_AIT501': 6.8,
        # Motor physics features
        'true_P101_motor_temp': 45.0, 'true_P101_current': 3.5, 'true_P101_vibration': 1.2,
        'true_P201_motor_temp': 42.0, 'true_P201_current': 2.8, 'true_P201_vibration': 0.9,
        'true_P203_motor_temp': 40.0, 'true_P203_current': 2.5, 'true_P203_vibration': 0.8,
        'true_P205_motor_temp': 43.0, 'true_P205_current': 3.0, 'true_P205_vibration': 1.0,
        'true_P302_motor_temp': 46.0, 'true_P302_current': 3.8, 'true_P302_vibration': 1.3,
        'true_P402_motor_temp': 44.0, 'true_P402_current': 3.2, 'true_P402_vibration': 1.1,
        'true_P403_motor_temp': 41.0, 'true_P403_current': 2.7, 'true_P403_vibration': 0.9,
        'true_P501_motor_temp': 48.0, 'true_P501_current': 4.0, 'true_P501_vibration': 1.4,
        'true_MV101_motor_temp': 38.0, 'true_MV101_current': 1.5, 'true_MV101_vibration': 0.5,
        'true_MV304_motor_temp': 39.0, 'true_MV304_current': 1.6, 'true_MV304_vibration': 0.6,
    }

    # Create buffer and add 60 samples
    buffer = SensorBuffer(window_size=60, n_features=40)

    for i in range(60):
        result1 = run_pipeline(test_payload, sensor_buffer=buffer)

    if result1['success']:
        print(f"✅ Stage 1: {result1['stage1']['is_anomaly']}")
        print(f"✅ Stage 2: {result1['stage2']['state']} (conf: {result1['stage2']['confidence']:.2f})")
        print(f"✅ Stage 3: {result1['stage3']['component']}")
        print(f"\n📊 Buffer Status:")
        print(f"   Size: {result1['buffer_status']['size']}/60")
        print(f"   Ready: {result1['buffer_status']['ready']}")
        print(f"   Using Buffer: {result1['buffer_status']['using_buffer']}")
    else:
        print(f"\n❌ Pipeline Error: {result1['error']}")
