@echo off

start "Ollama" cmd /k ollama serve
start "Python RAG API" cmd /k "D:\FYP - FINAL\SwatDashboard\PythonRagService\start_rag_api.bat"

exit
