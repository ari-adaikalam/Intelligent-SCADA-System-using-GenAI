"""
SWAT RAG Service - Main Flask API
===================================
Handles chat requests from C# backend and orchestrates RAG pipeline.

Endpoints:
- GET  /               - Service info (was 404, now 200)
- GET  /health         - Health check
- POST /api/chat       - Main chat endpoint
- POST /api/generate-report  - Report generation
- POST /api/session/clear    - Clear session memory

Fixes applied:
  1. Added GET / route (eliminates noisy 404s in Render logs)
  2. Startup banner uses correct PORT env var
  3. Warmup thread only starts when rag_engine loaded successfully
  4. session_memory pruning is O(1) with deque instead of list slice
  5. Consistent logging labels [CHAT] vs [SUCCESS]
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import sys
import os
import threading
import time
from datetime import datetime
from collections import deque

os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/rag_service.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Render sits in front of this service as a reverse proxy — trust its
# X-Forwarded-For header so rate limiting (below) keys on the real client
# IP instead of Render's internal proxy IP.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# Only the dashboard's own origin may call this service from a browser.
# (This does not stop direct server-to-server calls — that's handled by
# rate limiting below and the SQL validator in sql_generator.py — but it
# closes off the "any website's JS can call this on a visitor's behalf"
# path.)
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get(
        "ALLOWED_ORIGINS", "https://swat-dashboard-hlxg.onrender.com"
    ).split(",") if o.strip()
]
CORS(app, origins=ALLOWED_ORIGINS)

# Rate limiting — chat/report requests trigger billed LLM calls and DB
# queries, so a per-IP limit matters even with CORS locked down (CORS
# doesn't stop direct server-to-server calls).
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://",
)

# ---------------------------------------------------------------------------
# RAG engine initialisation
# ---------------------------------------------------------------------------

rag_engine = None
try:
    from rag_engine import RagEngine
    rag_engine = RagEngine()
    logger.info("[OK] RAG engine initialized successfully")
except Exception as e:
    logger.error(f"[ERROR] Failed to initialize RAG engine: {e}")
    rag_engine = None

# ---------------------------------------------------------------------------
# Session memory  (session_id -> deque of {user, bot, timestamp})
# ---------------------------------------------------------------------------

session_memory: dict[str, deque] = {}
SESSION_MAX_TURNS = 20


def _get_session(session_id: str) -> deque:
    if session_id not in session_memory:
        session_memory[session_id] = deque(maxlen=SESSION_MAX_TURNS)
    return session_memory[session_id]


# ---------------------------------------------------------------------------
# Background LLM warmup
# ---------------------------------------------------------------------------

def _warmup_llm():
    time.sleep(3)
    if rag_engine:
        try:
            result = rag_engine.check_llm()
            logger.info(f"[WARMUP] LLM warmup result: {result}")
        except Exception as e:
            logger.warning(f"[WARMUP] LLM warmup failed: {e}")


if rag_engine:
    threading.Thread(target=_warmup_llm, daemon=True).start()
    logger.info("[WARMUP] Background LLM warmup thread started")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/", methods=["GET"])
def index():
    """Service info — eliminates 404 noise in Render health-check logs."""
    return jsonify({
        "service": "SWAT RAG API",
        "status": "running",
        "rag_engine": rag_engine is not None,
        "timestamp": datetime.utcnow().isoformat(),
    }), 200


@app.route("/health", methods=["GET"])
def health():
    try:
        details = {
            "rag_engine": rag_engine is not None,
            "chromadb": False,
            "ml_api": False,
            "llm": False,
        }

        if rag_engine:
            try:
                details["chromadb"] = rag_engine.check_chromadb()
            except Exception:
                pass

            try:
                details["ml_api"] = rag_engine.check_ml_api()
            except Exception:
                pass

            try:
                details["llm"] = rag_engine.check_llm()
            except Exception:
                pass

        core_ready = (
            details["rag_engine"]
            and details["chromadb"]
            and details["ml_api"]
        )

        return jsonify({
            "status": "ok" if core_ready else "starting",
            "ready": core_ready,
            "llm_ready": details["llm"],
            "details": details,
            "timestamp": datetime.utcnow().isoformat(),
        }), 200

    except Exception as e:
        logger.error(f"[HEALTH] Error: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "ready": False,
            "llm_ready": False,
            "error": "health_check_failed",
        }), 500


@app.route("/api/chat", methods=["POST"])
@limiter.limit("10 per minute")
def chat():
    """
    Main chat endpoint.

    Request JSON:
    {
        "sessionId": "session_123",
        "message": "Show me pump temperatures",
        "conversationHistory": [...],
        "realtimeData": {"payload": {...}, "ts": "..."},
        "databaseConnection": {...}
    }
    """
    if not rag_engine:
        return jsonify({
            "success": False,
            "text": "[ERROR] RAG service not initialized. Please check server logs.",
            "error": "RAG engine not available",
        }), 503

    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "error": "Invalid JSON in request body"}), 400

        session_id    = data.get("sessionId") or data.get("session_id") or "default"
        user_message  = data.get("message") or data.get("userMessage") or ""
        realtime_data = data.get("realtimeData") or data.get("realtime_data")
        db_connection = data.get("databaseConnection") or data.get("database_connection") or {}

        if not user_message or not isinstance(user_message, str):
            return jsonify({"success": False, "error": "Message is required and must be a string"}), 400

        mem = _get_session(session_id)

        # Merge client-supplied history with server-side memory
        conversation_history = list(data.get("conversationHistory") or []) + list(mem)

        logger.info(f"[CHAT] Chat request from session {session_id}: {user_message[:50]}…")

        response = rag_engine.process_message(
            message=user_message,
            session_id=session_id,
            conversation_history=conversation_history,
            realtime_data=realtime_data,
            db_connection=db_connection,
        )

        # Persist exchange (deque auto-prunes to SESSION_MAX_TURNS)
        mem.append({
            "user": user_message,
            "bot": response.get("text", ""),
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.info(f"[SUCCESS] Chat response generated for session {session_id}")
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"[ERROR] chat endpoint: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "text": "I encountered an error processing your request. Please try again.",
            "error": "internal_error",
        }), 500


@app.route("/api/generate-report", methods=["POST"])
def generate_report():
    """Report generation endpoint."""
    try:
        data = request.get_json(silent=True) or {}

        if not rag_engine:
            return jsonify({
                "success": False,
                "text": "RAG service not initialized.",
                "error": "RAG engine not available",
            }), 503

        # Delegate to the engine's report handler
        report_intent = {"time_range": data.get("timeRange")}
        message = data.get("reportType", "summary report")
        context = {"knowledge": [], "conversation_history": []}
        response = rag_engine._handle_report_generation(
            message, report_intent, context, data.get("databaseConnection") or {}
        )
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "text": "Report generation failed. Please try again.",
            "error": "internal_error",
        }), 500


@app.route("/api/session/clear", methods=["POST"])
def clear_session():
    """Clear a specific session's server-side memory."""
    try:
        data = request.get_json(silent=True)
        session_id = data.get("sessionId") if data else None

        if session_id and session_id in session_memory:
            del session_memory[session_id]
            logger.info(f"[SESSION] Cleared session: {session_id}")

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Error clearing session: {e}", exc_info=True)
        return jsonify({"success": False, "error": "internal_error"}), 500


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print("=" * 60)
    print("SWAT RAG Service with Mistral 7B")
    print("=" * 60)
    print(f"RAG Engine Status: {'[OK] Loaded' if rag_engine else '[ERROR] Not Loaded'}")
    print(f"Starting server on http://0.0.0.0:{port}")
    print("=" * 60)

    app.run(host="0.0.0.0", port=port)
