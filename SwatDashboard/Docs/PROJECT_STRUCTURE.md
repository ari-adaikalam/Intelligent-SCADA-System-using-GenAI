# 📁 PROJECT STRUCTURE GUIDE

**Last Updated:** January 26, 2026  
**Project Root:** `D:\FYP - FINAL\`

---

## 🗂️ **Complete Directory Tree**

```
D:\FYP - FINAL\
│
├── 📁 .venv\                                    # Python virtual environment (EXISTING)
│   ├── Scripts\
│   │   ├── python.exe
│   │   ├── pip.exe
│   │   └── activate.bat
│   └── Lib\
│
├── 📁 SwatDashboard\                                # Main ASP.NET project (EXISTING)
│   │
│   ├── 📄 SwatDashboard.csproj                 # Project file
│   ├── 📄 SwatDashboard.sln                    # Solution file
│   ├── 📄 Program.cs                           # Application entry point
│   ├── 📄 appsettings.json                     # Configuration
│   │
│   ├── 📁 Controllers\                          # API Controllers (EXISTING + NEW)
│   │   ├── DashboardController.cs              # [EXISTING] Main dashboard
│   │   ├── AnalyticsController.cs              # [EXISTING] Analytics endpoints
│   │   ├── ExportController.cs                 # [EXISTING] Export functionality
│   │   └── ChatController.cs                   # [NEW - BATCH 3] AI chat endpoints
│   │
│   ├── 📁 Services\                             # Business logic services (EXISTING + NEW)
│   │   ├── DatabaseService.cs                  # [EXISTING] Database access
│   │   ├── ExportService.cs                    # [EXISTING] Export functionality
│   │   ├── MlInferenceService.cs               # [EXISTING] ML API integration
│   │   ├── LiveDataBackgroundService.cs        # [EXISTING] Real-time data
│   │   ├── MlApiHostedService.cs               # [EXISTING] ML API hosting
│   │   └── ChatService.cs                      # [NEW - BATCH 3] RAG API integration
│   │
│   ├── 📁 Models\                               # Data models (EXISTING + NEW)
│   │   ├── DataModels.cs                       # [EXISTING] Core data models
│   │   └── ChatModels.cs                       # [NEW - BATCH 3] Chat-specific models
│   │
│   ├── 📁 Hubs\                                 # SignalR hubs (EXISTING)
│   │   └── LiveDataHub.cs                      # Real-time data streaming
│   │
│   ├── 📁 Views\                                # Razor views (EXISTING + MODIFIED)
│   │   ├── Dashboard\
│   │   │   └── Index.cshtml                    # [MODIFIED - BATCH 2] Add chat tab
│   │   └── Shared\
│   │       ├── _Layout.cshtml                  # [EXISTING] Master layout
│   │       └── _ViewImports.cshtml             # [EXISTING] View imports
│   │
│   ├── 📁 wwwroot\                              # Static web assets (EXISTING + NEW)
│   │   ├── 📁 css\
│   │   │   └── chat.css                        # [NEW - BATCH 2] Chat styling
│   │   ├── 📁 js\
│   │   │   ├── dashboard.js                    # [EXISTING] Dashboard logic
│   │   │   └── chat.js                         # [NEW - BATCH 2] Chat interface logic
│   │   └── 📁 lib\
│   │       └── Chart.js (or via CDN)           # [EXISTING] Charting library
│   │
│   ├── 📁 PythonMlService\                      # Existing ML API (EXISTING)
│   │   ├── ml_api.py                           # Flask ML API
│   │   ├── ml_inference.py                     # 3-stage ML pipeline
│   │   ├── sensor_buffer.py                    # Buffer for temporal analysis
│   │   ├── alerts.py                           # Alert system
│   │   ├── requirements.txt                    # ML dependencies
│   │   ├── 📁 models\                           # Trained ML models
│   │   │   ├── stage1\
│   │   │   ├── stage2\
│   │   │   └── stage3\
│   │   └── 📁 ml_data\                          # ML data and scaler
│   │       └── scaler.pkl
│   │
│   └── 📁 PythonRagService\                     # NEW AI RAG Service (NEW - BATCH 4)
│       │
│       ├── 📄 rag_api.py                        # [NEW] Main Flask API
│       ├── 📄 rag_engine.py                    # [NEW] RAG logic core
│       ├── 📄 sql_generator.py                 # [NEW] SQL generation & validation
│       ├── 📄 report_generator.py              # [NEW] PDF/Excel report generation
│       ├── 📄 initialize_chromadb.py           # [NEW] ChromaDB setup script
│       ├── 📄 test_chromadb.py                 # [NEW] ChromaDB test script
│       ├── 📄 requirements.txt                 # [NEW] RAG dependencies
│       │
│       ├── 📁 chroma_db\                        # [NEW] ChromaDB persistent storage
│       │   └── (vector embeddings stored here)
│       │
│       ├── 📁 downloads\                        # [NEW] Generated reports
│       │   ├── report_20260126.pdf
│       │   └── report_20260126.xlsx
│       │
│       └── 📁 logs\                             # [NEW] RAG service logs
│           └── rag_service.log
│
└── 📁 docs\                                      # Documentation (NEW - BATCH 1)
    ├── INSTALLATION_GUIDE.md                   # [NEW] Setup instructions
    ├── ARCHITECTURE_DOCUMENTATION.md           # [NEW] System architecture
    ├── PROJECT_STRUCTURE.md                    # [NEW] This file
    ├── API_REFERENCE.md                        # [NEW - BATCH 4] API documentation
    └── USER_GUIDE.md                           # [NEW - BATCH 5] End-user guide
```

---

## 📦 **Batch-by-Batch File Creation Plan**

### **BATCH 1: Setup & Documentation** ✅ (Current)
**Location:** `D:\FYP - FINAL\docs\`

Files created:
1. ✅ `INSTALLATION_GUIDE.md` - Ollama + Mistral setup
2. ✅ `ARCHITECTURE_DOCUMENTATION.md` - Complete system design
3. ✅ `PROJECT_STRUCTURE.md` - This file
4. ✅ `requirements.txt` - Python dependencies
5. ✅ `setup_windows.bat` - Automated setup script

**Action:** Download these 5 files to `D:\FYP - FINAL\Dashboard\docs\`

---

### **BATCH 2: Frontend - Chat Interface** (Next)
**Location:** `D:\FYP - FINAL\Dashboard\wwwroot\`

Files to create:
1. `wwwroot/css/chat.css` - Chat styling (colors, layout, animations)
2. `wwwroot/js/chat.js` - Chat interface logic (message handling, Chart.js)
3. `Views/Dashboard/Index.cshtml` - Modified with chat tab

**Action:** Add chat tab to existing dashboard

---

### **BATCH 3: C# Backend Integration**
**Location:** `D:\FYP - FINAL\Dashboard\`

Files to create:
1. `Controllers/ChatController.cs` - Chat API endpoints
2. `Services/ChatService.cs` - Python RAG API client
3. `Models/ChatModels.cs` - Chat-specific data models
4. `Program.cs` - Modified to register ChatService

**Action:** Add backend support for chat

---

### **BATCH 4: Python RAG Service**
**Location:** `D:\FYP - FINAL\Dashboard\PythonRagService\`

Files to create:
1. `rag_api.py` - Main Flask API (routes, health checks)
2. `rag_engine.py` - Core RAG logic (6-stage pipeline)
3. `sql_generator.py` - SQL generation + validation
4. `report_generator.py` - PDF/Excel generation
5. `initialize_chromadb.py` - ChromaDB setup
6. `test_chromadb.py` - Testing script
7. `requirements.txt` - Already created in BATCH 1

**Action:** Build AI engine

---

### **BATCH 5: Testing & Integration**
**Location:** Various

Files to create:
1. `test_integration.py` - End-to-end testing
2. `test_ml_integration.py` - ML API integration test
3. `test_rag_service.py` - RAG service unit tests
4. `USER_GUIDE.md` - Documentation for operators

**Action:** Verify everything works

---

## 🗺️ **File Relationships & Dependencies**

```
┌─────────────────────────────────────────────────────────────┐
│                     USER BROWSER                            │
│                           ↓                                 │
│  Views/Dashboard/Index.cshtml                               │
│           ↓ (loads)                                         │
│  wwwroot/js/chat.js + wwwroot/css/chat.css                  │
│           ↓ (calls)                                         │
│  Controllers/ChatController.cs                              │
│           ↓ (uses)                                          │
│  Services/ChatService.cs                                    │
│           ↓ (HTTP call)                                     │
│  PythonRagService/rag_api.py                                │
│           ↓ (uses)                                          │
│  PythonRagService/rag_engine.py                             │
│           ├─→ sql_generator.py                              │
│           ├─→ report_generator.py                           │
│           ├─→ chroma_db/ (vector search)                    │
│           └─→ PythonMlService/ml_api.py (ML predictions)    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 **Configuration Files**

### **appsettings.json** (Existing, needs modification)
```json
{
  "ConnectionStrings": {
    "SwatDatabase": "Server=localhost;Database=swat;..."
  },
  "SwatSettings": {
    "RefreshIntervalMs": 1000,
    "OfflineThresholdSeconds": 5,
    "PythonMlApiUrl": "http://127.0.0.1:5000",
    "PythonRagApiUrl": "http://127.0.0.1:5001"  // ADD THIS
  }
}
```

### **requirements.txt** (Two versions)

**PythonMlService/requirements.txt** (Existing):
- TensorFlow, XGBoost, LightGBM, etc.

**PythonRagService/requirements.txt** (New):
- Ollama, ChromaDB, Flask, ReportLab, etc.

---

## 📊 **Ports & Services**

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| **ASP.NET App** | 5000/5001 | HTTPS | Main dashboard (EXISTING) |
| **SignalR Hub** | 5000/5001 | WebSocket | Real-time data (EXISTING) |
| **Python ML API** | 5000 | HTTP | ML inference (EXISTING) |
| **Python RAG API** | 5001 | HTTP | AI chatbot (NEW) |
| **Ollama LLM** | 11434 | HTTP | Mistral 7B (NEW) |
| **MS SQL Server** | 1433 | TCP | Database (EXISTING) |

**Note:** ASP.NET and Python ML API both use port 5000 but different protocols. ASP.NET uses HTTPS (5001) for production.

---

## 🗃️ **Database Schema**

### **Existing Tables**

```sql
-- EXISTING: Main SCADA data table
CREATE TABLE raw_plant_data (
    id INT PRIMARY KEY IDENTITY,
    ts DATETIME2 NOT NULL,
    plant_id NVARCHAR(50),
    payload_json NVARCHAR(MAX),
    INDEX idx_ts (ts),
    INDEX idx_plant_id (plant_id)
);
```

### **No New Tables Required**

The AI chatbot uses:
- ✅ Existing `raw_plant_data` table (read-only)
- ✅ In-memory session storage (C# ConcurrentDictionary)
- ✅ ChromaDB for vector embeddings (file-based, not SQL)

**No database schema changes needed!** ✅

---

## 🎨 **Styling & Branding**

### **Color Scheme (SCADA Standard)**

```css
/* wwwroot/css/chat.css will use these colors */
:root {
    /* System Status Colors */
    --color-normal: #4CAF50;      /* Green */
    --color-warning: #FF9800;     /* Orange */
    --color-critical: #F44336;    /* Red */
    --color-offline: #9E9E9E;     /* Gray */
    
    /* Chart Colors */
    --color-primary: #2196F3;     /* Blue */
    --color-secondary: #00BCD4;   /* Cyan */
    --color-accent: #FFC107;      /* Amber */
    
    /* UI Colors */
    --color-background: #1E1E1E;  /* Dark */
    --color-surface: #2D2D2D;     /* Slightly lighter */
    --color-text: #FFFFFF;        /* White */
    --color-text-secondary: #B0B0B0; /* Gray */
}
```

### **Company Branding Placeholders**

**In report_generator.py:**
```python
COMPANY_NAME = "SWAT Water Treatment Solutions"  # PLACEHOLDER
LOGO_PATH = "logo_placeholder.png"  # PLACEHOLDER
```

**You can replace these later without changing code structure.**

---

## 🚀 **Deployment Workflow**

### **Development (Your Current Setup)**

```
1. Start MS SQL Server
2. Start .NET App: dotnet run
   → ML API auto-starts on port 5000
3. Start Ollama: ollama serve (port 11434)
4. Start RAG API: python PythonRagService/rag_api.py (port 5001)
5. Open browser: https://localhost:5001
6. Click "Chat" tab
```

### **Production (Future)**

```
1. ML API as Windows Service
2. RAG API as Windows Service
3. Ollama as Windows Service (auto-start)
4. .NET App deployed to IIS
5. Reverse proxy (optional): Nginx/IIS URL Rewrite
```

---

## 📦 **Package Dependencies**

### **Python Packages** (Total ~2GB with dependencies)

**PythonMlService:** (Already installed)
- TensorFlow: ~500MB
- XGBoost: ~100MB
- LightGBM: ~50MB
- Flask: ~10MB

**PythonRagService:** (New)
- Ollama: ~5MB (client only)
- ChromaDB: ~300MB (includes embedding model)
- ReportLab: ~50MB
- Sentence-Transformers: ~400MB (embedding model)

**Total New:** ~750MB

### **.NET Packages** (Already installed)

- ASP.NET Core
- SignalR
- Dapper
- EPPlus (Excel)
- iText7 (PDF)

**No new .NET packages required!** ✅

---

## 🔐 **Security Notes**

### **File Permissions**

```powershell
# Ensure Python can write to these directories:
icacls "D:\FYP - FINAL\Dashboard\PythonRagService\chroma_db" /grant Users:F
icacls "D:\FYP - FINAL\Dashboard\PythonRagService\downloads" /grant Users:F
icacls "D:\FYP - FINAL\Dashboard\PythonRagService\logs" /grant Users:F
```

### **Sensitive Files** (Add to .gitignore)

```
# .gitignore additions
appsettings.json         # Contains database password
*.log                    # Log files
PythonRagService/chroma_db/  # Vector embeddings
PythonRagService/downloads/  # Generated reports
.env                     # Environment variables
```

---

## 📞 **Where to Find Things**

| What | Where |
|------|-------|
| **Database connection string** | `appsettings.json` |
| **ML models** | `PythonMlService/models/` |
| **Vector embeddings** | `PythonRagService/chroma_db/` |
| **Generated reports** | `PythonRagService/downloads/` |
| **Frontend assets** | `wwwroot/css/` and `wwwroot/js/` |
| **API controllers** | `Controllers/` |
| **Business logic** | `Services/` |
| **Documentation** | `docs/` |
| **Logs (RAG)** | `PythonRagService/logs/` |
| **Logs (.NET)** | Visual Studio Output or IIS logs |

---

## ✅ **Next Steps After BATCH 1**

1. ✅ Download all BATCH 1 files to `D:\FYP - FINAL\Dashboard\docs\`
2. ✅ Run `setup_windows.bat` to install Python dependencies
3. ✅ Follow `INSTALLATION_GUIDE.md` to install Ollama + Mistral
4. ✅ Verify installation with health checks
5. ➡️ Proceed to **BATCH 2: Frontend Development**

---

**🎉 Project structure documented! Ready to build!**
