@echo off
REM ============================================================================
REM SWAT AI Chatbot - Automated Setup Script for Windows
REM ============================================================================
REM Run this script from: D:\FYP - FINAL\Dashboard
REM Requirements: Python 3.9+, pip, existing venv
REM ============================================================================

echo.
echo ============================================================================
echo SWAT AI CHATBOT - SETUP SCRIPT
echo ============================================================================
echo.

REM Check if running from correct directory
if not exist "PythonRagService" (
    echo [ERROR] Please run this script from D:\FYP - FINAL\Dashboard
    echo Current directory: %CD%
    pause
    exit /b 1
)

REM ============================================================================
REM STEP 1: Activate Virtual Environment
REM ============================================================================
echo [1/8] Activating virtual environment...
if not exist "..\.venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at D:\FYP - FINAL\.venv
    echo Please create venv first: python -m venv D:\FYP - FINAL\.venv
    pause
    exit /b 1
)

call ..\.venv\Scripts\activate.bat
echo [OK] Virtual environment activated
echo.

REM ============================================================================
REM STEP 2: Check Python Version
REM ============================================================================
echo [2/8] Checking Python version...
python --version
if errorlevel 1 (
    echo [ERROR] Python not found in venv
    pause
    exit /b 1
)
echo [OK] Python version check passed
echo.

REM ============================================================================
REM STEP 3: Upgrade pip
REM ============================================================================
echo [3/8] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo [WARNING] pip upgrade failed, continuing anyway...
)
echo [OK] pip upgraded
echo.

REM ============================================================================
REM STEP 4: Install Python Dependencies
REM ============================================================================
echo [4/8] Installing Python dependencies...
echo This may take 5-10 minutes...
pip install --break-system-packages -r PythonRagService\requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    echo Check PythonRagService\requirements.txt exists
    pause
    exit /b 1
)
echo [OK] All dependencies installed
echo.

REM ============================================================================
REM STEP 5: Create ChromaDB Directory
REM ============================================================================
echo [5/8] Creating ChromaDB directory...
if not exist "PythonRagService\chroma_db" (
    mkdir PythonRagService\chroma_db
    echo [OK] ChromaDB directory created
) else (
    echo [OK] ChromaDB directory already exists
)
echo.

REM ============================================================================
REM STEP 6: Initialize ChromaDB with Knowledge Base
REM ============================================================================
echo [6/8] Initializing ChromaDB with SWAT knowledge...
python PythonRagService\initialize_chromadb.py
if errorlevel 1 (
    echo [ERROR] ChromaDB initialization failed
    pause
    exit /b 1
)
echo [OK] ChromaDB initialized
echo.

REM ============================================================================
REM STEP 7: Verify ODBC Driver
REM ============================================================================
echo [7/8] Checking ODBC Driver for SQL Server...
powershell -Command "Get-OdbcDriver | Where-Object {$_.Name -like '*SQL Server*'}" > nul 2>&1
if errorlevel 1 (
    echo [WARNING] ODBC Driver 17 for SQL Server not found
    echo Download from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
    echo.
    echo Press any key to continue anyway...
    pause > nul
) else (
    echo [OK] ODBC Driver found
)
echo.

REM ============================================================================
REM STEP 8: Test Installation
REM ============================================================================
echo [8/8] Testing installation...
python -c "import ollama; import chromadb; import flask; import pyodbc; import reportlab; import openpyxl; print('OK - All imports successful')"
if errorlevel 1 (
    echo [ERROR] Import test failed
    echo Some packages may not be installed correctly
    pause
    exit /b 1
)
echo [OK] All packages imported successfully
echo.

REM ============================================================================
REM SETUP COMPLETE
REM ============================================================================
echo.
echo ============================================================================
echo SETUP COMPLETE
echo ============================================================================
echo.
echo Next steps:
echo 1. Install Ollama from https://ollama.com/download/windows
echo 2. Download Mistral 7B model: ollama pull mistral:7b-instruct-v0.3-q4_K_M
echo 3. Start Ollama service: ollama serve
echo 4. Test RAG service: python PythonRagService\rag_api.py
echo.
echo For detailed instructions, see:
echo - INSTALLATION_GUIDE.md
echo - ARCHITECTURE_DOCUMENTATION.md
echo.
echo ============================================================================
echo.

pause
