# 🔧 INSTALLATION GUIDE - SWAT AI Chatbot Setup

**Last Updated:** January 26, 2026  
**Target System:** Windows 11, Acer Predator Helios 300 (RTX 3060 6GB)  
**Python Environment:** Existing venv at `D:\FYP - FINAL\venv`

---

## 📋 **Table of Contents**

1. [Prerequisites Check](#prerequisites-check)
2. [Ollama Installation](#ollama-installation)
3. [Mistral 7B Model Download](#mistral-7b-model-download)
4. [Python RAG Service Setup](#python-rag-service-setup)
5. [ChromaDB Initialization](#chromadb-initialization)
6. [Testing Your Setup](#testing-your-setup)
7. [Troubleshooting](#troubleshooting)

---

## ✅ **Prerequisites Check**

Before starting, verify you have:

```powershell
# Check Python version (should be 3.8+)
python --version

# Check CUDA is available (for GPU acceleration)
nvidia-smi

# Check your existing venv
D:\FYP - FINAL\venv\Scripts\activate
python -c "import sys; print(sys.executable)"
```

**Expected Output:**
- Python 3.9+ 
- NVIDIA Driver 470+
- CUDA 11.2+
- venv path: `D:\FYP - FINAL\venv\Scripts\python.exe`

---

## 🦙 **Ollama Installation**

### **Step 1: Download Ollama for Windows**

1. Open browser, go to: https://ollama.com/download/windows
2. Download `OllamaSetup.exe` (approx. 500MB)
3. Run installer with administrator privileges
4. Follow installation wizard (default options are fine)

**Installation Location:** `C:\Users\<YourName>\AppData\Local\Programs\Ollama`

### **Step 2: Verify Ollama Installation**

Open **Command Prompt** (not PowerShell for this step):

```cmd
ollama --version
```

**Expected Output:**
```
ollama version is 0.1.x
```

### **Step 3: Start Ollama Service**

Ollama runs as a background service. Start it:

```cmd
ollama serve
```

**Expected Output:**
```
Ollama server starting on http://127.0.0.1:11434
```

**⚠️ IMPORTANT:** Keep this terminal window open! Ollama must be running for the chatbot to work.

**Alternative:** Ollama auto-starts with Windows. To check if it's running:

```powershell
# Check if Ollama is running
Get-Process ollama -ErrorAction SilentlyContinue
```

---

## 🤖 **Mistral 7B Model Download**

### **Step 1: Pull Mistral Model**

Open **NEW Command Prompt window**, run:

```cmd
ollama pull mistral:7b-instruct-v0.3-q4_K_M
```

**Download Size:** ~4.1 GB  
**Time:** 10-30 minutes (depends on internet speed)

**Expected Output:**
```
pulling manifest 
pulling 8934d96d3f08... 100% ▕████████████████▏ 4.1 GB                         
pulling 8c17c2ebb0ea... 100% ▕████████████████▏ 7.0 KB                         
pulling 7c23fb36d801... 100% ▕████████████████▏ 4.8 KB                         
pulling 2e0493f67d0c... 100% ▕████████████████▏   59 B                         
pulling fa304d675061... 100% ▕████████████████▏   91 B                         
pulling 42347cd80dc8... 100% ▕████████████████▏  485 B                         
verifying sha256 digest 
writing manifest 
removing any unused layers 
success
```

### **Step 2: Verify Model is Available**

```cmd
ollama list
```

**Expected Output:**
```
NAME                            ID              SIZE      MODIFIED
mistral:7b-instruct-v0.3        8934d96d3f08    4.1 GB    2 minutes ago
```

### **Step 3: Test Model Inference**

```cmd
ollama run mistral:7b-instruct-v0.3-q4_K_M "Hello, can you help me with SCADA systems?"
```

**Expected Output:** Should respond with relevant text about SCADA systems in 2-5 seconds.

**⚠️ GPU Check:** Monitor GPU usage while testing:

```powershell
nvidia-smi
```

You should see `ollama_llama_server.exe` using 4-5GB VRAM.

---

## 🐍 **Python RAG Service Setup**

### **Step 1: Activate Existing Virtual Environment**

```powershell
cd "D:\FYP - FINAL"
.\venv\Scripts\Activate.ps1
```

**If you get execution policy error:**

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then retry activation.

### **Step 2: Upgrade pip**

```powershell
python -m pip install --upgrade pip
```

### **Step 3: Install RAG Service Dependencies**

```powershell
pip install --break-system-packages -r Dashboard\PythonRagService\requirements.txt
```

**Expected Packages (~15-20 packages):**
- `ollama` - Ollama Python client
- `chromadb` - Vector database
- `langchain` - RAG framework
- `pyodbc` - MS SQL connector
- `flask` - Web server
- `reportlab` - PDF generation
- `openpyxl` - Excel generation
- And more...

**Installation Time:** 5-10 minutes

### **Step 4: Verify ODBC Driver for SQL Server**

```powershell
# Check installed ODBC drivers
Get-OdbcDriver | Where-Object {$_.Name -like "*SQL Server*"}
```

**Expected Output:** Should show `ODBC Driver 17 for SQL Server` or similar.

**If missing, download from:**
https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

---

## 🗄️ **ChromaDB Initialization**

ChromaDB will store database schema and component knowledge for RAG.

### **Step 1: Initialize ChromaDB**

```powershell
cd "D:\FYP - FINAL\Dashboard\PythonRagService"
python initialize_chromadb.py
```

**Expected Output:**
```
============================================================
ChromaDB Initialization for SWAT RAG Service
============================================================
✅ ChromaDB initialized at: D:\FYP - FINAL\Dashboard\PythonRagService\chroma_db
✅ Embedding 4 knowledge documents...
✅ Document 'schema_main' embedded (384 dimensions)
✅ Document 'components_pumps' embedded (384 dimensions)
✅ Document 'components_sensors' embedded (384 dimensions)
✅ Document 'ml_models' embedded (384 dimensions)
✅ ChromaDB ready! Total documents: 4
```

### **Step 2: Test Vector Search**

```powershell
python test_chromadb.py
```

**Expected Output:**
```
Testing ChromaDB vector search...
Query: "What pumps are in stage 2?"
Top Result: P201, P203, P205: Secondary treatment pumps (Stage 2)
✅ ChromaDB working correctly!
```

---

## 🧪 **Testing Your Setup**

### **Test 1: Ollama API Accessibility**

```powershell
# Test direct Ollama API
curl http://127.0.0.1:11434/api/tags
```

**Expected Output:** JSON with model list including Mistral.

### **Test 2: RAG Service Health Check**

Start the RAG service:

```powershell
cd "D:\FYP - FINAL\Dashboard\PythonRagService"
python rag_api.py
```

**Expected Output:**
```
============================================================
SWaT RAG Service with Mistral 7B
============================================================
✅ Ollama connected
✅ ChromaDB loaded (4 documents)
✅ ML API accessible at http://127.0.0.1:5000
Starting on http://localhost:5001
```

In **NEW terminal window**, test health endpoint:

```powershell
curl http://127.0.0.1:5001/health
```

**Expected Output:**
```json
{
  "status": "ok",
  "ollama_connected": true,
  "chromadb_ready": true,
  "ml_api_available": true,
  "models_loaded": ["mistral:7b-instruct-v0.3-q4_K_M"]
}
```

### **Test 3: Simple Chat Query**

```powershell
curl -X POST http://127.0.0.1:5001/api/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"message\": \"What sensors are available?\", \"session_id\": \"test123\"}"
```

**Expected Response Time:** 3-5 seconds  
**Expected Output:** JSON with text explanation of available sensors.

### **Test 4: GPU Usage Monitoring**

While RAG service is running, open **Task Manager** → **Performance** → **GPU**

**Expected:**
- GPU Utilization: 40-60% during inference
- VRAM Usage: 4.5-5.5 GB
- Temperature: 60-75°C (normal under load)

### **Test 5: End-to-End Integration Test**

```powershell
cd "D:\FYP - FINAL\Dashboard"
python test_integration.py
```

This will test:
1. ✅ ML API (Port 5000) connectivity
2. ✅ RAG API (Port 5001) connectivity
3. ✅ Database connection
4. ✅ Sample chat query
5. ✅ SQL generation and execution
6. ✅ ML model inference integration

---

## 🔧 **Troubleshooting**

### **Problem 1: Ollama Not Found**

**Symptom:** `ollama: command not found`

**Solution:**
```powershell
# Add Ollama to PATH manually
$env:Path += ";C:\Users\$env:USERNAME\AppData\Local\Programs\Ollama"

# Verify
ollama --version
```

### **Problem 2: Model Download Fails**

**Symptom:** `Error pulling model: connection timeout`

**Solution:**
```powershell
# Use alternative mirror (if available)
ollama pull mistral:7b-instruct-v0.3-q4_K_M --insecure

# Or download manually and import
```

### **Problem 3: GPU Not Detected**

**Symptom:** Ollama uses CPU only (very slow)

**Solution:**
```powershell
# Check CUDA installation
nvidia-smi

# Reinstall CUDA toolkit if needed
# https://developer.nvidia.com/cuda-downloads

# Verify GPU is enabled in Ollama
ollama ps
```

### **Problem 4: ChromaDB Permission Error**

**Symptom:** `PermissionError: [WinError 5] Access is denied`

**Solution:**
```powershell
# Run as administrator OR
# Change ChromaDB directory permissions
icacls "D:\FYP - FINAL\Dashboard\PythonRagService\chroma_db" /grant Users:F /t
```

### **Problem 5: ODBC Driver Missing**

**Symptom:** `pyodbc.InterfaceError: ('IM002', '[IM002] [Microsoft][ODBC Driver Manager] Data source name not found')`

**Solution:**
```powershell
# Download and install ODBC Driver 17
# https://go.microsoft.com/fwlink/?linkid=2249004

# Verify installation
Get-OdbcDriver
```

### **Problem 6: Port Already in Use**

**Symptom:** `OSError: [WinError 10048] Only one usage of each socket address`

**Solution for Port 5001:**
```powershell
# Find process using port 5001
netstat -ano | findstr :5001

# Kill process (replace <PID> with actual PID)
taskkill /PID <PID> /F

# Restart RAG service
```

### **Problem 7: Slow Inference (>10 seconds)**

**Possible Causes & Solutions:**

1. **Using CPU instead of GPU:**
   ```powershell
   # Check if GPU is being used
   nvidia-smi
   
   # If not, reinstall Ollama with GPU support
   ```

2. **VRAM Fragmentation:**
   ```powershell
   # Restart Ollama service
   taskkill /IM ollama.exe /F
   ollama serve
   ```

3. **Model not quantized properly:**
   ```powershell
   # Re-download model
   ollama rm mistral:7b-instruct-v0.3-q4_K_M
   ollama pull mistral:7b-instruct-v0.3-q4_K_M
   ```

### **Problem 8: RAG Service Can't Connect to ML API**

**Symptom:** `ML API is not available` error

**Solution:**
```powershell
# Verify ML API is running
curl http://127.0.0.1:5000/health

# If not running, start it from your .NET app
cd "D:\FYP - FINAL\Dashboard"
dotnet run
```

---

## 📊 **Performance Benchmarks**

After successful installation, you should achieve:

| Metric | Target | Acceptable |
|--------|--------|------------|
| **Ollama Response Time** | 2-4 seconds | <5 seconds |
| **SQL Query Generation** | 1-2 seconds | <3 seconds |
| **Chart Generation** | <1 second | <2 seconds |
| **Full Chat Response** | 3-5 seconds | <8 seconds |
| **GPU VRAM Usage** | 4.5-5.5 GB | <6 GB |
| **GPU Temperature** | 60-75°C | <80°C |

---

## ✅ **Installation Complete Checklist**

Before proceeding to BATCH 2, verify:

- [ ] Ollama installed and running (`ollama serve` in background)
- [ ] Mistral 7B model downloaded (`ollama list` shows model)
- [ ] Test inference works (<5 seconds response)
- [ ] Python venv activated
- [ ] All requirements installed (no errors)
- [ ] ChromaDB initialized (4 documents embedded)
- [ ] RAG service starts without errors
- [ ] Health check returns `"status": "ok"`
- [ ] Sample chat query works
- [ ] GPU is being used (check nvidia-smi)
- [ ] ML API accessible at port 5000
- [ ] RAG API accessible at port 5001

---

## 🚀 **Next Steps**

Once all checks pass:

1. Keep Ollama running in background
2. Move to **BATCH 2: Frontend Development**
3. Create chat interface in your dashboard

---

## 📞 **Need Help?**

If you encounter issues not covered here:

1. Check Ollama logs: `C:\Users\<YourName>\.ollama\logs\server.log`
2. Check RAG service logs: Terminal output
3. Check GPU status: `nvidia-smi`
4. Review Python errors: Full stack trace

**Common Log Locations:**
- Ollama: `%USERPROFILE%\.ollama\logs\`
- Python RAG: Console output (save to file with `python rag_api.py > rag.log 2>&1`)
- .NET App: Visual Studio Output window

---

**🎉 Ready to continue? Reply with "BATCH 2 READY" once installation is verified!**
