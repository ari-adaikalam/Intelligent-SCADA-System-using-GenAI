"""
SWAT RAG Service - Main Flask API
===================================
Handles chat requests from C# backend and orchestrates RAG pipeline.

Port: 5001
Endpoints:
- POST /api/chat - Main chat endpoint
- GET /health - Health check
- POST /api/generate-report - Report generation (basic)

Dependencies: Ollama (Mistral 7B), ChromaDB, MS SQL
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import sys
import os
from datetime import datetime

os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/rag_service.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)

# Import modules (after app creation)
try:
    from rag_engine import RagEngine
    from report_generator import ReportGenerator
    
    # Initialize RAG engine
    rag_engine = RagEngine()
    logger.info("[OK] RAG engine initialized successfully")
    
except Exception as e:
    logger.error(f"[ERROR] Failed to initialize RAG engine: {e}")
    rag_engine = None

# Session memory (in-memory storage)
session_memory = {}

# ============================================================================
# ROUTES
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        status = {
            "status": "ok",
            "timestamp": datetime.utcnow().isoformat(),
            "rag_engine_loaded": rag_engine is not None,
            "ollama_connected": False,
            "chromadb_ready": False,
            "ml_api_available": False
        }
        
        # Check Ollama connection
        if rag_engine:
            try:
                status["ollama_connected"] = rag_engine.check_ollama()
                status["chromadb_ready"] = rag_engine.check_chromadb()
                status["ml_api_available"] = rag_engine.check_ml_api()
            except Exception as e:
                logger.warning(f"Health check sub-components failed: {e}")
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Main chat endpoint
    
    Request JSON:
    {
        "sessionId": "session_123",
        "message": "Show me pump temperatures",
        "conversationHistory": [...],
        "realtimeData": {...},
        "databaseConnection": {...}
    }
    
    Response JSON:
    {
        "success": true,
        "text": "Here's the analysis...",
        "chartConfig": {...},
        "downloadLinks": {...},
        "mlInsights": {...},
        "sqlQuery": "SELECT...",
        "rowCount": 100
    }
    """
    
    if not rag_engine:
        return jsonify({
            "success": False,
            "text": "[ERROR] RAG service not initialized. Please check server logs.",
            "error": "RAG engine not available"
        }), 503
    
    try:
        # Parse request
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "Invalid JSON in request body"
            }), 400
        
        # Extract fields with safe defaults
        session_id = data.get("sessionId") or data.get("session_id") or "default"
        user_message = data.get("message") or data.get("userMessage") or ""
        conversation_history = data.get("conversationHistory") or data.get("conversation_history") or []
        realtime_data = data.get("realtimeData") or data.get("realtime_data")
        db_connection = data.get("databaseConnection") or data.get("database_connection") or {}
        
        # Validate
        if not user_message or not isinstance(user_message, str):
            logger.error(f"Invalid message: {user_message}")
            return jsonify({
                "success": False,
                "error": "Message is required and must be a string"
            }), 400
        
        logger.info(f"[CHAT] Chat request from session {session_id}: {user_message[:50]}...")
        
        # Get or initialize session memory
        if session_id not in session_memory:
            session_memory[session_id] = []
        
        # Process through RAG engine
        response = rag_engine.process_message(
            message=user_message,
            session_id=session_id,
            conversation_history=conversation_history,
            realtime_data=realtime_data,
            db_connection=db_connection
        )
        
        # Store in session memory
        session_memory[session_id].append({
            "user": user_message,
            "bot": response.get("text", ""),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep only last 20 messages per session
        if len(session_memory[session_id]) > 20:
            session_memory[session_id] = session_memory[session_id][-20:]
        
        logger.info(f"[SUCCESS] Chat response generated for session {session_id}")
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"[ERROR] Error in chat endpoint: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "text": "I encountered an error processing your request. Please try again.",
            "error": str(e)
        }), 500


@app.route('/api/generate-report', methods=['POST'])
def generate_report():
    """
    Generate report endpoint (basic implementation)
    
    Request JSON:
    {
        "message": "Generate weekly report",
        "timeRange": {...},
        "databaseConnection": {...}
    }
    """
    
    try:
        data = request.get_json()
        
        # For now, return placeholder response
        response = generate_report_placeholder(data)
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return jsonify({
            "success": False,
            "text": "Report generation failed. Please try again.",
            "error": str(e)
        }), 500


@app.route('/api/session/clear', methods=['POST'])
def clear_session():
    """Clear a specific session's memory"""
    try:
        data = request.get_json()
        session_id = data.get("sessionId")
        
        if session_id and session_id in session_memory:
            del session_memory[session_id]
            logger.info(f"Cleared session: {session_id}")
            return jsonify({"success": True}), 200
        
        return jsonify({"success": True, "message": "Session not found"}), 200
        
    except Exception as e:
        logger.error(f"Error clearing session: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    print("=" * 60)
    print("SWAT RAG Service with Mistral 7B")
    print("=" * 60)
    print(f"RAG Engine Status: {'[OK] Loaded' if rag_engine else '[ERROR] Not Loaded'}")
    print("Starting server on http://0.0.0.0:5001")
    print("=" * 60)
    
    # Run Flask app
    app.run(
        host="0.0.0.0",
        port=5001,
        debug=False,  # Set to False for production
        threaded=True
    )
