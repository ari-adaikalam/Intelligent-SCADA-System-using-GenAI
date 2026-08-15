# 🏗️ SWAT AI CHATBOT - COMPLETE ARCHITECTURE DOCUMENTATION

**Project:** SWAT Dashboard with AI-Powered Natural Language Interface  
**Version:** 1.0  
**Last Updated:** January 26, 2026  
**Author:** AI Integration Team

---

## 📋 **Table of Contents**

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Component Breakdown](#component-breakdown)
4. [Data Flow Explained](#data-flow-explained)
5. [RAG System Deep Dive](#rag-system-deep-dive)
6. [Session Memory Design](#session-memory-design)
7. [ML Integration](#ml-integration)
8. [API Specifications](#api-specifications)
9. [Database Schema](#database-schema)
10. [Security Considerations](#security-considerations)
11. [Performance Optimization](#performance-optimization)
12. [Deployment Architecture](#deployment-architecture)

---

## 🎯 **System Overview**

### **What This System Does**

The SWAT AI Chatbot is an intelligent natural language interface that allows operators to:

1. **Query historical data** using plain English
2. **Get ML-powered predictive insights** about system health
3. **Generate automated reports** with visualizations
4. **Receive maintenance recommendations** based on real-time analysis
5. **Access both real-time and historical SCADA data** conversationally

### **Key Technologies**

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | HTML/CSS/JavaScript + Chart.js | Chat interface with inline visualizations |
| **Backend** | ASP.NET Core 8.0 (C#) | API orchestration, session management |
| **AI Engine** | Mistral 7B (via Ollama) | Natural language understanding & SQL generation |
| **RAG System** | ChromaDB + LangChain | Context retrieval & knowledge augmentation |
| **ML Models** | TensorFlow/XGBoost (Existing) | Predictive maintenance (3-stage pipeline) |
| **Database** | MS SQL Server | Time-series SCADA data storage |
| **Real-time** | SignalR | Live data streaming |

### **Why This Architecture?**

- ✅ **Local AI (Privacy-First):** All inference happens on your RTX 3060, no cloud dependency
- ✅ **Fast Response:** 3-5 second end-to-end query time
- ✅ **Scalable:** Can handle multiple concurrent users
- ✅ **Maintainable:** Clear separation of concerns across layers
- ✅ **Cost-Effective:** Zero API costs, runs on existing hardware

---



┌───────────────────────────────┐
│        USER / BROWSER         │
│ SWAT Dashboard + AI Chat (UI) │
└───────────────┬───────────────┘
                │ HTTPS / SignalR
                ▼
┌───────────────────────────────┐
│   ASP.NET Core Backend (C#)   │
│ Session Memory                │
└───────────────┬───────────────┘
                │ HTTP/JSON (5001)
                ▼
┌───────────────────────────────┐
│   Python RAG Service (Flask)  │
│ RAG Engine + ChromaDB         │
│ SQL Gen + Validation + Reports│
└───────┬───────────────┬───────┘
        │               │
        │               └──► ML API 
        │                     (3-stage ML inference)
        │
        └──► Ollama LLM 
        |      Mistral 7B (GPU, local)
        |
        └──► MS SQL Server (SCADA Data)

## 📐 **Architecture Diagram**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER BROWSER (Client)                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                    SWAT Dashboard Web Interface                       │ │
│  │  ┌─────────────┬──────────────┬──────────────┬─────────────────────┐ │ │
│  │  │ Live Data   │  Analytics   │  💬 AI Chat  │  Settings           │ │ │
│  │  │ Dashboard   │  Graphs      │  (NEW TAB)   │                     │ │ │
│  │  └─────────────┴──────────────┴──────────────┴─────────────────────┘ │ │
│  │                                                                       │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │  Chat Interface (chat.js)                                       │ │ │
│  │  │  • Message history display                                      │ │ │
│  │  │  • Typing indicator                                             │ │ │
│  │  │  • Inline Chart.js visualizations                               │ │ │
│  │  │  • Download buttons (PDF/Excel)                                 │ │ │
│  │  │  • Real-time status badge                                       │ │ │
│  │  │  • Session memory (in-memory)                                   │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↕ HTTPS (SignalR for real-time)
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ASP.NET CORE BACKEND (C# Layer)                          │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Controllers/                                                         │ │
│  │  ├── ChatController.cs                                                │ │
│  │  │   • POST /api/chat/message    → Process user message              │ │
│  │  │   • GET  /api/chat/history    → Retrieve session history          │ │
│  │  │   • POST /api/chat/clear      → Clear session                     │ │
│  │  │   • GET  /api/chat/status     → Check AI service health           │ │
│  │  ├── DashboardController.cs (Existing)                               │ │
│  │  ├── AnalyticsController.cs (Existing)                               │ │
│  │  └── ExportController.cs (Existing)                                  │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    ↕                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Services/                                                            │ │
│  │  ├── ChatService.cs                                                   │ │
│  │  │   • Bridges C# backend with Python RAG API                        │ │
│  │  │   • Injects real-time data when needed                            │ │
│  │  │   • Manages HTTP client to RAG service                            │ │
│  │  │   • Handles retry logic and error recovery                        │ │
│  │  ├── DatabaseService.cs (Existing)                                   │ │
│  │  ├── MlInferenceService.cs (Existing)                                │ │
│  │  └── ExportService.cs (Existing)                                     │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    ↕                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Session Management (In-Memory)                                      │ │
│  │  • ConcurrentDictionary<sessionId, ChatSession>                      │ │
│  │  • Auto-expiration after 2 hours inactivity                          │ │
│  │  • Thread-safe operations                                            │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↕ HTTP/JSON
┌─────────────────────────────────────────────────────────────────────────────┐
│               PYTHON RAG SERVICE (Port 5001)                                │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Flask API (rag_api.py)                                               │ │
│  │  ├── POST /api/chat              → Main chat endpoint                │ │
│  │  ├── POST /api/generate-report   → Report generation                 │ │
│  │  ├── GET  /health                → Health check                       │ │
│  │  └── POST /api/initialize        → Initialize/reset RAG system       │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    ↕                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  RAG Engine (rag_engine.py)                                          │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │ STAGE 1: Query Understanding                                    │ │ │
│  │  │  • Parse user intent (SQL query / ML analysis / Report)         │ │ │
│  │  │  • Extract entities (time range, components, actions)           │ │ │
│  │  │  • Detect if real-time data needed                              │ │ │
│  │  │  → Uses Mistral 7B for intent classification                    │ │ │
│  │  ├─────────────────────────────────────────────────────────────────┤ │ │
│  │  │ STAGE 2: Context Retrieval (RAG Core)                           │ │ │
│  │  │  • Vector search in ChromaDB                                    │ │ │
│  │  │  • Retrieve relevant database schema                            │ │ │
│  │  │  • Fetch component descriptions                                 │ │ │
│  │  │  • Get session conversation history                             │ │ │
│  │  │  → Builds enriched context for LLM                              │ │ │
│  │  ├─────────────────────────────────────────────────────────────────┤ │ │
│  │  │ STAGE 3: SQL Generation (if data query)                         │ │ │
│  │  │  • Mistral generates SQL based on context                       │ │ │
│  │  │  • SQL validator checks safety (no DELETE/DROP)                 │ │ │
│  │  │  • Inject parameters for time range                             │ │ │
│  │  │  → Safe, read-only SQL queries                                  │ │ │
│  │  ├─────────────────────────────────────────────────────────────────┤ │ │
│  │  │ STAGE 4: Data Execution                                         │ │ │
│  │  │  • Execute SQL against MS SQL via pyodbc                        │ │ │
│  │  │  • OR fetch real-time data from C# API                          │ │ │
│  │  │  • Handle query timeouts and errors                             │ │ │
│  │  │  → Returns structured data                                      │ │ │
│  │  ├─────────────────────────────────────────────────────────────────┤ │ │
│  │  │ STAGE 5: ML Integration (if predictive query)                   │ │ │
│  │  │  • Call ML API (Port 5000) with real-time data                  │ │ │
│  │  │  • Get Stage 1/2/3 predictions                                  │ │ │
│  │  │  • Extract recommended actions                                  │ │ │
│  │  │  → ML insights ready for explanation                            │ │ │
│  │  ├─────────────────────────────────────────────────────────────────┤ │ │
│  │  │ STAGE 6: Response Generation                                    │ │ │
│  │  │  • Mistral explains results in natural language                 │ │ │
│  │  │  • Generates Chart.js config if visualization needed            │ │ │
│  │  │  • Formats detailed analysis (uses exact ML action text)        │ │ │
│  │  │  → User-friendly response with charts                           │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    ↕                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  ChromaDB (Vector Database)                                          │ │
│  │  • Persistent storage at: PythonRagService/chroma_db/                │ │
│  │  • Embeddings: 384 dimensions (all-MiniLM-L6-v2)                     │ │
│  │  • Collections:                                                       │ │
│  │    - swat_knowledge (database schema, components)                    │ │
│  │  • Query Performance: <50ms for vector search                        │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    ↕                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Report Generator (report_generator.py)                              │ │
│  │  • PDF: ReportLab with company branding                              │ │
│  │  • Excel: openpyxl with formatted sheets                             │ │
│  │  • Charts embedded in reports                                        │ │
│  │  • Saves to: /mnt/user-data/outputs/                                 │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↕ HTTP
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OLLAMA LLM SERVER (Port 11434)                           │
│  • Model: Mistral 7B Instruct v0.3 (4-bit quantized)                       │
│  • VRAM Usage: ~4.8 GB                                                      │
│  • Context Window: 8192 tokens                                              │
│  • Inference Speed: 40-60 tokens/second on RTX 3060                         │
│  • GPU Acceleration: CUDA 11.2+                                             │
│  • Endpoint: http://127.0.0.1:11434/api/generate                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↕ HTTP
┌─────────────────────────────────────────────────────────────────────────────┐
│                 EXISTING ML API (Port 5000)                                 │
│  • Stage 1: Anomaly Detection (Autoencoder/LOF/IForest/XGBoost)            │
│  • Stage 2: State Classification (LSTM/CNN/XGBoost)                         │
│  • Stage 3: Component Identification (MLP/LightGBM/XGBoost)                 │
│  • 60-sample buffer for temporal analysis                                   │
│  • Recommended actions with emojis (🔧, 📋, 💧, etc.)                       │
│  • Returns: confidence scores, component health, alerts                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↕ SQL Queries
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MS SQL SERVER DATABASE                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Database: swat                                                       │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │  Table: raw_plant_data                                          │ │ │
│  │  │  ├── id (int, PK, IDENTITY)                                     │ │ │
│  │  │  ├── ts (datetime2)                                             │ │ │
│  │  │  ├── plant_id (nvarchar(50))                                    │ │ │
│  │  │  └── payload_json (nvarchar(MAX))                               │ │ │
│  │  │      {                                                          │ │ │
│  │  │        "P101": 2, "P201": 2, ... (actuator states)             │ │ │
│  │  │        "true_FIT101": 2.48, ... (sensor readings)              │ │ │
│  │  │        "true_P101_motor_temp": 42.22, ... (motor health)       │ │ │
│  │  │        "timestamp": "2026-01-26T12:00:00",                     │ │ │
│  │  │        "system_status": "RUN"                                  │ │ │
│  │  │      }                                                          │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  │  • Indexes: idx_ts, idx_plant_id                                     │ │
│  │  • Retention: 1 year (configurable)                                  │ │
│  │  • Growth Rate: ~10MB/day                                             │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧩 **Component Breakdown**

### **1. Frontend - Chat Interface (chat.js)**

**Responsibility:** User interaction and visualization

**Key Features:**
- Message rendering (user = right bubble, bot = left bubble)
- Markdown support for formatted responses
- Inline Chart.js rendering
- Download button management
- Typing indicators
- Auto-scroll to latest message
- Session persistence (in-memory)

**Technology Stack:**
- Vanilla JavaScript (ES6+)
- Chart.js 4.x for visualizations
- CSS Grid for layout
- Fetch API for backend communication

**Performance:**
- Message render time: <50ms
- Chart render time: <200ms
- Smooth scrolling with 60fps

---

### **2. Backend - ChatController.cs**

**Responsibility:** API orchestration and session management

**Key Endpoints:**

```csharp
POST /api/chat/message
Request:
{
  "sessionId": "uuid-or-timestamp",
  "message": "Show me pump temperatures",
  "includeRealtime": true
}

Response:
{
  "text": "Here's the current pump temperature analysis...",
  "chartConfig": { /* Chart.js config */ },
  "downloadLinks": {
    "pdf": "/downloads/report_xyz.pdf",
    "excel": "/downloads/report_xyz.xlsx"
  },
  "mlInsights": {
    "isAnomaly": true,
    "state": "WARNING",
    "faultyComponent": "P302",
    "confidence": 0.87,
    "recommendations": ["🔧 Inspect UF feed pump P302", ...]
  }
}
```

**Session Storage:**
```csharp
private static ConcurrentDictionary<string, ChatSession> _sessions = new();

public class ChatSession
{
    public List<ChatMessage> ConversationHistory { get; }
    public DateTime CreatedAt { get; }
    public DateTime LastActivity { get; private set; }
    public bool IsExpired => (DateTime.UtcNow - LastActivity).TotalHours > 2;
}
```

**Real-time Data Injection:**
- When `includeRealtime: true`, fetches latest row from `DatabaseService`
- Includes in RAG API request for ML analysis

---

### **3. Backend - ChatService.cs**

**Responsibility:** Python RAG API integration

**Key Methods:**

```csharp
public async Task<ChatResponse> ProcessMessageAsync(
    string userMessage,
    List<ChatMessage> conversationHistory,
    RawPlantData? realtimeData = null)
{
    // Build request payload
    var payload = new {
        message = userMessage,
        conversation_history = conversationHistory,
        realtime_data = realtimeData?.Payload,
        database_connection = GetDbConfig(),
        session_id = GenerateSessionId()
    };
    
    // Call Python RAG API
    var response = await _httpClient.PostAsJsonAsync(
        "http://127.0.0.1:5001/api/chat",
        payload
    );
    
    // Parse and return
    return await response.Content.ReadFromJsonAsync<ChatResponse>();
}
```

**Error Handling:**
- Retry logic (3 attempts with exponential backoff)
- Graceful degradation (returns cached response if RAG fails)
- Logs all errors to ILogger

---

### **4. Python RAG Service - rag_api.py**

**Responsibility:** AI orchestration and RAG pipeline execution

**Main Chat Flow:**

```python
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    
    # Step 1: Understand intent
    intent = analyze_intent(data["message"])
    # → Returns: {"type": "sql_query", "time_range": "last_hour", ...}
    
    # Step 2: Retrieve context
    context = retrieve_context(data["message"], data["session_id"])
    # → Searches ChromaDB, gets session history
    
    # Step 3: Route to appropriate handler
    if intent["type"] == "sql_query":
        response = handle_sql_query(data, context)
    elif intent["type"] == "ml_analysis":
        response = handle_ml_analysis(data, context)
    elif intent["type"] == "report_generation":
        response = handle_report_generation(data, context)
    
    # Step 4: Store in session memory
    session_memory[data["session_id"]].append({
        "user": data["message"],
        "bot": response["text"]
    })
    
    return jsonify(response)
```

**Intent Classification:**
```python
def analyze_intent(message: str) -> dict:
    prompt = f"""
    Classify this user message:
    Message: "{message}"
    
    Classify as:
    - sql_query: User wants historical data
    - ml_analysis: User wants ML predictions
    - report_generation: User wants report/export
    - general_query: General question
    
    Extract:
    - time_range: if mentioned (e.g., "last week")
    - components: which pumps/sensors
    - action: what they want
    
    Response in JSON only.
    """
    
    response = ollama.generate(model="mistral:7b-instruct-v0.3", prompt=prompt, format="json")
    return json.loads(response["response"])
```

**SQL Generation with Safety:**
```python
def handle_sql_query(data, context):
    # Generate SQL
    sql = generate_sql_with_mistral(data["message"], context)
    
    # Validate (CRITICAL)
    if not validate_sql(sql):
        return {"error": "Unsafe query detected"}
    
    # Execute
    results = execute_sql(sql, data["database_connection"])
    
    # Explain results
    explanation = explain_results_with_mistral(results, data["message"])
    
    # Generate chart
    chart = generate_chart_config(results)
    
    return {
        "text": explanation,
        "chartConfig": chart,
        "sqlQuery": sql,  # For debugging
        "rowCount": len(results)
    }

def validate_sql(sql: str) -> bool:
    sql_lower = sql.lower().strip()
    
    # Must start with SELECT
    if not sql_lower.startswith('select'):
        return False
    
    # Blacklist dangerous keywords
    dangerous = ['insert', 'update', 'delete', 'drop', 'alter', 'truncate', 'exec']
    if any(kw in sql_lower for kw in dangerous):
        return False
    
    return True
```

---

### **5. RAG System - ChromaDB**

**Responsibility:** Vector-based knowledge retrieval

**Embedding Model:** `all-MiniLM-L6-v2` (384 dimensions)

**Knowledge Documents Stored:**

```python
knowledge_base = [
    {
        "id": "schema_main",
        "text": """
        Table: raw_plant_data
        Columns: id, ts, plant_id, payload_json
        JSON structure: actuators (P101-P501, MV101-MV304),
                       sensors (FIT, LIT, PIT, AIT, DPIT),
                       motor_health (temp, current, vibration)
        """,
        "metadata": {"type": "database_schema"}
    },
    {
        "id": "components_pumps",
        "text": """
        P101: Primary intake pump (Stage 1)
        P201/P203/P205: Secondary treatment (Stage 2)
        P302: Ultrafiltration pump (Stage 3)
        P402/P403: Reverse osmosis (Stage 4)
        P501: Distribution pump (Stage 5)
        
        Normal ranges:
        - Motor temp: 35-45°C
        - Vibration: <1.5 normal, >1.5 warning, >2.0 critical
        """,
        "metadata": {"type": "component_info"}
    },
    {
        "id": "components_sensors",
        "text": """
        FIT: Flow Indicator Transmitter (L/min)
        LIT: Level Indicator Transmitter (mm)
        PIT: Pressure Indicator Transmitter (kPa)
        DPIT: Differential Pressure
        AIT: Analog Indicator Transmitter
        
        Naming: [TYPE][STAGE][NUMBER]
        Example: FIT201 = Flow sensor, Stage 2, sensor #1
        """,
        "metadata": {"type": "sensor_info"}
    },
    {
        "id": "ml_models",
        "text": """
        ML Pipeline (Port 5000):
        - Stage 1: Anomaly Detection
        - Stage 2: State Classification (NORMAL/DEGRADING/FAULTED)
        - Stage 3: Component Identification
        
        Requires 60-sample buffer for temporal analysis.
        Returns: confidence scores, recommended actions.
        """,
        "metadata": {"type": "ml_info"}
    }
]
```

**Vector Search Example:**
```python
# User asks: "What sensors measure flow?"
results = collection.query(
    query_texts=["What sensors measure flow?"],
    n_results=3
)

# ChromaDB returns (cosine similarity):
# 1. components_sensors (similarity: 0.89) - FIT description
# 2. schema_main (similarity: 0.72) - JSON structure
# 3. components_pumps (similarity: 0.45) - Pump info
```

This context is then injected into Mistral's prompt for accurate response generation.

---

## 🔄 **Data Flow Explained**

### **Example 1: SQL Query - "Show pump temperatures for last hour"**

```
┌─────────────────────────────────────────────────────────────┐
│ USER TYPES: "Show pump temperatures for last hour"         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (chat.js)                                          │
│ • Adds message to UI (user bubble)                          │
│ • Shows typing indicator                                    │
│ • POST /api/chat/message {message, sessionId}               │
└─────────────────────────────────────────────────────────────┘
                          ↓ (HTTP Request)
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (ChatController.cs)                                 │
│ • Retrieves/creates session                                 │
│ • No real-time data needed (historical query)               │
│ • Calls ChatService.ProcessMessageAsync()                   │
└─────────────────────────────────────────────────────────────┘
                          ↓ (HTTP Request)
┌─────────────────────────────────────────────────────────────┐
│ PYTHON RAG API (rag_api.py)                                 │
│ • Receives: {message, conversation_history, db_connection}  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Intent Analysis (Mistral 7B)                      │
│ Prompt: "Classify: 'Show pump temperatures for last hour'" │
│ Response: {                                                 │
│   "type": "sql_query",                                      │
│   "time_range": "last_hour",                                │
│   "components": ["P101","P201","P203",...],                 │
│   "action": "show",                                         │
│   "visualization": "line_chart"                             │
│ }                                                           │
│ Time: ~1.5 seconds                                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: Context Retrieval (ChromaDB)                      │
│ Query: "pump temperatures"                                  │
│ Retrieved:                                                  │
│ • Database schema (JSON_VALUE extraction syntax)            │
│ • Pump component info (P101-P501 descriptions)              │
│ • Normal temperature ranges (35-45°C)                       │
│ Time: ~30ms                                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: SQL Generation (Mistral 7B)                       │
│ Prompt includes:                                            │
│ • User question                                             │
│ • Retrieved schema context                                  │
│ • Time range constraint                                     │
│                                                             │
│ Generated SQL:                                              │
│ SELECT                                                      │
│   ts,                                                       │
│   JSON_VALUE(payload_json,'$.true_P101_motor_temp') P101,  │
│   JSON_VALUE(payload_json,'$.true_P201_motor_temp') P201,  │
│   ... (all 8 pumps)                                         │
│ FROM raw_plant_data                                         │
│ WHERE ts >= DATEADD(hour, -1, GETDATE())                   │
│ ORDER BY ts                                                 │
│ Time: ~2 seconds                                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3B: SQL Validation                                   │
│ ✅ Starts with SELECT                                       │
│ ✅ No dangerous keywords (INSERT/DELETE/DROP)               │
│ ✅ Approved for execution                                   │
│ Time: <1ms                                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 4: SQL Execution (MS SQL)                            │
│ • Connect via pyodbc                                        │
│ • Execute query                                             │
│ • Returns 60 rows (1 per minute for last hour)             │
│ • Each row has 8 temperature values                         │
│ Time: ~150ms                                                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 5: Result Explanation (Mistral 7B)                   │
│ Prompt:                                                     │
│ "User asked: 'Show pump temperatures for last hour'        │
│  SQL executed: [query]                                      │
│  Results (60 rows): [first 10 rows shown]                  │
│                                                             │
│  Provide detailed analysis:                                 │
│  1. Summarize temperature trends                            │
│  2. Highlight any pumps exceeding normal range             │
│  3. Compare relative temperatures                           │
│  4. Actionable insights"                                    │
│                                                             │
│ Response:                                                   │
│ "Over the past hour, pump temperatures remained stable     │
│  for most units. However, P302 averaged 46.2°C, which is   │
│  above the normal range of 35-45°C. This elevated temp     │
│  suggests increased load or potential cooling issues.      │
│  All other pumps operated within normal parameters."       │
│ Time: ~2 seconds                                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 6: Chart Generation                                  │
│ Chart.js Config:                                            │
│ {                                                           │
│   type: "line",                                             │
│   data: {                                                   │
│     labels: [timestamps from 60 rows],                      │
│     datasets: [                                             │
│       {label: "P101", data: [...], color: "blue"},         │
│       {label: "P201", data: [...], color: "green"},        │
│       ...                                                   │
│       {label: "P302", data: [...], color: "red"}  // Hot!  │
│     ]                                                       │
│   },                                                        │
│   options: {/* responsive, scales, etc */}                  │
│ }                                                           │
│ Time: ~50ms                                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ PYTHON RAG API RETURNS                                      │
│ {                                                           │
│   "text": "Over the past hour, pump temperatures...",      │
│   "chartConfig": {/* Chart.js config */},                   │
│   "downloadLinks": null,  // No report generated           │
│   "sqlQuery": "SELECT...",  // For debugging               │
│   "rowCount": 60                                            │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                          ↓ (HTTP Response)
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (ChatController.cs)                                 │
│ • Stores conversation in session                            │
│ • Returns response to frontend                              │
└─────────────────────────────────────────────────────────────┘
                          ↓ (HTTP Response)
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (chat.js)                                          │
│ • Hides typing indicator                                    │
│ • Renders bot message bubble with text                      │
│ • Creates Chart.js canvas                                   │
│ • Renders line chart with 8 pump temperature series         │
│ • Auto-scrolls to show new content                          │
│ Time: ~150ms rendering                                      │
└─────────────────────────────────────────────────────────────┘

TOTAL TIME: ~4-5 seconds from user press "Send" to chart displayed
```

---

### **Example 2: ML Analysis - "Why is P302 showing anomaly?"**

```
┌─────────────────────────────────────────────────────────────┐
│ USER TYPES: "Why is P302 showing anomaly?"                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND                                                    │
│ • Detects "anomaly" keyword                                 │
│ • Sets includeRealtime: true                                │
│ • POST /api/chat/message                                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (ChatController.cs)                                 │
│ • Calls DatabaseService.GetLatestDataAsync()                │
│ • Gets current payload from raw_plant_data                  │
│ • Injects into RAG request                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ PYTHON RAG API                                              │
│ • Receives realtime_data: {payload: {...}}                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Intent → "ml_analysis"                            │
│ Extracted: component="P302", action="explain_anomaly"      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: Context Retrieval                                 │
│ Retrieved:                                                  │
│ • P302 description (Ultrafiltration pump)                   │
│ • Normal operating ranges                                   │
│ • ML model capabilities                                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: Call ML API (Port 5000)                           │
│ POST http://127.0.0.1:5000/api/inference                    │
│ Body: {payload: {P302: 2, true_P302_motor_temp: 46.5, ...}}│
│                                                             │
│ ML API Returns:                                             │
│ {                                                           │
│   "success": true,                                          │
│   "stage1": {                                               │
│     "isAnomaly": true,                                      │
│     "confidence": 0.87                                      │
│   },                                                        │
│   "stage2": {                                               │
│     "state": "WARNING",                                     │
│     "confidence": 0.92                                      │
│   },                                                        │
│   "stage3": {                                               │
│     "component": "P302",                                    │
│     "confidence": 0.85,                                     │
│     "top3": [                                               │
│       {"component": "P302", "confidence": 0.85},            │
│       {"component": "P201", "confidence": 0.08},            │
│       {"component": "P501", "confidence": 0.04}             │
│     ]                                                       │
│   },                                                        │
│   "componentHealth": {                                      │
│     "P302": {                                               │
│       "status": "DEGRADING",                                │
│       "icon": "🟡",                                         │
│       "message": "Degrading - Schedule maintenance"         │
│     }                                                       │
│   },                                                        │
│   "recommendedActions": [                                   │
│     "🔧 Inspect UF feed pump P302",                         │
│     "📋 Check UF membrane differential pressure",           │
│     "💧 Consider membrane backwash or cleaning"             │
│   ]                                                         │
│ }                                                           │
│ Time: ~150ms                                                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE 4: Detailed Explanation (Mistral 7B)                 │
│ Prompt:                                                     │
│ "User asked: 'Why is P302 showing anomaly?'                │
│                                                             │
│  ML Results: [full JSON above]                              │
│                                                             │
│  Current P302 metrics:                                      │
│  - Motor temp: 46.5°C (normal: 35-45°C)                    │
│  - Vibration: 1.789 (threshold: 1.5)                       │
│  - Current: 6.441A (elevated)                               │
│                                                             │
│  Provide DETAILED analysis:                                 │
│  1. Anomaly Status explanation                              │
│  2. System State reasoning                                  │
│  3. Component Analysis with specific metrics                │
│  4. Root Cause analysis                                     │
│  5. Use EXACT recommended actions from ML API"              │
│                                                             │
│ Mistral Generates:                                          │
│ "P302 (Ultrafiltration pump) is showing an anomaly with    │
│  87% confidence. Here's the detailed analysis:             │
│                                                             │
│  **1. Anomaly Status:**                                     │
│  Stage 1 anomaly detection flagged abnormal behavior        │
│  with high confidence (87%). This indicates P302's          │
│  operating parameters have deviated from learned patterns.  │
│                                                             │
│  **2. System State:**                                       │
│  Stage 2 classified the system as WARNING (92% confidence).│
│  The system is still operational but has elevated risk.     │
│  This is not yet critical, but requires attention.          │
│                                                             │
│  **3. Component Analysis:**                                 │
│  Stage 3 identified P302 as the faulty component (85%):    │
│  • Motor temperature: 46.5°C - EXCEEDS normal range        │
│    (35-45°C) by 1.5°C ⚠️                                    │
│  • Vibration: 1.789 - ABOVE threshold of 1.5 ⚠️            │
│  • Current draw: 6.441A - Elevated from typical ~6.0A      │
│                                                             │
│  **4. Root Cause:**                                         │
│  The combination of elevated temperature AND high           │
│  vibration strongly suggests bearing wear or misalignment.  │
│  The increased current draw indicates the motor is working  │
│  harder than normal, likely due to mechanical resistance.   │
│                                                             │
│  **5. Recommended Actions:**                                │
│  🔧 Inspect UF feed pump P302                               │
│  📋 Check UF membrane differential pressure                 │
│  💧 Consider membrane backwash or cleaning                  │
│                                                             │
│  **Timeline:** Schedule maintenance within 24-48 hours.     │
│  Continue monitoring vibration trends closely."             │
│ Time: ~3 seconds                                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ PYTHON RAG API RETURNS                                      │
│ {                                                           │
│   "text": "[Mistral's detailed explanation above]",        │
│   "chartConfig": null,  // No chart for this query          │
│   "mlInsights": {                                           │
│     "isAnomaly": true,                                      │
│     "state": "WARNING",                                     │
│     "faultyComponent": "P302",                              │
│     "confidence": 0.85,                                     │
│     "recommendations": [...]                                │
│   }                                                         │
│ }                                                           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND                                                    │
│ • Renders detailed explanation                              │
│ • Shows ML insights badge (⚠️ WARNING)                      │
│ • Highlights recommended actions with emojis                │
│ • No chart (text-only response)                             │
└─────────────────────────────────────────────────────────────┘

TOTAL TIME: ~4-5 seconds
```

---

## 🧠 **RAG System Deep Dive**

### **What is RAG (Retrieval-Augmented Generation)?**

Traditional LLM approach:
```
User: "What's wrong with P302?"
LLM: "I don't have access to your system."
```

RAG approach:
```
User: "What's wrong with P302?"
   ↓
1. Retrieve relevant context:
   - P302 = Ultrafiltration pump
   - Normal temp: 35-45°C
   - Current temp: 46.5°C
   - Vibration: 1.789
   ↓
2. Inject context into LLM prompt
   ↓
3. LLM generates informed response:
   "P302 motor temperature (46.5°C) exceeds normal range..."
```

### **Why RAG is Critical for SCADA Systems**

1. **Prevents Hallucinations:** LLM can't make up sensor readings
2. **Domain Knowledge:** Teaches LLM about your specific equipment
3. **Up-to-date Info:** Queries live database, not training data
4. **Explainable:** Can show which sources informed the answer

### **ChromaDB Vector Search Explained**

**Step 1: Embedding**
```python
# User question
question = "What sensors measure flow?"

# Convert to vector (384 numbers)
embedding = embedding_model.encode(question)
# Result: [0.234, -0.156, 0.872, ..., 0.432]  (384 dimensions)
```

**Step 2: Similarity Search**
```python
# ChromaDB finds most similar stored embeddings
results = collection.query(
    query_embeddings=[embedding],
    n_results=3
)

# Returns documents ranked by cosine similarity:
# 1. "FIT sensors measure flow in L/min" (similarity: 0.91)
# 2. "Sensor naming: [TYPE][STAGE][NUMBER]" (similarity: 0.78)
# 3. "P101 pump controls flow..." (similarity: 0.52)
```

**Step 3: Context Injection**
```python
# Build enriched prompt
prompt = f"""
You are a SCADA expert.

Relevant Knowledge:
{results[0]}  # FIT sensor info
{results[1]}  # Naming convention
{results[2]}  # Pump info

User Question: {question}

Answer based on the provided knowledge.
"""

# LLM now has context to answer accurately
```

### **Session Memory vs. RAG Knowledge**

**Session Memory (Short-term):**
- Stores recent conversation turns
- Expires after 2 hours
- Enables follow-up questions like "What about the other one?"
- Example:
  ```
  User: "Show P302 data"
  Bot: [shows data]
  User: "Why is it hot?" ← Remembers "it" = P302
  ```

**RAG Knowledge (Long-term):**
- Permanent database schema and component info
- Never expires
- Consistent across all users
- Example: Always knows P302 = Ultrafiltration pump

---

## 🔐 **Security Considerations**

### **SQL Injection Prevention**

**Defense Layer 1: Validation**
```python
def validate_sql(sql: str) -> bool:
    sql_lower = sql.lower().strip()
    
    # Must start with SELECT
    if not sql_lower.startswith('select'):
        return False
    
    # Blacklist
    dangerous = ['insert', 'update', 'delete', 'drop', 'alter', 
                 'truncate', 'exec', 'execute', 'xp_', 'sp_']
    if any(kw in sql_lower for kw in dangerous):
        return False
    
    # Only allow raw_plant_data table
    if 'raw_plant_data' not in sql_lower:
        return False
    
    return True
```

**Defense Layer 2: Read-Only Database User**
```sql
-- In MS SQL, create read-only user for RAG service
CREATE USER rag_readonly WITH PASSWORD = 'SecurePassword123!';
GRANT SELECT ON dbo.raw_plant_data TO rag_readonly;
-- No INSERT/UPDATE/DELETE permissions
```

**Defense Layer 3: Query Timeout**
```python
cursor.execute(sql, timeout=5)  # Max 5 seconds
```

### **Session Hijacking Prevention**

```csharp
// Use cryptographically secure session IDs
public static string GenerateSessionId()
{
    return $"{Guid.NewGuid()}_{DateTime.UtcNow.Ticks}";
}

// Auto-expire old sessions
public void CleanupExpiredSessions()
{
    var expired = _sessions.Where(s => s.Value.IsExpired).ToList();
    foreach (var session in expired)
    {
        _sessions.TryRemove(session.Key, out _);
    }
}
```

### **API Rate Limiting**

```python
from flask_limiter import Limiter

limiter = Limiter(
    app,
    key_func=lambda: request.headers.get('X-Session-Id'),
    default_limits=["20 per minute"]  # Prevent abuse
)

@app.route("/api/chat", methods=["POST"])
@limiter.limit("5 per minute")  # Stricter for chat
def chat():
    ...
```

---

## ⚡ **Performance Optimization**

### **1. Model Caching**

```python
# Load models ONCE at startup (not per request)
MODELS = None

def get_models():
    global MODELS
    if MODELS is None:
        MODELS = load_models_from_disk()
    return MODELS
```

### **2. ChromaDB Query Caching**

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def retrieve_context(query: str):
    # Cached for identical queries
    return collection.query(query_texts=[query])
```

### **3. Database Connection Pooling**

```python
import pyodbc
from contextlib import contextmanager

# Connection pool (reuse connections)
connection_pool = []

@contextmanager
def get_db_connection():
    if connection_pool:
        conn = connection_pool.pop()
    else:
        conn = pyodbc.connect(connection_string)
    
    try:
        yield conn
    finally:
        connection_pool.append(conn)
```

### **4. Async Operations**

```csharp
// Use async/await for I/O operations
public async Task<ChatResponse> ProcessMessageAsync(...)
{
    // Don't block threads during HTTP calls
    var response = await _httpClient.PostAsync(...);
    return await response.Content.ReadFromJsonAsync<ChatResponse>();
}
```

### **5. Ollama GPU Optimization**

```bash
# Set environment variables for optimal GPU usage
export OLLAMA_NUM_PARALLEL=1       # Only 1 request at a time (6GB VRAM limit)
export OLLAMA_MAX_LOADED_MODELS=1  # Keep only Mistral loaded
export CUDA_VISIBLE_DEVICES=0      # Use first GPU
```

---

## 📊 **Performance Targets**

| Operation | Target | Acceptable | Critical |
|-----------|--------|------------|----------|
| **Intent Classification** | <2s | <3s | <5s |
| **Context Retrieval** | <50ms | <100ms | <200ms |
| **SQL Generation** | <2s | <3s | <5s |
| **SQL Execution** | <200ms | <500ms | <1s |
| **Result Explanation** | <3s | <4s | <6s |
| **Chart Generation** | <100ms | <200ms | <500ms |
| **Total Response Time** | <5s | <8s | <12s |

---

## 🚀 **Deployment Checklist**

### **Production Readiness**

- [ ] Ollama service auto-starts with system
- [ ] Python RAG service as Windows Service (or systemd)
- [ ] Database backups enabled
- [ ] Monitoring dashboards (Grafana?)
- [ ] Log rotation configured
- [ ] Error alerting (email/SMS on crashes)
- [ ] SSL/TLS enabled for production
- [ ] Firewall rules configured (only local ports)
- [ ] GPU temperature monitoring
- [ ] Disk space alerts (ChromaDB can grow)

---

## 📞 **Support & Maintenance**

### **Monitoring Commands**

```powershell
# Check Ollama status
Get-Process ollama

# Check GPU usage
nvidia-smi -l 1  # Update every 1 second

# Check Python RAG service
curl http://127.0.0.1:5001/health

# Check ChromaDB size
Get-ChildItem "D:\FYP - FINAL\Dashboard\PythonRagService\chroma_db" -Recurse | Measure-Object -Property Length -Sum
```

### **Log Locations**

- **Ollama:** `%USERPROFILE%\.ollama\logs\server.log`
- **RAG Service:** Console output (redirect to file)
- **.NET App:** Visual Studio Output / IIS logs
- **ML API:** Console output

---

**🎉 Architecture documentation complete! Ready for BATCH 2?**
