"""
Detects a GPU if one is available and configures TensorFlow, XGBoost, and
LightGBM to use it. Every training script calls setup_gpu() once at the
start. On a machine with no GPU everything just falls back to CPU.
"""

import os
import warnings

warnings.filterwarnings("ignore")

# Has to be set before TensorFlow is imported.
os.environ.setdefault("KERAS_BACKEND", "tensorflow")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

_GPU_CONFIG = None


def _nvidia_smi_gpus():
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode != 0:
            return []
        return [line.strip() for line in r.stdout.strip().split("\n") if line.strip()]
    except Exception:
        return []


def setup_gpu(memory_growth=True, memory_limit_mb=None, verbose=False):
    global _GPU_CONFIG

    config = {
        "has_gpu": False,
        "gpu_count": 0,
        "gpu_names": [],
        "tensorflow_gpu": False,
        "xgboost_gpu": False,
        "lightgbm_gpu": False,
        "device_type": "CPU",
        "xgboost_version": None,
    }

    gpu_names = _nvidia_smi_gpus()
    if gpu_names:
        config["has_gpu"] = True
        config["gpu_names"] = gpu_names
        config["gpu_count"] = len(gpu_names)
        config["device_type"] = "GPU"

    try:
        import sys
        # Some environments ship a broken partial jax install that trips up
        # TensorFlow's import, so clear it out before importing TF.
        sys.modules.pop("jax", None)
        sys.modules.pop("jaxlib", None)

        import tensorflow as tf
        gpus = tf.config.list_physical_devices("GPU")

        if gpus:
            try:
                for gpu in gpus:
                    if memory_growth:
                        tf.config.experimental.set_memory_growth(gpu, True)
                    if memory_limit_mb:
                        tf.config.set_logical_device_configuration(
                            gpu,
                            [tf.config.LogicalDeviceConfiguration(memory_limit=memory_limit_mb)],
                        )
                config["tensorflow_gpu"] = True
                config["has_gpu"] = True
                config["device_type"] = "GPU"
                if verbose:
                    print(f"TensorFlow GPU enabled ({len(gpus)} device(s))")
            except Exception as e:
                if verbose:
                    print(f"TensorFlow GPU setup failed ({e}), using CPU")
        elif verbose:
            print("No GPU visible to TensorFlow, using CPU")

    except Exception as e:
        if verbose:
            print(f"TensorFlow import failed ({e}), using CPU")
        config["tensorflow_gpu"] = False

    try:
        import xgboost as xgb
        config["xgboost_version"] = getattr(xgb, "__version__", None)
        config["xgboost_gpu"] = bool(config["has_gpu"])
    except Exception:
        config["xgboost_gpu"] = False

    try:
        import lightgbm as lgb
        try:
            lgb.LGBMClassifier(device="gpu", gpu_platform_id=0, gpu_device_id=0, n_estimators=1)
            config["lightgbm_gpu"] = True
            config["has_gpu"] = True
            config["device_type"] = "GPU"
        except Exception:
            config["lightgbm_gpu"] = False
    except Exception:
        config["lightgbm_gpu"] = False

    if verbose:
        print(f"Device: {config['device_type']}  "
              f"TF: {'GPU' if config['tensorflow_gpu'] else 'CPU'}  "
              f"XGBoost: {'GPU' if config['xgboost_gpu'] else 'CPU'}  "
              f"LightGBM: {'GPU' if config['lightgbm_gpu'] else 'CPU'}")

    _GPU_CONFIG = config
    return config


def get_xgb_params(base_params=None):
    """Merge in XGBoost 3.x device settings on top of the caller's params."""
    global _GPU_CONFIG
    if _GPU_CONFIG is None:
        setup_gpu(verbose=False)

    params = (base_params or {}).copy()
    params["tree_method"] = "hist"
    params["device"] = "cuda" if _GPU_CONFIG.get("xgboost_gpu") else "cpu"
    params.pop("gpu_id", None)       # deprecated in XGBoost 3.x
    params.pop("predictor", None)    # deprecated in XGBoost 3.x
    return params


def get_lgb_params(base_params=None):
    """Merge in LightGBM device settings on top of the caller's params."""
    global _GPU_CONFIG
    if _GPU_CONFIG is None:
        setup_gpu(verbose=False)

    params = (base_params or {}).copy()
    if _GPU_CONFIG.get("lightgbm_gpu"):
        params["device"] = "gpu"
        params["gpu_platform_id"] = 0
        params["gpu_device_id"] = 0
    else:
        params["device"] = "cpu"
        params.pop("gpu_platform_id", None)
        params.pop("gpu_device_id", None)
    return params


# Run once on import so a bare `from gpu_setup import get_xgb_params`
# still has hardware info ready without the caller remembering to call
# setup_gpu() first.
try:
    setup_gpu(verbose=False)
except Exception:
    pass
