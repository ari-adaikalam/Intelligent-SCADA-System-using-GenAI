"""
SWAT RAG Engine - Core Intelligence
====================================
Implements the 6-stage RAG pipeline:
1. Query Understanding (Intent Classification)
2. Context Retrieval (ChromaDB + Session Memory)
3. SQL Generation (if data query)
4. Data Execution (MS SQL or Real-time)
5. ML Integration (if predictive query)
6. Response Generation (Mistral explanation)

Dependencies: Ollama, ChromaDB, pyodbc
"""

import logging
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Import sub-modules
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama not available")

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not available")

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    logger.warning("pyodbc not available")

# Import our modules
from sql_generator import SqlGenerator
from chart_generator import ChartGenerator
from report_generator import ReportGenerator


class RagEngine:
    """
    Main RAG engine that orchestrates the entire pipeline
    """
    
    def __init__(self):
        """Initialize RAG engine with all components"""
        
        logger.info("Initializing RAG Engine...")
        
        # Ollama client
        self.ollama_model = "mistral:7b-instruct-v0.3-q4_K_M"
        
        # ChromaDB client
        self.chroma_client = None
        self.collection = None
        
        if CHROMADB_AVAILABLE:
            try:
                self.chroma_client = chromadb.PersistentClient(
                    path="./chroma_db",
                    settings=Settings(anonymized_telemetry=False)
                )
                self.collection = self.chroma_client.get_collection("swat_knowledge")
                logger.info(f"[CHROMADB] Loaded ({self.collection.count()} documents)")
            except Exception as e:
                logger.error(f"ChromaDB initialization failed: {e}")
        
        # Sub-components
        self.sql_generator = SqlGenerator()
        self.chart_generator = ChartGenerator()
        self.report_generator = ReportGenerator()
        
        # ML API URL
        self.ml_api_url = "http://127.0.0.1:5000"
        
        logger.info("[INIT] RAG Engine initialized")
    
    # ========================================================================
    # MAIN PIPELINE
    # ========================================================================
    
    def process_message(
        self,
        message: str,
        session_id: str,
        conversation_history: List[Dict],
        realtime_data: Optional[Dict],
        db_connection: Dict
    ) -> Dict[str, Any]:
        """
        Main entry point - processes a user message through the 6-stage pipeline
        
        Returns:
        {
            "success": True,
            "text": "Response text",
            "chartConfig": {...},
            "downloadLinks": {...},
            "mlInsights": {...},
            "sqlQuery": "...",
            "rowCount": 100
        }
        """
        
        try:
            logger.info(f"[PIPELINE START] Processing: {message[:50]}...")
            
            # STAGE 1: Query Understanding
            logger.info("[STAGE 1] Analyzing intent...")
            intent = self._analyze_intent(message)
            logger.info(f"[STAGE 1] Intent: {intent.get('type', 'unknown')}")
            
            # STAGE 2: Context Retrieval
            logger.info("[STAGE 2] Retrieving context...")
            context = self._retrieve_context(message, conversation_history)
            logger.info(f"[STAGE 2] Retrieved {len(context.get('knowledge', []))} knowledge docs")
            
            # Route based on intent
            intent_type = intent.get("type", "general_query")
            
            if intent_type == "sql_query":
                response = self._handle_sql_query(
                    message, intent, context, db_connection
                )
            elif intent_type == "ml_analysis":
                response = self._handle_ml_analysis(
                    message, intent, context, realtime_data
                )
            elif intent_type == "report_generation":
                response = self._handle_report_generation(
                    message, intent, context, db_connection
                )
            else:
                response = self._handle_general_query(
                    message, context
                )
            
            logger.info(f"[PIPELINE END] Success: {response.get('success', False)}")
            return response
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            return {
                "success": False,
                "text": "I encountered an error processing your request. Please try again.",
                "error": str(e)
            }
    
    # ========================================================================
    # STAGE 1: INTENT CLASSIFICATION
    # ========================================================================
    
    def _analyze_intent(self, message: str) -> Dict[str, Any]:
        """
        Classify user intent using Mistral
        
        Returns:
        {
            "type": "sql_query" | "ml_analysis" | "report_generation" | "general_query",
            "time_range": "last_hour" | "yesterday" | ...,
            "components": ["P302", "P101"],
            "action": "show" | "analyze" | "compare" | "predict"
        }
        """
        
        # ============================================================
        # PRE-CHECK: Health/Status queries ALWAYS trigger ML
        # ============================================================
        message_lower = message.lower()
        
        health_phrases = [
            "is there any issue",
            "any issue",
            "is there a problem",
            "any problem", 
            "check system",
            "system status",
            "system health",
            "everything ok",
            "all good",
            "system ok",
            "any fault",
            "check health",
            "everything okay",
            "is everything ok",
            "are there any issues"
        ]
        
        if any(phrase in message_lower for phrase in health_phrases):
            logger.info("[INTENT] Health check detected (PRE-CHECK) -> ML ANALYSIS")
            return {
                "type": "ml_analysis",
                "action": "health_check",
                "components": []
            }
        
        # ============================================================
        # Continue with Mistral classification
        # ============================================================
        
        if not OLLAMA_AVAILABLE:
            logger.warning("Ollama not available, using rule-based intent")
            return self._rule_based_intent(message)
        
        try:
            prompt = f"""Analyze this user question about a SCADA water treatment system.

User Question: "{message}"

Classify the intent as ONE of these types:
- "sql_query": User wants to see historical data, trends, or statistics
- "ml_analysis": User wants ML predictions, anomaly explanations, or component health analysis
- "report_generation": User wants to generate/download a report
- "general_query": General questions about the system

Also extract:
- time_range: if mentioned (e.g., "last_hour", "yesterday", "this_week", "today")
- components: list of pump/sensor names mentioned (e.g., ["P302", "FIT101"])
- action: what they want to do (e.g., "show", "analyze", "compare", "predict")

Respond ONLY with JSON. No explanation.

Example response:
{{"type": "sql_query", "time_range": "last_hour", "components": ["P302"], "action": "show"}}"""

            response = ollama.generate(
                model=self.ollama_model,
                prompt=prompt,
                options={"temperature": 0.1}  # Low temperature for classification
            )
            
            # Parse JSON response
            intent = json.loads(response["response"])
            return intent
            
        except Exception as e:
            logger.warning(f"Mistral intent classification failed: {e}, using fallback")
            return self._rule_based_intent(message)
    
    def _rule_based_intent(self, message: str) -> Dict[str, Any]:
        """Fallback rule-based intent classification"""
        message_lower = message.lower()
        
        # HIGH PRIORITY: System health/status check (ALWAYS ML)
        health_phrases = [
            "is there any issue",
            "any issue",
            "is there a problem",
            "any problem",
            "check system",
            "system status",
            "system health",
            "everything ok",
            "all good",
            "system ok",
            "any fault",
            "check health"
        ]
        if any(phrase in message_lower for phrase in health_phrases):
            logger.info("[INTENT] Health check detected -> ML ANALYSIS")
            return {"type": "ml_analysis", "action": "analyze"}
        
        # ML analysis keywords (anomaly detection)
        if any(kw in message_lower for kw in [
            "anomaly", "why", "predict", "fault", "warning", 
            "alert", "critical", "diagnosis", "abnormal"
        ]):
            return {"type": "ml_analysis", "action": "analyze"}
        
        # Report generation keywords
        if any(kw in message_lower for kw in [
            "report", "generate", "download", "export", "create report"
        ]):
            return {"type": "report_generation", "action": "generate"}
        
        # SQL query keywords (default for most questions)
        if any(kw in message_lower for kw in [
            "show", "display", "what", "when", "how many", "list", 
            "temperature", "flow", "pressure", "level", "trend"
        ]):
            return {"type": "sql_query", "action": "show"}
        
        # Default to general query
        return {"type": "general_query", "action": "explain"}
    
    # ========================================================================
    # STAGE 2: CONTEXT RETRIEVAL
    # ========================================================================
    
    def _retrieve_context(
        self, 
        message: str, 
        conversation_history: List[Dict]
    ) -> Dict[str, Any]:
        """
        Retrieve relevant context from ChromaDB and conversation history
        
        Returns:
        {
            "knowledge": ["doc1", "doc2", ...],
            "conversation_history": [...],
            "session_summary": "..."
        }
        """
        
        context = {
            "knowledge": [],
            "conversation_history": conversation_history[-5:] if conversation_history else []
        }
        
        # Vector search in ChromaDB
        if self.collection:
            try:
                results = self.collection.query(
                    query_texts=[message],
                    n_results=3
                )
                
                if results and results["documents"]:
                    context["knowledge"] = results["documents"][0]
                    
            except Exception as e:
                logger.warning(f"ChromaDB query failed: {e}")
        
        return context
    
    # ========================================================================
    # STAGE 3-6: INTENT HANDLERS
    # ========================================================================
    
    def _handle_sql_query(
        self,
        message: str,
        intent: Dict,
        context: Dict,
        db_connection: Dict
    ) -> Dict[str, Any]:
        """Handle SQL data queries"""
        
        logger.info("[SQL QUERY] Generating SQL...")
        
        try:
            # Generate SQL using SqlGenerator
            sql_result = self.sql_generator.generate_and_execute(
                message=message,
                intent=intent,
                context=context,
                db_connection=db_connection,
                ollama_model=self.ollama_model
            )
            
            if not sql_result["success"]:
                return {
                    "success": False,
                    "text": sql_result.get("error", "SQL execution failed")
                }
            
            logger.info(f"[SQL QUERY] Executed, got {sql_result.get('row_count', 0)} rows")
            
            # Generate explanation using Mistral
            explanation = self._explain_sql_results(
                message=message,
                sql_query=sql_result["sql"],
                results=sql_result["data"],
                row_count=sql_result["row_count"],
                context=context
            )
            
            # Generate chart if applicable
            chart_config = None
            if sql_result["row_count"] > 0:
                chart_config = self.chart_generator.generate_chart(
                    data=sql_result["data"],
                    query_type=intent.get("action", "show")
                )
            
            return {
                "success": True,
                "text": explanation,
                "chartConfig": chart_config,
                "sqlQuery": sql_result["sql"],
                "rowCount": sql_result["row_count"]
            }
            
        except Exception as e:
            logger.error(f"SQL query handler failed: {e}")
            return {
                "success": False,
                "text": f"Failed to process data query: {str(e)}"
            }
    
    def _handle_ml_analysis(
        self,
        message: str,
        intent: Dict,
        context: Dict,
        realtime_data: Optional[Dict]
    ) -> Dict[str, Any]:
        """Handle ML prediction/analysis queries"""
        
        logger.info("[ML ANALYSIS] Calling ML API...")
        
        if not realtime_data:
            return {
                "success": True,
                "text": "I need real-time data to perform ML analysis. Please try asking about current system status."
            }
        
        # Retry logic with exponential backoff for thread-safety
        max_retries = 3
        retry_delay = 0.5  # Start with 500ms
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.debug(f"[ML ANALYSIS] Attempt {attempt}/{max_retries}")
                
                # Call ML API with longer timeout (ML inference can take 200-500ms)
                ml_response = requests.post(
                    f"{self.ml_api_url}/api/inference",
                    json={"payload": realtime_data.get("payload", {})},
                    timeout=10,  # 10 second timeout (generous for concurrent access)
                    headers={"X-Request-Source": "chatbot"}  # Identify source
                )
                
                if not ml_response.ok:
                    if attempt < max_retries:
                        logger.warning(f"[ML ANALYSIS] ML API returned {ml_response.status_code}, retrying...")
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    
                    return {
                        "success": False,
                        "text": "ML service is temporarily busy. Please try again in a moment."
                    }
                
                ml_result = ml_response.json()
                break  # Success, exit retry loop
                
            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    logger.warning(f"[ML ANALYSIS] Timeout on attempt {attempt}, retrying...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                    
                logger.error("[ML ANALYSIS] ML API timeout after retries")
                return {
                    "success": False,
                    "text": "ML analysis is taking longer than expected. The system may be processing live data. Please try again in a moment."
                }
                
            except requests.exceptions.ConnectionError:
                if attempt < max_retries:
                    logger.warning(f"[ML ANALYSIS] Connection error on attempt {attempt}, retrying...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                    
                logger.error("[ML ANALYSIS] Cannot connect to ML API")
                return {
                    "success": False,
                    "text": "Cannot connect to ML service. Please ensure the ML API is running."
                }
                
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"[ML ANALYSIS] Error on attempt {attempt}: {e}, retrying...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                    
                logger.error(f"[ML ANALYSIS] Unexpected error: {e}")
                return {
                    "success": False,
                    "text": f"ML analysis failed: {str(e)}"
                }
        
        # Successfully got ML result
        logger.info(f"[ML ANALYSIS] ML API returned: {ml_result.get('success', False)}")
        
        # Generate detailed explanation
        explanation = self._explain_ml_results(
            message=message,
            ml_result=ml_result,
            realtime_data=realtime_data,
            context=context
        )
        
        # Extract ML insights for frontend
        ml_insights = None
        if ml_result.get("success"):
            ml_insights = {
                "isAnomaly": ml_result.get("stage1", {}).get("isAnomaly", False),
                "state": ml_result.get("stage2", {}).get("state", "UNKNOWN"),
                "faultyComponent": ml_result.get("stage3", {}).get("component"),
                "confidence": ml_result.get("stage3", {}).get("confidence", 0.0),
                "recommendations": ml_result.get("recommendedActions", [])
            }
        
        return {
            "success": True,
            "text": explanation,
            "mlInsights": ml_insights
        }
    
    def _handle_report_generation(
        self,
        message: str,
        intent: Dict,
        context: Dict,
        db_connection: Dict
    ) -> Dict[str, Any]:
        """Handle report generation requests"""
        
        logger.info("[REPORT] Report generation requested")
        
        try:
            # Detect report format from message
            message_lower = message.lower()
            if "pdf" in message_lower:
                format_type = "pdf"
            elif "excel" in message_lower or "xlsx" in message_lower:
                format_type = "excel"
            elif "csv" in message_lower:
                format_type = "csv"
            elif "html" in message_lower:
                format_type = "html"
            else:
                format_type = "summary"  # Default to text summary
            
            # ============================================================
            # QUERY DATABASE FOR ACTUAL DATA
            # ============================================================
            logger.info("[REPORT] Querying database for actual data...")
            
            # Build time filter based on report request
            if "yesterday" in message_lower:
                time_filter = "ts >= DATEADD(day, -1, CAST(GETDATE() AS DATE)) AND ts < CAST(GETDATE() AS DATE)"
                logger.info("[REPORT] Time range: Yesterday")
            elif "today" in message_lower:
                time_filter = "ts >= CAST(GETDATE() AS DATE)"
                logger.info("[REPORT] Time range: Today")
            elif "week" in message_lower or "7 day" in message_lower:
                time_filter = "ts >= DATEADD(day, -7, GETDATE())"
                logger.info("[REPORT] Time range: Last 7 days")
            elif "month" in message_lower or "30 day" in message_lower:
                time_filter = "ts >= DATEADD(day, -30, GETDATE())"
                logger.info("[REPORT] Time range: Last 30 days")
            elif "daily" in message_lower:
                # Default daily: last 24 hours
                time_filter = "ts >= DATEADD(hour, -24, GETDATE())"
                logger.info("[REPORT] Time range: Last 24 hours")
            else:
                # Default: last 24 hours
                time_filter = "ts >= DATEADD(hour, -24, GETDATE())"
                logger.info("[REPORT] Time range: Default (Last 24 hours)")
            
            # Query comprehensive data for report
            report_data = None
            try:
                # ============================================================
                # USE TEMPLATE SQL FOR REPORTS (Fast & Reliable)
                # ============================================================
                logger.info("[REPORT] Using template SQL query for report data")
                
                # Build comprehensive SQL query directly (no Mistral - faster!)
                report_sql = f"""
                SELECT TOP 1000
                    ts,
                    CAST(JSON_VALUE(payload_json, '$.true_P101_motor_temp') AS FLOAT) AS P101_temp,
                    CAST(JSON_VALUE(payload_json, '$.true_P201_motor_temp') AS FLOAT) AS P201_temp,
                    CAST(JSON_VALUE(payload_json, '$.true_P302_motor_temp') AS FLOAT) AS P302_temp,
                    CAST(JSON_VALUE(payload_json, '$.true_FIT101') AS FLOAT) AS FIT101,
                    CAST(JSON_VALUE(payload_json, '$.true_FIT201') AS FLOAT) AS FIT201,
                    CAST(JSON_VALUE(payload_json, '$.true_LIT101') AS FLOAT) AS LIT101,
                    CAST(JSON_VALUE(payload_json, '$.true_LIT301') AS FLOAT) AS LIT301,
                    CAST(JSON_VALUE(payload_json, '$.true_PIT501') AS FLOAT) AS PIT501
                FROM raw_plant_data
                WHERE {time_filter}
                ORDER BY ts DESC
                """
                
                # Execute SQL directly via sql_generator
                import pyodbc
                conn_str = (
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                    f"SERVER={db_connection.get('server', 'localhost')};"
                    f"DATABASE={db_connection.get('database', 'SwatDB')};"
                    f"UID={db_connection.get('username', 'sa')};"
                    f"PWD={db_connection.get('password', '')};"
                    f"TrustServerCertificate=yes;"
                )
                
                conn = pyodbc.connect(conn_str, timeout=10)
                cursor = conn.cursor()
                cursor.execute(report_sql)
                
                columns = [column[0] for column in cursor.description]
                results = []
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                
                cursor.close()
                conn.close()
                
                if results:
                    row_count = len(results)
                    logger.info(f"[REPORT] Retrieved {row_count} rows for report")
                    report_data = {
                        "query_results": results,
                        "row_count": row_count
                    }
                else:
                    logger.warning("[REPORT] Database query returned no data")
                    
            except Exception as e:
                logger.warning(f"[REPORT] Failed to query database: {e}")
            
            # Fallback to context data if query failed
            if not report_data:
                logger.info("[REPORT] Using context data (may be empty)")
                report_data = context.get("data")
            
            # ============================================================
            # GENERATE REPORT WITH REAL DATA
            # ============================================================
            
            # Generate report
            report_result = self.report_generator.generate_report(
                report_type=message,
                data=report_data,
                format=format_type,
                time_range=intent.get("time_range")
            )
            
            if report_result.get("success"):
                # Build response text
                if format_type == "summary":
                    response_text = report_result.get("content", "Report generated successfully.")
                else:
                    response_text = f"📊 **{report_result.get('title', 'Report')} Generated**\n\n"
                    response_text += f"Format: {format_type.upper()}\n"
                    response_text += f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    
                    if report_result.get("download_available"):
                        response_text += f"Report ready for download\n"
                        response_text += f"📄 Filename: {report_result.get('filename', 'report.txt')}\n"
                    else:
                        response_text += report_result.get("error", "Report content displayed above.")
                
                return {
                    "success": True,
                    "text": response_text,
                    "reportData": report_result,
                    "downloadLinks": {
                        "report": report_result.get("filename")
                    } if report_result.get("download_available") else None
                }
            else:
                # Report generation failed
                error_msg = report_result.get("error", "Unknown error")
                
                response_text = f"❌ **Report Generation Failed**\n\n{error_msg}\n\n"
                
                # Provide helpful suggestions
                if "reportlab" in error_msg or "openpyxl" in error_msg:
                    response_text += "💡 **Try these alternatives:**\n"
                    response_text += "- Ask for a 'summary' report (text format)\n"
                    response_text += "- Ask for 'csv' format for spreadsheet export\n"
                    response_text += "- Use the Analytics Dashboard export feature\n"
                else:
                    response_text += "💡 **Suggestions:**\n"
                    response_text += "- Try: 'Generate a daily summary report'\n"
                    response_text += "- Try: 'Create a weekly performance report'\n"
                    response_text += "- Try: 'Export data as CSV'\n"
                
                return {
                    "success": True,
                    "text": response_text,
                    "downloadLinks": None
                }
        
        except Exception as e:
            logger.error(f"[REPORT] Report generation error: {e}", exc_info=True)
            return {
                "success": True,
                "text": f"⚠️ **Report Generation Error**\n\n{str(e)}\n\n" \
                       "Please try again or use a different report format.",
                "downloadLinks": None
            }
    
    def _handle_general_query(
        self,
        message: str,
        context: Dict
    ) -> Dict[str, Any]:
        """Handle general questions about the system"""
        
        logger.info("[GENERAL] Handling general query")
        
        if not OLLAMA_AVAILABLE:
            return {
                "success": True,
                "text": "I can help you query SCADA data and analyze system health. " \
                       "Try asking about pump temperatures, flow rates, or anomaly status."
            }
        
        try:
            # Build prompt with context
            knowledge_context = "\n\n".join(context.get("knowledge", [])[:2])
            
            prompt = f"""You are an expert assistant for a SCADA water treatment system.

Relevant System Knowledge:
{knowledge_context}

User Question: {message}

Provide a helpful, concise response. If the question is about specific data or predictions, 
suggest that the user ask for specific queries like "Show pump temperatures" or 
"Why is P302 showing an anomaly?"

Keep your response under 200 words."""

            response = ollama.generate(
                model=self.ollama_model,
                prompt=prompt,
                options={"temperature": 0.7}
            )
            
            return {
                "success": True,
                "text": response["response"]
            }
            
        except Exception as e:
            logger.error(f"General query failed: {e}")
            return {
                "success": True,
                "text": "I can help you query SCADA data and analyze system health. " \
                       "Try asking about pump temperatures, flow rates, or anomaly status."
            }
    
    # ========================================================================
    # EXPLANATION GENERATORS
    # ========================================================================
    
    def _explain_sql_results(
        self,
        message: str,
        sql_query: str,
        results: List[Dict],
        row_count: int,
        context: Dict
    ) -> str:
        """Generate natural language explanation of SQL results"""
        
        if not OLLAMA_AVAILABLE or row_count == 0:
            return f"Query returned {row_count} results."
        
        try:
            # Sample data for explanation (first 5 rows)
            sample_data = json.dumps(results[:5], indent=2, default=str)
            
            prompt = f"""User asked: "{message}"

SQL Query executed:
{sql_query}

Results: {row_count} rows returned

Sample data (first 5 rows):
{sample_data}

Provide a detailed analysis:
1. Summarize what the data shows
2. Highlight any notable patterns, anomalies, or trends
3. Compare values to normal ranges if applicable
4. Provide actionable insights

Keep response under 250 words. Use clear formatting."""

            response = ollama.generate(
                model=self.ollama_model,
                prompt=prompt,
                options={"temperature": 0.7}
            )
            
            return response["response"]
            
        except Exception as e:
            logger.error(f"SQL explanation failed: {e}")
            return f"Found {row_count} records matching your query."
    
    def _explain_ml_results(
        self,
        message: str,
        ml_result: Dict,
        realtime_data: Dict,
        context: Dict
    ) -> str:
        """Generate detailed explanation of ML predictions"""
        
        if not OLLAMA_AVAILABLE:
            # Fallback explanation
            stage1 = ml_result.get("stage1", {})
            stage2 = ml_result.get("stage2", {})
            stage3 = ml_result.get("stage3", {})
            actions = ml_result.get("recommendedActions", [])
            
            text = f"**ML Analysis Results:**\n\n"
            
            # Stage 1: ALWAYS use "Issue Detection" (not anomaly)
            text += f"**Stage 1 - Issue Detection:** "
            text += f"{'Issue detected' if stage1.get('isAnomaly') else 'No issues detected'} "
            text += f"({stage1.get('confidence', 0)*100:.0f}% confidence)\n\n"
            
            # Stage 2: System State Classification
            text += f"**Stage 2 - System State:** {stage2.get('state', 'UNKNOWN')}\n\n"
            
            # Stage 3: Faulty Component (if applicable)
            if stage3.get("component"):
                text += f"**Stage 3 - Faulty Component:** {stage3.get('component')} "
                text += f"({stage3.get('confidence', 0)*100:.0f}% confidence)\n\n"
            
            if actions:
                text += "**Recommended Actions:**\n"
                for action in actions[:5]:
                    text += f"• {action}\n"
            
            return text
        
        try:
            # Use Mistral for detailed explanation
            prompt = f"""User asked: "{message}"

ML Inference Results:
{json.dumps(ml_result, indent=2)}

Current system metrics:
{json.dumps(realtime_data.get('payload', {}), indent=2, default=str)}

Provide a DETAILED analysis with these sections:

**1. Issue Detection (Stage 1):**
- Is there any issue with the system currently?
- Confidence level
- What this means operationally

**2. System State Classification (Stage 2):**
- Current state: NORMAL, WARNING, or CRITICAL
- Confidence level
- Why the system is in this state
- Contributing factors

**3. Faulty Component Identification (Stage 3):**
- If applicable, which component is problematic
- Specific metrics causing concern
- Confidence level

**4. Root Cause:**
- Analyze motor temperature, current, vibration
- Compare to normal ranges (temp: 35-45°C, vibration: <1.5)
- Explain correlations

**5. Recommended Actions:**
Use the EXACT action text from the ML results with emojis.

Keep response under 300 words. Be technical but clear."""

            response = ollama.generate(
                model=self.ollama_model,
                prompt=prompt,
                options={"temperature": 0.6}
            )
            
            return response["response"]
            
        except Exception as e:
            logger.error(f"ML explanation failed: {e}")
            return "ML analysis completed. Check the ML insights panel for details."
    
    # ========================================================================
    # HEALTH CHECKS
    # ========================================================================
    
    def check_ollama(self) -> bool:
        """Check if Ollama is accessible"""
        try:
            if not OLLAMA_AVAILABLE:
                return False
            ollama.list()
            return True
        except:
            return False
    
    def check_chromadb(self) -> bool:
        """Check if ChromaDB is accessible"""
        return self.collection is not None
    
    def check_ml_api(self) -> bool:
        """Check if ML API is accessible"""
        try:
            response = requests.get(f"{self.ml_api_url}/health", timeout=2)
            return response.ok
        except:
            return False
