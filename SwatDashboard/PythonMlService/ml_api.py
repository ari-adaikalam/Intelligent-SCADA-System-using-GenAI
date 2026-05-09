"""
SWaT ML Inference API Service
Directly calls ml_inference.run_pipeline() and returns dashboard-friendly JSON
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
import time
import traceback

# Import from current folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

app = Flask(__name__)
CORS(app)

ML_AVAILABLE = False
ML_IMPORT_ERROR = None
ML_API_FILE = os.path.abspath(__file__)
ML_PID = os.getpid()

sensor_buffer = None
MODELS = None  # cached models (already cached in your ml_inference too)


# -----------------------------------------------------------------------------
# Startup: load models ONCE + create one shared buffer
# -----------------------------------------------------------------------------
try:
    from sensor_buffer import SensorBuffer
    import ml_inference

    t0 = time.perf_counter()
    MODELS = ml_inference.load_models()
    t1 = time.perf_counter()

    if not MODELS or not MODELS.get("loaded"):
        raise RuntimeError(MODELS.get("error", "Models not loaded"))

    sensor_buffer = SensorBuffer(window_size=60, n_features=40)
    ML_AVAILABLE = True

    print(f"✅ Models loaded successfully in {(t1 - t0)*1000:.1f} ms")
    print("ML Available: True")

except Exception as e:
    ML_IMPORT_ERROR = f"{e}\n{traceback.format_exc()}"
    ML_AVAILABLE = False
    print(f"ML Import Error: {e}")
    print(traceback.format_exc())
    print("ML Available: False")


# -----------------------------------------------------------------------------
# Map ml_inference output -> what your web app expects
# -----------------------------------------------------------------------------
def to_dashboard_schema(result: dict):
    stage1 = result.get("stage1", {}) or {}
    stage2 = result.get("stage2", {}) or {}
    stage3 = result.get("stage3", {}) or {}

    bs = result.get("buffer_status", {}) or {}
    buffer_status = {
        "ready": bool(bs.get("ready", sensor_buffer.is_ready() if sensor_buffer else False)),
        "size": int(bs.get("size", len(sensor_buffer) if sensor_buffer else 0)),
        "capacity": int(getattr(sensor_buffer, "window_size", 60)) if sensor_buffer else 60,
        "usingBuffer": bool(bs.get("using_buffer", False)),
    }

    return {
        "success": True,
        "stage1": {
            "isAnomaly": bool(stage1.get("is_anomaly", False)),
            "confidence": float(stage1.get("confidence", 0.0)),
            "score": stage1.get("score", None),
            "modelType": stage1.get("model_type", None),
        },
        "stage2": {
            "state": stage2.get("state", "UNKNOWN"),
            "confidence": float(stage2.get("confidence", 0.0)),
            "modelType": stage2.get("model_type", None),
        },
        "stage3": {
            "component": stage3.get("component", None),
            "confidence": float(stage3.get("confidence", 0.0)),
            "top3": [
                {"component": c, "confidence": float(p)}
                for (c, p) in (stage3.get("top3") or [])
            ],
            "modelType": stage3.get("model_type", None),
        },
        "componentHealth": result.get("component_health", {}) or {},
        "recommendedActions": result.get("actions", []) or [],
        "alertsSent": result.get("alerts_sent", {}) or {},
        "bufferStatus": buffer_status,
    }


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "ml_available": bool(ML_AVAILABLE),
        "pid": ML_PID,
        "file": ML_API_FILE,
        "import_error": ML_IMPORT_ERROR,
        "buffer_size": len(sensor_buffer) if sensor_buffer else 0,
        "buffer_ready": sensor_buffer.is_ready() if sensor_buffer else False,
    })


@app.route("/api/inference", methods=["POST"])
def run_inference():
    if not ML_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "ML components not available",
            "import_error": ML_IMPORT_ERROR
        }), 503

    try:
        data = request.get_json(silent=True) or {}
        payload = data.get("payload")

        if not isinstance(payload, dict):
            return jsonify({"success": False, "error": "Missing payload in request"}), 400

        # ✅ Directly call YOUR working pipeline
        result = ml_inference.run_pipeline(payload, sensor_buffer=sensor_buffer)

        if not result.get("success", False):
            return jsonify({
                "success": False,
                "error": result.get("error", "Pipeline failed"),
                "bufferStatus": {
                    "ready": sensor_buffer.is_ready() if sensor_buffer else False,
                    "size": len(sensor_buffer) if sensor_buffer else 0,
                    "capacity": getattr(sensor_buffer, "window_size", 60) if sensor_buffer else 60,
                    "usingBuffer": False,
                }
            }), 200

        return jsonify(to_dashboard_schema(result)), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/buffer/reset", methods=["POST"])
def reset_buffer():
    global sensor_buffer
    if not ML_AVAILABLE:
        return jsonify({"success": False, "error": "ML not available"}), 503

    from sensor_buffer import SensorBuffer
    sensor_buffer = SensorBuffer(window_size=60, n_features=40)
    return jsonify({"success": True, "message": "Buffer reset"}), 200


@app.route("/api/buffer/status", methods=["GET"])
def buffer_status():
    if not sensor_buffer:
        return jsonify({"ready": False, "size": 0, "capacity": 60})
    return jsonify({
        "ready": sensor_buffer.is_ready(),
        "size": len(sensor_buffer),
        "capacity": sensor_buffer.window_size
    })


if __name__ == "__main__":
    print("=" * 60)
    print("SWaT ML Inference API Service")
    print("=" * 60)
    print(f"ML Available: {ML_AVAILABLE}")
    print("Starting server on http://localhost:5000")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False, use_reloader=False)
