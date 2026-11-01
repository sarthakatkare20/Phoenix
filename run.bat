@echo off
title Phoenix - AI Assistant
echo ===================================================
echo           PHOENIX - STARTING BACKEND & FACE
echo ===================================================

echo [1/2] Starting Phoenix Python Backend on Port 8000...
start "Phoenix Backend" cmd /k "python -m uvicorn server:app --host 127.0.0.1 --port 8000"

timeout /t 2 /nobreak >nul

echo [2/2] Starting Phoenix React 3D Interface on Port 5173...
start "Phoenix Face" cmd /k "npm run dev"

echo ===================================================
echo Phoenix is launching!
echo UI:  http://localhost:5173
echo API: http://localhost:8000/docs
echo ===================================================
